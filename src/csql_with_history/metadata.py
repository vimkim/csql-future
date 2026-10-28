"""Bounded catalog reads through an independent csql process."""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import subprocess
import tempfile
import threading
import time

from .completion import Relation, Schema


CATALOG_QUERY = """
SELECT 'relation' AS kind, CURRENT_USER AS login_name, owner_name, class_name,
       class_name AS item_name, class_type AS item_type
FROM db_class WHERE is_system_class = 'NO'
UNION ALL
SELECT 'column', CURRENT_USER, a.owner_name, a.class_name, a.attr_name, a.attr_type
FROM db_attribute a JOIN db_class c
ON a.owner_name = c.owner_name AND a.class_name = c.class_name
WHERE c.is_system_class = 'NO' AND a.attr_type IN ('INSTANCE', 'SHARED');
"""
HEADER = ['kind', 'login_name', 'owner_name', 'class_name', 'item_name', 'item_type']
MAX_CATALOG_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Connection:
  arguments: tuple[str, ...]
  standalone: bool


def unescape(value: str) -> str:
  escaped = {'n': '\n', 't': '\t', '\\': '\\'}
  result = []
  index = 0
  while index < len(value):
    if value[index] == '\\':
      index += 1
      if index == len(value) or value[index] not in escaped:
        raise ValueError('invalid plain-output escape')
      result.append(escaped[value[index]])
    else:
      result.append(value[index])
    index += 1
  return ''.join(result)


def parse_catalog(output: bytes) -> Schema:
  lines = output.decode('utf-8').splitlines()
  if not lines or lines[0].split('\t') != HEADER:
    raise ValueError('missing catalog header')
  relations = {}
  columns: dict[tuple[str, str], list[str]] = {}
  user = ''
  for line in lines[1:]:
    if not line:
      continue
    fields = [unescape(field) for field in line.split('\t')]
    if len(fields) != 6:
      raise ValueError('invalid catalog row')
    kind, login, owner, name, item, item_type = fields
    if user and login != user or not login or not owner or not name:
      raise ValueError('invalid catalog identity')
    user = login
    key = owner, name
    if kind == 'relation' and item_type in ('CLASS', 'VCLASS'):
      relations[key] = item_type
    elif kind == 'column' and item_type in ('INSTANCE', 'SHARED'):
      columns.setdefault(key, []).append(item)
    else:
      raise ValueError('invalid catalog kind')
  return Schema(user, tuple(
    Relation(owner, name, kind, tuple(sorted(set(columns.get((owner, name), ())), key=str.casefold)))
    for (owner, name), kind in sorted(relations.items())
  ))


class CatalogCache:
  """Publish immutable snapshots. Only the editor thread draws the menu."""

  def __init__(self, executable: str, connection: Connection | None, timeout: float = 3.0) -> None:
    self.executable = executable
    self.connection = connection
    self.timeout = timeout
    self.schema = Schema()
    self.message = 'Schema unavailable for these connection options' if connection is None else ''
    self.revision = 0
    self.updated = 0.0
    self.refresh_seconds = 60.0
    self.worker: threading.Thread | None = None
    self.stop = threading.Event()
    self.lock = threading.Lock()

  def snapshot(self) -> tuple[Schema, str, int]:
    with self.lock:
      return self.schema, self.message, self.revision

  def request(self, force: bool = False) -> None:
    with self.lock:
      if self.connection is None or self.stop.is_set():
        return
      if self.connection.standalone:
        if force:
          self.message = 'Standalone snapshot: restart to refresh schema'
          self.revision += 1
        return
      if self.worker is not None and self.worker.is_alive():
        return
      if not force and self.updated and time.monotonic() - self.updated < self.refresh_seconds:
        return
      self.message = 'Loading schema'
      self.revision += 1
      self.worker = threading.Thread(target=self._load, daemon=True, name='csql-catalog')
      self.worker.start()

  def prepare_standalone(self) -> None:
    """Run once before the interactive client acquires the standalone DB."""
    if self.connection is not None and self.connection.standalone:
      self._load()
      with self.lock:
        if not self.message:
          self.message = 'Standalone schema snapshot'

  def _load(self) -> None:
    try:
      schema = self._read()
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
      with self.lock:
        self.message = 'Schema refresh failed; using cached names' if self.schema.relations else 'Schema unavailable; keywords only'
        self.updated = time.monotonic()
        self.revision += 1
      return
    with self.lock:
      self.schema = schema
      self.message = ''
      self.updated = time.monotonic()
      self.revision += 1

  def _read(self) -> Schema:
    assert self.connection is not None
    command = [self.executable, *self.connection.arguments, '-r', '-t', '-c', CATALOG_QUERY]
    # A file bounds waiting even if an unexpected descendant keeps stdout open.
    with tempfile.TemporaryFile() as output:
      process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
      deadline = time.monotonic() + self.timeout
      try:
        while process.poll() is None:
          if self.stop.wait(0.02) or time.monotonic() >= deadline or os.fstat(output.fileno()).st_size > MAX_CATALOG_BYTES:
            raise ValueError('catalog request cancelled or exceeded its limit')
        if process.returncode != 0:
          raise ValueError('catalog request failed')
        output.seek(0)
        data = output.read(MAX_CATALOG_BYTES + 1)
        if len(data) > MAX_CATALOG_BYTES:
          raise ValueError('catalog result too large')
        return parse_catalog(data)
      finally:
        if process.poll() is None:
          try:
            os.killpg(process.pid, signal.SIGKILL)
          except ProcessLookupError:
            pass
          process.wait()

  def close(self) -> None:
    self.stop.set()
    if self.worker is not None:
      self.worker.join(timeout=1.0)

#!/usr/bin/env python3
#
# Copyright 2008 Search Solution Corporation
# Copyright 2016 CUBRID Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Run csql with an editable prompt for interactive terminal sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import sqlite3
import struct
import sys
import termios
import time
import tty
from typing import Callable, List, Optional, Sequence, Tuple
import unicodedata
import uuid

DEFAULT_HISTORY_LIMIT = 10_000
DEFAULT_HISTORY_NAME = ".csql_history.sqlite3"
HISTORY_BUSY_TIMEOUT_MILLISECONDS = 300
TERMINATION_SIGNALS = (signal.SIGHUP, signal.SIGTERM)

# Keep this grammar synchronized with src/executables/csql_launcher.c. It is
# needed only to avoid treating a csql option value as a wrapper option.
CSQL_LONG_OPTIONS = {
  "SA-mode",
  "CS-mode",
  "user",
  "password",
  "error-continue",
  "input-file",
  "output-file",
  "single-line",
  "command",
  "line-output",
  "read-only",
  "no-auto-commit",
  "no-pager",
  "no-single-line",
  "sysadm",
  "sysadm-rebuild-catalog",
  "write-on-standby",
  "string-width",
  "no-trigger-action",
  "plain-output",
  "skip-column-names",
  "skip-vacuum",
  "query-output",
  "delimiter",
  "enclosure",
  "loaddb-output",
  "skip-title",
  "version",
}
CSQL_LONG_OPTIONS_WITH_VALUE = {
  "user",
  "password",
  "input-file",
  "output-file",
  "command",
  "string-width",
  "delimiter",
  "enclosure",
}
CSQL_SHORT_OPTIONS_WITH_VALUE = {"u", "p", "i", "o", "c"}

RESET = "\033[0m"
PROMPT_STYLE = "\033[1;38;2;203;166;247m"
STATUS_STYLE = "\033[38;2;205;214;244;48;2;24;24;37m"
STATUS_KEY_STYLE = "\033[1;38;2;137;180;250;48;2;24;24;37m"
MEMORY_ONLY_STATUS = " MEMORY-ONLY history | entries disappear on exit | "


@dataclass(frozen=True)
class WrapperOptions:
  history_file: Path
  history_limit: int
  no_history: bool


class OptionError(ValueError):
  pass


class TerminationRequest(BaseException):

  def __init__(self, signum: int) -> None:
    super().__init__(signum)
    self.signum = signum


class HistoryMode(Enum):
  PERSISTENT = auto()
  MEMORY_ONLY = auto()
  SAVE_DISABLED = auto()


class SubmissionHistory:

  def __init__(self, path: Path, limit: int, save_disabled: bool) -> None:
    self.limit = limit
    self.mode = HistoryMode.SAVE_DISABLED if save_disabled else HistoryMode.PERSISTENT
    self.memory_entries: List[str] = []
    self.connection: Optional[sqlite3.Connection] = None
    try:
      if save_disabled:
        if not path.exists():
          return
        self.connection = sqlite3.connect(
          path.as_uri() + "?mode=ro",
          uri=True,
          timeout=HISTORY_BUSY_TIMEOUT_MILLISECONDS / 1000,
        )
      else:
        self.connection = sqlite3.connect(
          path,
          timeout=HISTORY_BUSY_TIMEOUT_MILLISECONDS / 1000,
        )
      self.connection.execute(
        "PRAGMA busy_timeout={}".format(HISTORY_BUSY_TIMEOUT_MILLISECONDS)
      )
      if not save_disabled:
        self._enable_wal()
        self.connection.execute(
          "CREATE TABLE IF NOT EXISTS submissions "
          "(id INTEGER PRIMARY KEY, command TEXT NOT NULL)"
        )
        self.connection.commit()
      self._refresh_memory()
    except sqlite3.Error as error:
      self._handle_storage_failure(error)

  def _enable_wal(self) -> None:
    assert self.connection is not None
    deadline = time.monotonic() + HISTORY_BUSY_TIMEOUT_MILLISECONDS / 1000
    while True:
      try:
        journal_mode = self.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        break
      except sqlite3.OperationalError as error:
        if "locked" not in str(error).casefold() or time.monotonic() >= deadline:
          raise
        time.sleep(0.01)
    if journal_mode.casefold() != "wal":
      raise sqlite3.OperationalError(
        "history database did not enable WAL journal mode: {}".format(journal_mode)
      )

  def save(self, text: str) -> None:
    if self.mode is HistoryMode.SAVE_DISABLED or text.startswith(" "):
      return
    if self.mode is HistoryMode.MEMORY_ONLY:
      self._remember(text)
      return
    assert self.connection is not None
    try:
      with self.connection:
        self.connection.execute("INSERT INTO submissions(command) VALUES (?)", (text,))
        self.connection.execute(
          "DELETE FROM submissions WHERE id NOT IN "
          "(SELECT id FROM submissions ORDER BY id DESC LIMIT ?)",
          (self.limit,),
        )
    except sqlite3.Error as error:
      self._handle_storage_failure(error)
    self._remember(text)

  def entries(self) -> List[str]:
    if self.connection is not None:
      try:
        self._refresh_memory()
      except sqlite3.Error as error:
        self._handle_storage_failure(error)
    entries = []
    seen = set()
    for command in reversed(self.memory_entries):
      if command not in seen:
        entries.append(command)
        seen.add(command)
    return entries

  def _refresh_memory(self) -> None:
    assert self.connection is not None
    rows = self.connection.execute(
      "SELECT command FROM submissions ORDER BY id"
    )
    self.memory_entries = [command for command, in rows]

  def _remember(self, text: str) -> None:
    self.memory_entries.append(text)
    if self.limit == 0:
      self.memory_entries = []
    elif self.limit > 0:
      self.memory_entries = self.memory_entries[-self.limit:]

  def _handle_storage_failure(self, error: sqlite3.Error) -> None:
    if self.connection is not None:
      self.connection.close()
      self.connection = None
    if self.mode is HistoryMode.SAVE_DISABLED:
      print(
        "csql-with-history: warning: persistent history unavailable ({}); "
        "history saving remains disabled".format(error),
        file=sys.stderr,
        flush=True,
      )
      return
    self.mode = HistoryMode.MEMORY_ONLY
    print(
      "csql-with-history: warning: persistent history unavailable ({}); "
      "using memory-only history; newly retained entries will disappear on exit".format(error),
      file=sys.stderr,
      flush=True,
    )

  def close(self) -> None:
    if self.connection is not None:
      self.connection.close()


class EditorAction(Enum):
  INSERT = auto()
  SUBMIT = auto()
  EOF = auto()
  INTERRUPT = auto()
  NEWLINE = auto()
  BACKSPACE = auto()
  DELETE = auto()
  LEFT = auto()
  RIGHT = auto()
  UP = auto()
  DOWN = auto()
  HOME = auto()
  END = auto()
  REDRAW = auto()
  SEARCH = auto()
  CANCEL = auto()
  IGNORE = auto()


@dataclass(frozen=True)
class KeyEvent:
  action: EditorAction
  text: str = ""


@dataclass
class HistorySearch:
  active: bool = False
  query: str = ""
  entries: List[str] = field(default_factory=list)
  matches: List[str] = field(default_factory=list)
  selected: int = 0

  def activate(self, entries: List[str]) -> None:
    self.active = True
    self.query = ""
    self.entries = entries
    self.update_matches()

  def update_matches(self) -> None:
    terms = self.query.casefold().split()
    self.matches = [
      entry for entry in self.entries
      if all(term in entry.casefold() for term in terms)
    ]
    self.selected = 0

  def handle(self, event: KeyEvent) -> Optional[str]:
    if event.action is EditorAction.CANCEL:
      self.active = False
    elif event.action is EditorAction.SUBMIT:
      if self.matches:
        self.active = False
        return self.matches[self.selected]
    elif event.action is EditorAction.UP:
      if self.matches:
        self.selected = max(0, self.selected - 1)
    elif event.action is EditorAction.DOWN:
      if self.matches:
        self.selected = min(len(self.matches) - 1, self.selected + 1)
    elif event.action is EditorAction.BACKSPACE:
      self.query = self.query[:-1]
      self.update_matches()
    elif event.action is EditorAction.INSERT:
      self.query += event.text
      self.update_matches()
    return None


class DraftEditor:

  def __init__(
    self,
    history: SubmissionHistory,
    consume_resize: Callable[[], bool],
  ) -> None:
    self.history = history
    self.consume_resize = consume_resize
    self.text = ""
    self.cursor = 0
    self.rendered_rows = 0
    self.cursor_to_bottom = 0
    self.history_entries: List[str] = []
    self.history_index: Optional[int] = None
    self.unfinished_text = ""
    self.unfinished_cursor = 0
    self.search = HistorySearch()

  def read(self) -> Optional[str]:
    previous = termios.tcgetattr(0)
    tty.setraw(0)
    try:
      self.text = ""
      self.cursor = 0
      self.history_entries = []
      self.history_index = None
      self.unfinished_text = ""
      self.unfinished_cursor = 0
      self.search = HistorySearch()
      self._render()
      while True:
        event = self._read_key()
        if event.action is EditorAction.SEARCH:
          if not self.search.active:
            self.search.activate(self.history.entries())
          self._render()
          continue
        if self.search.active:
          if event.action is EditorAction.INTERRUPT:
            self.search.active = False
            self.text = ""
            self.cursor = 0
            self.history_index = None
            self._render()
            continue
          self._handle_search(event)
          self._render()
          continue
        if event.action is EditorAction.SUBMIT:
          return self.text
        if event.action is EditorAction.EOF:
          if not self.text:
            return None
          self._delete()
        elif event.action is EditorAction.INTERRUPT:
          self.text = ""
          self.cursor = 0
        elif event.action is EditorAction.NEWLINE:
          self._insert("\n")
        elif event.action is EditorAction.BACKSPACE:
          if self.cursor:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1
        elif event.action is EditorAction.DELETE:
          self._delete()
        elif event.action is EditorAction.LEFT:
          self.cursor = max(0, self.cursor - 1)
        elif event.action is EditorAction.RIGHT:
          self.cursor = min(len(self.text), self.cursor + 1)
        elif event.action is EditorAction.UP:
          if self.text[:self.cursor].count("\n"):
            self._move_vertical(-1)
          else:
            self._browse_older()
        elif event.action is EditorAction.DOWN:
          if self.text[:self.cursor].count("\n") < self.text.count("\n"):
            self._move_vertical(1)
          else:
            self._browse_newer()
        elif event.action is EditorAction.HOME:
          self.cursor = self.text.rfind("\n", 0, self.cursor) + 1
        elif event.action is EditorAction.END:
          end = self.text.find("\n", self.cursor)
          self.cursor = len(self.text) if end < 0 else end
        elif event.action is EditorAction.INSERT:
          self._insert(event.text)
        self._render()
    finally:
      self._erase()
      termios.tcsetattr(0, termios.TCSADRAIN, previous)

  def _delete(self) -> None:
    if self.cursor < len(self.text):
      self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]

  def _insert(self, text: str) -> None:
    self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
    self.cursor += len(text)

  def _move_vertical(self, direction: int) -> None:
    lines = self.text.split("\n")
    before = self.text[:self.cursor]
    row = before.count("\n")
    column = len(before.rsplit("\n", 1)[-1])
    target = row + direction
    if target < 0 or target >= len(lines):
      return
    self.cursor = sum(len(line) + 1 for line in lines[:target]) + min(column, len(lines[target]))

  def _handle_search(self, event: KeyEvent) -> None:
    recalled = self.search.handle(event)
    if recalled is not None:
      self.text = recalled
      self.cursor = 0
      self.history_index = None

  def _browse_older(self) -> None:
    if self.history_index is None:
      self.history_entries = self.history.entries()
      if not self.history_entries:
        return
      self.unfinished_text = self.text
      self.unfinished_cursor = self.cursor
      self.history_index = 0
    elif self.history_index + 1 < len(self.history_entries):
      self.history_index += 1
    else:
      return
    self.text = self.history_entries[self.history_index]
    self.cursor = 0

  def _browse_newer(self) -> None:
    if self.history_index is None:
      return
    if self.history_index:
      self.history_index -= 1
      self.text = self.history_entries[self.history_index]
      self.cursor = len(self.text)
    else:
      self.history_index = None
      self.text = self.unfinished_text
      self.cursor = self.unfinished_cursor

  def _read_key(self) -> KeyEvent:
    while True:
      if self.consume_resize():
        return KeyEvent(EditorAction.REDRAW)
      ready, _, _ = select.select([0], [], [], 0.05)
      if ready:
        break
    first = os.read(0, 1)
    if first == b"\r":
      return KeyEvent(EditorAction.SUBMIT)
    if first == b"\n":
      return KeyEvent(EditorAction.NEWLINE)
    if first == b"\x03":
      return KeyEvent(EditorAction.INTERRUPT)
    if first == b"\x04":
      return KeyEvent(EditorAction.EOF)
    if first in (b"\x08", b"\x7f"):
      return KeyEvent(EditorAction.BACKSPACE)
    if first == b"\x09":
      return KeyEvent(EditorAction.INSERT, "\t")
    if first == b"\x0c":
      return KeyEvent(EditorAction.REDRAW)
    if first == b"\x12":
      return KeyEvent(EditorAction.SEARCH)
    if first == b"\x1b":
      return self._read_escape()
    if first < b"\x20":
      return KeyEvent(EditorAction.IGNORE)

    expected = 1
    value = first[0]
    if value & 0xE0 == 0xC0:
      expected = 2
    elif value & 0xF0 == 0xE0:
      expected = 3
    elif value & 0xF8 == 0xF0:
      expected = 4
    data = bytearray(first)
    while len(data) < expected:
      data.extend(os.read(0, expected - len(data)))
    return KeyEvent(EditorAction.INSERT, data.decode("utf-8", errors="replace"))

  def _read_escape(self) -> KeyEvent:
    ready, _, _ = select.select([0], [], [], 0.05)
    if not ready:
      return KeyEvent(EditorAction.CANCEL)
    second = os.read(0, 1)
    if second in (b"\r", b"\n"):
      return KeyEvent(EditorAction.NEWLINE)
    if second != b"[":
      return KeyEvent(EditorAction.INSERT, second.decode("utf-8", errors="ignore"))

    sequence = bytearray()
    while len(sequence) < 8:
      ready, _, _ = select.select([0], [], [], 0.01)
      if not ready:
        break
      sequence.extend(os.read(0, 1))
      if sequence[-1:] in b"~ABCDHF":
        break
    action = {
      b"A": EditorAction.UP,
      b"B": EditorAction.DOWN,
      b"C": EditorAction.RIGHT,
      b"D": EditorAction.LEFT,
      b"H": EditorAction.HOME,
      b"F": EditorAction.END,
      b"1~": EditorAction.HOME,
      b"3~": EditorAction.DELETE,
      b"4~": EditorAction.END,
      b"7~": EditorAction.HOME,
      b"8~": EditorAction.END,
    }.get(bytes(sequence), EditorAction.IGNORE)
    return KeyEvent(action)

  def _render(self) -> None:
    self._erase()
    lines = self.text.split("\n")
    before = self.text[:self.cursor]
    cursor_row = before.count("\n")
    cursor_offset = len(before.rsplit("\n", 1)[-1])
    terminal_size = shutil.get_terminal_size((80, 24))
    columns = max(2, terminal_size.columns)
    content_width = columns - 1

    visual_lines = []
    cursor_visual_row = 0
    cursor_column = 0
    for row, line in enumerate(lines):
      wrapped, positions = self._wrap_line(line, content_width)
      if row < cursor_row:
        cursor_visual_row += len(wrapped)
      elif row == cursor_row:
        local_row, cursor_column = positions[cursor_offset]
        cursor_visual_row += local_row
      visual_lines.extend(wrapped)

    reserved_rows = 5 if self.search.active else 2
    draft_rows = max(1, terminal_size.lines - reserved_rows)
    first_visual_row = min(
      max(0, cursor_visual_row - draft_rows // 2),
      max(0, len(visual_lines) - draft_rows),
    )
    visible_visual_lines = visual_lines[first_visual_row:first_visual_row + draft_rows]
    cursor_visual_row -= first_visual_row

    prompt = self._truncate("csql-with-history>", content_width)

    output = [PROMPT_STYLE, prompt, RESET, "\033[K\r\n"]
    for line in visible_visual_lines:
      output.extend((line, "\033[K\r\n"))
    extra_rows = 0
    if self.search.active:
      output.extend((PROMPT_STYLE, "History search:", RESET, "\033[K\r\n"))
      output.extend((self._truncate(self.search.query, content_width), "\033[K\r\n"))
      if self.search.matches:
        result_rows = max(1, min(6, terminal_size.lines - len(visible_visual_lines) - 4))
        start = max(0, self.search.selected - result_rows + 1)
        visible_matches = self.search.matches[start:start + result_rows]
        for index, match in enumerate(visible_matches, start):
          marker = "> " if index == self.search.selected else "  "
          display = marker + match.replace("\n", " ↵ ")
          output.extend((self._truncate(display, content_width), "\033[K\r\n"))
      else:
        visible_matches = []
        output.extend(("(no matches)", "\033[K\r\n"))
      output.extend((self._search_status(content_width), RESET, "\033[K"))
      extra_rows = 2 + max(1, len(visible_matches))
      cursor_visual_row = len(visible_visual_lines) + 1
      cursor_column = min(self._text_width(self.search.query), content_width)
    else:
      output.extend((self._status(len(lines), content_width), RESET, "\033[K"))
    self.cursor_to_bottom = len(visible_visual_lines) + extra_rows - cursor_visual_row
    if self.cursor_to_bottom:
      output.append("\033[{}A".format(self.cursor_to_bottom))
    output.extend(("\r", "\033[{}C".format(cursor_column) if cursor_column else ""))
    os.write(1, "".join(output).encode("utf-8"))
    self.rendered_rows = len(visible_visual_lines) + extra_rows + 2

  @classmethod
  def _wrap_line(cls, line: str, width: int) -> Tuple[List[str], List[Tuple[int, int]]]:
    rows = [""]
    positions = [(0, 0)]
    row = 0
    column = 0
    for character in line:
      visible = character
      character_width = cls._character_width(character, column)
      if character == "\t":
        visible = " " * character_width
      if character_width > width:
        visible = "?"
        character_width = 1
      if character_width and column and column + character_width > width:
        rows.append("")
        row += 1
        column = 0
        if character == "\t":
          character_width = cls._character_width(character, column)
          visible = " " * character_width
      rows[row] += visible
      column += character_width
      positions.append((row, column))
    return rows, positions

  @staticmethod
  def _character_width(character: str, column: int) -> int:
    if character == "\t":
      return 8 - column % 8
    if unicodedata.combining(character):
      return 0
    if unicodedata.category(character).startswith("C"):
      return 0
    return 2 if unicodedata.east_asian_width(character) in ("W", "F") else 1

  @classmethod
  def _truncate(cls, text: str, width: int) -> str:
    result = []
    column = 0
    for character in text:
      character_width = cls._character_width(character, column)
      if column + character_width > width:
        break
      result.append(character)
      column += character_width
    return "".join(result)

  @classmethod
  def _text_width(cls, text: str) -> int:
    column = 0
    for character in text:
      column += cls._character_width(character, column)
    return column

  def _search_status(self, width: int) -> str:
    if self.history.mode is HistoryMode.MEMORY_ONLY:
      text = MEMORY_ONLY_STATUS + "Enter recall | Esc cancel | Up/Down select "
    else:
      text = " History | Enter recall | Esc cancel | Up/Down select "
    return STATUS_STYLE + text[:width].ljust(width)

  def _status(self, line_count: int, width: int) -> str:
    segments = []
    if self.history.mode is HistoryMode.MEMORY_ONLY:
      segments.append((STATUS_STYLE, MEMORY_ONLY_STATUS))
    segments.extend((
      (STATUS_STYLE, " SQL  draft {} lines | ".format(line_count)),
      (STATUS_KEY_STYLE, "Enter"),
      (STATUS_STYLE, " submit "),
      (STATUS_KEY_STYLE, "Ctrl+J"),
      (STATUS_STYLE, " newline "),
      (STATUS_KEY_STYLE, "Alt+Enter"),
      (STATUS_STYLE, " newline "),
      (STATUS_KEY_STYLE, "Ctrl+R"),
      (STATUS_STYLE, " search "),
      (STATUS_KEY_STYLE, "Ctrl+C"),
      (STATUS_STYLE, " clear "),
    ))
    remaining = width
    output = []
    for style, text in segments:
      if not remaining:
        break
      visible = text[:remaining]
      output.extend((style, visible))
      remaining -= len(visible)
    if remaining:
      output.extend((STATUS_STYLE, " " * remaining))
    return "".join(output)

  def _erase(self) -> None:
    if not self.rendered_rows:
      return
    output = []
    if self.cursor_to_bottom:
      output.append("\033[{}B".format(self.cursor_to_bottom))
    output.append("\r")
    for row in range(self.rendered_rows):
      output.append("\033[2K")
      if row + 1 < self.rendered_rows:
        output.append("\033[1A")
    output.append("\r")
    os.write(1, "".join(output).encode("ascii"))
    self.rendered_rows = 0
    self.cursor_to_bottom = 0


class CsqlTerminal:

  def __init__(
    self,
    executable: str,
    arguments: Sequence[str],
    child_signal_mask: set[signal.Signals],
  ) -> None:
    self.prompt_base = "__CSQL_WITH_HISTORY_{}__".format(uuid.uuid4().hex)
    self.prompt = (self.prompt_base + "> ").encode("ascii")
    self.pending = bytearray()
    self.prompt_candidate_since: Optional[float] = None
    self.wait_status: Optional[int] = None
    self.baseline_terminal_children: Optional[set[int]] = None
    self.resize_pending = False
    process_id, terminal_fd = pty.fork()
    if process_id == 0:
      signal.pthread_sigmask(signal.SIG_SETMASK, child_signal_mask)
      environment = os.environ.copy()
      environment["CUBRID_CSQL_PROMPT"] = self.prompt_base
      os.execve(executable, ["csql", *arguments], environment)
    self.process_id = process_id
    self.terminal_fd = terminal_fd
    self.previous_resize_handler = signal.signal(signal.SIGWINCH, self._handle_resize)
    self.previous_termination_handlers = {
      signum: signal.signal(signum, self._handle_termination)
      for signum in TERMINATION_SIGNALS
    }
    self.resize()

  def resize(self) -> None:
    size = os.get_terminal_size(0)
    fcntl.ioctl(
      self.terminal_fd,
      termios.TIOCSWINSZ,
      struct.pack("HHHH", size.lines, size.columns, 0, 0),
    )

  def consume_resize(self) -> bool:
    pending = self.resize_pending
    self.resize_pending = False
    return pending

  def _handle_resize(self, _signum: int, _frame: object) -> None:
    self.resize()
    self.resize_pending = True

  def _handle_termination(self, signum: int, _frame: object) -> None:
    self._signal_process_group(signum)
    raise TerminationRequest(signum)

  def relay_until_input(self) -> bool:
    outer_attributes = termios.tcgetattr(0)
    tty.setraw(0)
    try:
      while True:
        child_attributes = self._child_terminal_attributes()
        terminal_children = self._terminal_child_processes()
        terminal_program_active = (
          self.baseline_terminal_children is not None
          and bool(terminal_children - self.baseline_terminal_children)
        )
        at_input_boundary = (
          not terminal_program_active and self._at_input_boundary(child_attributes)
        )
        if at_input_boundary:
          position = self.pending.rfind(self.prompt)
          if position >= 0:
            self._write(bytes(self.pending[:position]))
            self.pending = self.pending[position + len(self.prompt):]
            self.prompt_candidate_since = None
            if self.baseline_terminal_children is None:
              self.baseline_terminal_children = terminal_children
            return True

        if terminal_program_active:
          self._write(bytes(self.pending))
          self.pending.clear()
          self.prompt_candidate_since = None
        else:
          self._flush_safe_prefix(at_input_boundary)
        ready, _, _ = select.select([self.terminal_fd, 0], [], [], 0.02)
        if self.terminal_fd in ready:
          try:
            data = os.read(self.terminal_fd, 65536)
          except OSError as error:
            if error.errno != errno.EIO:
              raise
            data = b""
          if not data:
            self._write(bytes(self.pending))
            self.pending.clear()
            self._reap(block=True)
            return False
          self.pending.extend(data)
        if 0 in ready:
          data = os.read(0, 65536)
          if data:
            os.write(self.terminal_fd, data)
        if not ready and self._reap(block=False):
          self._write(bytes(self.pending))
          self.pending.clear()
          return False
    finally:
      termios.tcsetattr(0, termios.TCSANOW, outer_attributes)

  def send_submission(self, text: str) -> bool:
    for line in text.split("\n"):
      os.write(self.terminal_fd, line.encode("utf-8") + b"\r")
      if not self.relay_until_input():
        return False
    return True

  def send_eof(self) -> bool:
    os.write(self.terminal_fd, b"\x04")
    return self.relay_until_input()

  def returncode(self) -> int:
    self._reap(block=True)
    assert self.wait_status is not None
    if os.WIFEXITED(self.wait_status):
      return os.WEXITSTATUS(self.wait_status)
    return 128 + os.WTERMSIG(self.wait_status)

  def close(self) -> None:
    signal.signal(signal.SIGWINCH, self.previous_resize_handler)
    for signum, previous_handler in self.previous_termination_handlers.items():
      signal.signal(signum, previous_handler)
    if self.wait_status is None:
      self._signal_process_group(signal.SIGTERM)
      deadline = time.monotonic() + 1.0
      while self.wait_status is None and time.monotonic() < deadline:
        self._reap(block=False)
        if self.wait_status is None:
          time.sleep(0.01)
      if self.wait_status is None:
        self._signal_process_group(signal.SIGKILL)
        self._reap(block=True)
    os.close(self.terminal_fd)

  def _signal_process_group(self, signum: int) -> None:
    try:
      os.killpg(self.process_id, signum)
    except ProcessLookupError:
      pass

  def _child_terminal_attributes(self) -> Optional[List[object]]:
    try:
      return termios.tcgetattr(self.terminal_fd)
    except termios.error:
      return None

  @staticmethod
  def _at_input_boundary(attributes: Optional[List[object]]) -> bool:
    if attributes is None:
      return False
    return not (attributes[3] & termios.ICANON) and not (attributes[3] & termios.ECHO)

  def _terminal_child_processes(self) -> set[int]:
    children = Path(
      "/proc/{}/task/{}/children".format(self.process_id, self.process_id)
    )
    try:
      child_ids = children.read_text(encoding="ascii").split()
      csql_terminal = os.readlink("/proc/{}/fd/0".format(self.process_id))
    except OSError:
      return set()
    terminal_children = set()
    for child_id_text in child_ids:
      try:
        child_id = int(child_id_text)
        if os.readlink("/proc/{}/fd/0".format(child_id)) == csql_terminal:
          terminal_children.add(child_id)
      except (OSError, ValueError):
        continue
    return terminal_children

  def _flush_safe_prefix(self, at_input_boundary: bool) -> None:
    if not at_input_boundary and self.pending.endswith(self.prompt):
      now = time.monotonic()
      if self.prompt_candidate_since is None:
        self.prompt_candidate_since = now
      if now - self.prompt_candidate_since < 0.1:
        return
    else:
      self.prompt_candidate_since = None

    keep = 0
    maximum = min(len(self.pending), len(self.prompt) - 1)
    for length in range(1, maximum + 1):
      if self.pending.endswith(self.prompt[:length]):
        keep = length
    if keep:
      output = bytes(self.pending[:-keep])
      self.pending = self.pending[-keep:]
    else:
      output = bytes(self.pending)
      self.pending.clear()
    self.prompt_candidate_since = None
    self._write(output)

  def _reap(self, block: bool) -> bool:
    if self.wait_status is not None:
      return True
    waited_process, status = os.waitpid(self.process_id, 0 if block else os.WNOHANG)
    if waited_process == self.process_id:
      self.wait_status = status
      return True
    return False

  @staticmethod
  def _write(data: bytes) -> None:
    if data:
      os.write(1, data)


def _required_value(arguments: Sequence[str], index: int, option: str) -> Tuple[str, int]:
  if index + 1 >= len(arguments):
    raise OptionError("option {} requires a value".format(option))
  return arguments[index + 1], index + 2


def _resolved_csql_long_option(argument: str) -> Optional[str]:
  name = argument[2:].split("=", 1)[0]
  if name in CSQL_LONG_OPTIONS:
    return name
  matches = [option for option in CSQL_LONG_OPTIONS if option.startswith(name)]
  return matches[0] if len(matches) == 1 else None


def _csql_option_consumes_next(argument: str) -> bool:
  if argument.startswith("--"):
    option = _resolved_csql_long_option(argument)
    return option in CSQL_LONG_OPTIONS_WITH_VALUE and "=" not in argument
  if not argument.startswith("-") or argument == "-":
    return False

  cluster = argument[1:]
  for position, option in enumerate(cluster):
    if option in CSQL_SHORT_OPTIONS_WITH_VALUE:
      return position == len(cluster) - 1
  return False


def parse_options(arguments: Sequence[str], launch_directory: Path) -> Tuple[WrapperOptions, List[str]]:
  history_file = launch_directory / DEFAULT_HISTORY_NAME
  history_limit = DEFAULT_HISTORY_LIMIT
  no_history = False
  forwarded: List[str] = []
  index = 0

  while index < len(arguments):
    argument = arguments[index]
    if argument == "--":
      forwarded.extend(arguments[index:])
      break

    if argument == "--no-history":
      no_history = True
      index += 1
      continue

    if argument == "--history-file":
      value, index = _required_value(arguments, index, argument)
      history_file = Path(os.path.abspath(os.path.join(str(launch_directory), value)))
      continue
    if argument.startswith("--history-file="):
      value = argument.split("=", 1)[1]
      history_file = Path(os.path.abspath(os.path.join(str(launch_directory), value)))
      index += 1
      continue

    if argument == "--history-limit":
      value, index = _required_value(arguments, index, argument)
      history_limit = _integer_limit(value)
      continue
    if argument.startswith("--history-limit="):
      history_limit = _integer_limit(argument.split("=", 1)[1])
      index += 1
      continue

    forwarded.append(argument)
    if _csql_option_consumes_next(argument) and index + 1 < len(arguments):
      forwarded.append(arguments[index + 1])
      index += 2
    else:
      index += 1

  options = WrapperOptions(history_file.resolve(strict=False), history_limit, no_history)
  return options, forwarded


def _integer_limit(value: str) -> int:
  try:
    return int(value, 10)
  except ValueError as error:
    raise OptionError("--history-limit must be an integer") from error


def find_csql() -> Optional[str]:
  # Follow the selected CUBRID environment, including csql.sh's verified client.
  return shutil.which("csql")


def is_interactive(arguments: Sequence[str]) -> bool:
  if not os.isatty(0) or not os.isatty(1):
    return False

  index = 0
  while index < len(arguments):
    argument = arguments[index]
    if argument == "--":
      break
    if argument.startswith("--"):
      option = _resolved_csql_long_option(argument)
      if option in ("input-file", "command"):
        return False
    elif argument.startswith("-") and argument != "-":
      for option in argument[1:]:
        if option in ("i", "c"):
          return False
        if option in CSQL_SHORT_OPTIONS_WITH_VALUE:
          break
    if _csql_option_consumes_next(argument):
      index += 2
    else:
      index += 1
  return True


def run_interactive(executable: str, arguments: Sequence[str], options: WrapperOptions) -> int:
  previous_signal_mask = signal.pthread_sigmask(signal.SIG_BLOCK, TERMINATION_SIGNALS)
  terminal: Optional[CsqlTerminal] = None
  history: Optional[SubmissionHistory] = None
  signal_mask_restored = False
  try:
    terminal = CsqlTerminal(executable, arguments, previous_signal_mask)
    signal_mask_restored = True
    signal.pthread_sigmask(signal.SIG_SETMASK, previous_signal_mask)
    if not terminal.relay_until_input():
      return terminal.returncode()

    history = SubmissionHistory(options.history_file, options.history_limit, options.no_history)
    editor = DraftEditor(history, terminal.consume_resize)
    while True:
      submission = editor.read()
      if submission is None:
        if not terminal.send_eof():
          break
      else:
        history.save(submission)
        if not terminal.send_submission(submission):
          break
    return terminal.returncode()
  except TerminationRequest as request:
    return 128 + request.signum
  finally:
    if not signal_mask_restored:
      signal.pthread_sigmask(signal.SIG_SETMASK, previous_signal_mask)
    if history is not None:
      history.close()
    if terminal is not None:
      terminal.close()


def main(arguments: Optional[Sequence[str]] = None) -> int:
  if arguments is None:
    arguments = sys.argv[1:]
  if list(arguments) == ["--help"]:
    print("""Usage: csql-with-history [WRAPPER OPTIONS] [CSQL OPTIONS] DATABASE

Editable multiline input with persistent searchable history for CUBRID csql.
Uses the csql executable selected by PATH in your active CUBRID environment.

Wrapper options:
  --history-file PATH   SQLite history file (default: ./.csql_history.sqlite3)
  --history-limit N     Retain the latest N submissions (default: 10000)
  --no-history          Recall existing history without saving new submissions
  --help               Show this help without requiring CUBRID
  --version            Show the installed wrapper version
  --                   Forward remaining arguments to csql unchanged

Keys: Up/Down recall, Ctrl+R search, Ctrl+J newline, Enter submit.
Other arguments pass through to csql. Run csql directly for its native usage.""")
    return 0
  if list(arguments) == ["--version"]:
    from importlib.metadata import version
    print("csql-with-history " + version("csql-with-history"))
    return 0
  launch_directory = Path.cwd()
  try:
    options, csql_arguments = parse_options(arguments, launch_directory)
  except OptionError as error:
    print("csql-with-history: {}".format(error), file=sys.stderr)
    return 2

  executable = find_csql()
  if executable is None:
    print("csql-with-history: installed csql executable not found", file=sys.stderr)
    return 127

  if is_interactive(csql_arguments):
    return run_interactive(executable, csql_arguments, options)

  try:
    os.execv(executable, ["csql", *csql_arguments])
  except OSError as error:
    print("csql-with-history: cannot execute csql: {}".format(error), file=sys.stderr)
    return 126
  return 126


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))

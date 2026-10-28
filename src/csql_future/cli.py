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
import shlex
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import tempfile
import termios
import time
import tty
from typing import Callable, List, Optional, Sequence, Tuple
import unicodedata
import uuid

from .completion import CompletionMenu, suggest
from .metadata import CatalogCache, Connection

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
HELP_KEY_STYLE = "\033[1;38;2;137;180;250m"
HISTORY_TIME_STYLE = "\033[38;2;166;173;200m"
MEMORY_ONLY_STATUS = " MEMORY-ONLY history | entries disappear on exit | "


@dataclass(frozen=True)
class WrapperOptions:
  history_file: Path
  history_limit: int
  no_history: bool
  completion: bool = True


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


@dataclass(frozen=True)
class HistoryEntry:
  command: str
  submitted_at: Optional[float] = None


def format_history_age(submitted_at: Optional[float], now: Optional[float] = None) -> str:
  if submitted_at is None:
    return "time unknown"
  elapsed = max(0, int((time.time() if now is None else now) - submitted_at))
  if elapsed < 5:
    return "just now"
  for seconds, singular, plural in (
    (31536000, "year", "years"), (2592000, "month", "months"),
    (86400, "day", "days"), (3600, "hr", "hr"),
    (60, "min", "min"), (1, "sec", "sec"),
  ):
    count = elapsed // seconds
    if count:
      return "{} {} ago".format(count, singular if count == 1 else plural)
  return "just now"


class SubmissionHistory:

  def __init__(self, path: Path, limit: int, save_disabled: bool) -> None:
    self.limit = limit
    self.mode = HistoryMode.SAVE_DISABLED if save_disabled else HistoryMode.PERSISTENT
    self.memory_entries: List[HistoryEntry] = []
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
        # Serialize legacy migration with other writers opening the same store.
        with self.connection:
          self.connection.execute("BEGIN IMMEDIATE")
          self.connection.execute(
            "CREATE TABLE IF NOT EXISTS submissions "
            "(id INTEGER PRIMARY KEY, command TEXT NOT NULL, submitted_at REAL)"
          )
          if "submitted_at" not in self._columns():
            self.connection.execute("ALTER TABLE submissions ADD COLUMN submitted_at REAL")
          self.connection.execute(
            "DELETE FROM submissions WHERE id NOT IN "
            "(SELECT MAX(id) FROM submissions GROUP BY command)"
          )
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
    entry = HistoryEntry(text, time.time())
    if self.mode is HistoryMode.MEMORY_ONLY:
      self._remember(entry)
      return
    assert self.connection is not None
    try:
      with self.connection:
        self.connection.execute("DELETE FROM submissions WHERE command=?", (entry.command,))
        self.connection.execute(
          "INSERT INTO submissions(command, submitted_at) VALUES (?, ?)",
          (entry.command, entry.submitted_at),
        )
        self.connection.execute(
          "DELETE FROM submissions WHERE id NOT IN "
          "(SELECT id FROM submissions ORDER BY id DESC LIMIT ?)",
          (self.limit,),
        )
    except sqlite3.Error as error:
      self._handle_storage_failure(error)
    self._remember(entry)

  def entries(self) -> List[str]:
    return [entry.command for entry in self.records()]

  def records(self) -> List[HistoryEntry]:
    if self.connection is not None:
      try:
        self._refresh_memory()
      except sqlite3.Error as error:
        self._handle_storage_failure(error)
    entries = []
    seen = set()
    for entry in reversed(self.memory_entries):
      if entry.command not in seen:
        entries.append(entry)
        seen.add(entry.command)
    return entries

  def _columns(self) -> List[str]:
    assert self.connection is not None
    return [row[1] for row in self.connection.execute("PRAGMA table_info(submissions)")]

  def _refresh_memory(self) -> None:
    assert self.connection is not None
    # --no-history must also read older stores without changing their schema.
    timestamp_column = "submitted_at" if "submitted_at" in self._columns() else "NULL"
    rows = self.connection.execute(
      "SELECT command, {} FROM submissions ORDER BY id".format(timestamp_column)
    )
    self.memory_entries = [HistoryEntry(command, submitted_at) for command, submitted_at in rows]

  def _remember(self, entry: HistoryEntry) -> None:
    self.memory_entries = [old for old in self.memory_entries if old.command != entry.command]
    self.memory_entries.append(entry)
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
        "csql-future: warning: persistent history unavailable ({}); "
        "history saving remains disabled".format(error),
        file=sys.stderr,
        flush=True,
      )
      return
    self.mode = HistoryMode.MEMORY_ONLY
    print(
      "csql-future: warning: persistent history unavailable ({}); "
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
  QUIT = auto()
  INTERRUPT = auto()
  NEWLINE = auto()
  BACKSPACE = auto()
  DELETE = auto()
  LEFT = auto()
  RIGHT = auto()
  UP = auto()
  DOWN = auto()
  PAGE_UP = auto()
  PAGE_DOWN = auto()
  HOME = auto()
  END = auto()
  KILL_WORD = auto()
  KILL_START = auto()
  KILL_END = auto()
  YANK = auto()
  TRANSPOSE = auto()
  HISTORY_OLDER = auto()
  HISTORY_NEWER = auto()
  REDRAW = auto()
  SEARCH = auto()
  HELP = auto()
  EXTERNAL_EDITOR = auto()
  COMPLETE = auto()
  CANCEL = auto()
  IGNORE = auto()


@dataclass(frozen=True)
class KeyEvent:
  action: EditorAction
  text: str = ""


@dataclass
class TextBuffer:
  text: str = ""
  cursor: int = 0
  killed: str = ""

  def insert(self, text: str) -> None:
    self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
    self.cursor += len(text)

  def handle(self, event: KeyEvent) -> None:
    action = event.action
    if action is EditorAction.INSERT:
      self.insert(event.text)
    elif action is EditorAction.NEWLINE:
      self.insert("\n")
    elif action is EditorAction.BACKSPACE:
      if self.cursor:
        self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
        self.cursor -= 1
    elif action in (EditorAction.DELETE, EditorAction.EOF):
      self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
    elif action is EditorAction.LEFT:
      self.cursor = max(0, self.cursor - 1)
    elif action is EditorAction.RIGHT:
      self.cursor = min(len(self.text), self.cursor + 1)
    elif action is EditorAction.HOME:
      self.cursor = self.text.rfind("\n", 0, self.cursor) + 1
    elif action is EditorAction.END:
      end = self.text.find("\n", self.cursor)
      self.cursor = len(self.text) if end < 0 else end
    elif action is EditorAction.KILL_WORD:
      start = self.cursor
      while start and self.text[start - 1].isspace():
        start -= 1
      while start and not self.text[start - 1].isspace():
        start -= 1
      self._kill(start, self.cursor)
    elif action is EditorAction.KILL_START:
      self._kill(self.text.rfind("\n", 0, self.cursor) + 1, self.cursor)
    elif action is EditorAction.KILL_END:
      end = self.text.find("\n", self.cursor)
      if end == self.cursor:
        end += 1
      self._kill(self.cursor, len(self.text) if end < 0 else end)
    elif action is EditorAction.YANK:
      self.insert(self.killed)
    elif action is EditorAction.TRANSPOSE and self.cursor:
      end = min(len(self.text), self.cursor + 1)
      if end >= 2 and "\n" not in self.text[end - 2:end]:
        self.text = self.text[:end - 2] + self.text[end - 1] + self.text[end - 2] + self.text[end:]
        self.cursor = end

  def _kill(self, start: int, end: int) -> None:
    if start < end:
      self.killed = self.text[start:end]
      self.text = self.text[:start] + self.text[end:]
      self.cursor = start


@dataclass
class HistorySearch:
  active: bool = False
  query: TextBuffer = field(default_factory=TextBuffer)
  entries: List[HistoryEntry] = field(default_factory=list)
  matches: List[HistoryEntry] = field(default_factory=list)
  selected: int = 0

  def activate(self, entries: List[HistoryEntry]) -> None:
    self.active = True
    self.query = TextBuffer()
    self.entries = entries
    self.update_matches()

  def update_matches(self) -> None:
    terms = self.query.text.casefold().split()
    self.matches = [
      entry for entry in self.entries
      if all(term in entry.command.casefold() for term in terms)
    ]
    self.selected = 0

  def handle(self, event: KeyEvent) -> Optional[str]:
    if event.action is EditorAction.CANCEL:
      self.active = False
    elif event.action is EditorAction.SUBMIT:
      if self.matches:
        self.active = False
        return self.matches[self.selected].command
    elif event.action in (EditorAction.UP, EditorAction.HISTORY_OLDER):
      if self.matches:
        self.selected = max(0, self.selected - 1)
    elif event.action in (EditorAction.DOWN, EditorAction.HISTORY_NEWER):
      if self.matches:
        self.selected = min(len(self.matches) - 1, self.selected + 1)
    elif event.action is not EditorAction.NEWLINE:
      previous = self.query.text
      self.query.handle(event)
      if self.query.text != previous:
        self.update_matches()
    return None


class DraftEditor:

  INPUT_SHORTCUTS = (
    "Essential:",
    "Ctrl+R: Search query history (enters history search mode)",
    "Ctrl+Q: quit, discarding the draft",
    "Draft:",
    "Tab: complete SQL, session commands, or database names",
    "Enter: submit draft",
    "Ctrl+Enter / Ctrl+J: insert newline",
    "Ctrl+X Ctrl+E: open draft in $VISUAL/$EDITOR",
    "Ctrl+C: clear draft",
    "Ctrl+D: quit when the draft is empty",
    "History navigation:",
    "Ctrl+P / Ctrl+N: older/newer history",
    "Up/Down: draft lines, then history",
    "Help:",
    "?: shortcuts on an empty draft; F1: anytime",
  )
  SEARCH_SHORTCUTS = (
    "Search and recall:",
    "Type: filter history (all terms, ignore case)",
    "Enter: recall for editing, without executing",
    "Ctrl+N / Down: select next result",
    "Ctrl+P / Up: select previous result",
    "Leave search:",
    "Esc: return to Input mode, restoring the draft",
    "Ctrl+C: return to Input mode, clearing the draft",
    "Ctrl+Q: quit, discarding the draft",
    "Help:",
    "?: shortcuts on an empty query; F1: anytime",
  )
  COMPLETION_SHORTCUTS = (
    "Type or delete text to filter candidates",
    "Select and accept:",
    "Ctrl+N / Down / Tab: select next candidate",
    "Ctrl+P / Up: select previous candidate",
    "Enter: accept without executing SQL",
    "Esc: close completion, preserving the draft",
    "Other actions:",
    "Ctrl+R: close completion and search history",
    "Ctrl+X Ctrl+E: close completion and edit the draft",
    "Ctrl+Q: quit, discarding the draft",
    "F1: completion shortcuts",
  )
  EDITING_SHORTCUTS = (
    "Ctrl+A / Ctrl+E: line start/end",
    "Ctrl+B / Ctrl+F: character left/right",
    "Backspace / Ctrl+H: delete left",
    "Delete / Ctrl+D: delete at cursor",
    "Ctrl+W: cut previous word",
    "Ctrl+U / Ctrl+K: cut to line start/end",
    "Ctrl+Y: restore last cut",
    "Ctrl+T: swap adjacent characters",
    "Ctrl+L: redraw",
  )

  def __init__(
    self,
    history: SubmissionHistory,
    consume_resize: Callable[[], bool],
    catalog: Optional[CatalogCache] = None,
  ) -> None:
    self.history = history
    self.consume_resize = consume_resize
    self.catalog = catalog
    self.catalog_revision = -1
    self.draft = TextBuffer()
    self.rendered_rows = 0
    self.cursor_to_bottom = 0
    self.rendered_lines: List[str] = []
    self.rendered_columns = 0
    self.rendered_cursor_column = 0
    self.history_entries: List[str] = []
    self.history_index: Optional[int] = None
    self.unfinished_text = ""
    self.unfinished_cursor = 0
    self.search = HistorySearch()
    self.completion = CompletionMenu()
    self.show_help = False
    self.help_scroll = 0
    self.help_page_rows = 1
    self.help_max_scroll = 0
    self.editor_prefix = False

  def read(self) -> Optional[str]:
    previous = termios.tcgetattr(0)
    tty.setraw(0)
    try:
      self.draft.text = ""
      self.draft.cursor = 0
      self.history_entries = []
      self.history_index = None
      self.unfinished_text = ""
      self.unfinished_cursor = 0
      self.search = HistorySearch()
      self.completion = CompletionMenu()
      self.show_help = False
      self.help_scroll = 0
      self.editor_prefix = False
      self._render()
      while True:
        event = self._read_key()
        if event.action is EditorAction.QUIT:
          return None
        if self.show_help:
          if event.action in (
            EditorAction.CANCEL, EditorAction.SUBMIT, EditorAction.INTERRUPT, EditorAction.HELP,
          ) or event.text == "?":
            self.show_help = False
          elif event.action in (EditorAction.UP, EditorAction.HISTORY_OLDER):
            self.help_scroll = max(0, self.help_scroll - 1)
          elif event.action in (EditorAction.DOWN, EditorAction.HISTORY_NEWER):
            self.help_scroll += 1
          elif event.action is EditorAction.PAGE_UP:
            self.help_scroll = max(0, self.help_scroll - self.help_page_rows)
          elif event.action is EditorAction.PAGE_DOWN:
            self.help_scroll += self.help_page_rows
          elif event.action is EditorAction.HOME:
            self.help_scroll = 0
          elif event.action is EditorAction.END:
            self.help_scroll = self.help_max_scroll
          self._render(force=event.action is EditorAction.REDRAW)
          continue
        active_buffer = self.search.query if self.search.active else self.draft
        if event.action is EditorAction.HELP or (event.text == "?" and not active_buffer.text):
          self.show_help = True
          self.help_scroll = 0
          self._render()
          continue
        if event.action is EditorAction.SEARCH:
          self.completion.active = False
          if not self.search.active:
            self.search.activate(self.history.records())
          self._render()
          continue
        if self.completion.active:
          if event.action in (EditorAction.DOWN, EditorAction.HISTORY_NEWER, EditorAction.COMPLETE):
            self.completion.move(1)
          elif event.action in (EditorAction.UP, EditorAction.HISTORY_OLDER):
            self.completion.move(-1)
          elif event.action is EditorAction.SUBMIT:
            if self.completion.suggestions.candidates:
              self.draft.text, self.draft.cursor = self.completion.accept()
              self.history_index = None
          elif event.action is EditorAction.CANCEL:
            self.completion.active = False
          elif event.action is EditorAction.EXTERNAL_EDITOR:
            self.completion.active = False
            self._edit_external(previous)
            self._render(force=True)
            continue
          elif event.action is EditorAction.INTERRUPT:
            self.completion.active = False
            self.draft.text = ""
            self.draft.cursor = 0
          elif event.action is not EditorAction.REDRAW:
            before = (self.draft.text, self.draft.cursor)
            self.draft.handle(event)
            if (self.draft.text, self.draft.cursor) != before:
              self._refresh_completion()
          self._render(force=event.action is EditorAction.REDRAW)
          continue
        if self.search.active:
          if event.action is EditorAction.INTERRUPT:
            self.search.active = False
            self.draft.text = ""
            self.draft.cursor = 0
            self.history_index = None
            self._render()
            continue
          self._handle_search(event)
          self._render(force=event.action is EditorAction.REDRAW)
          continue
        if event.action is EditorAction.EXTERNAL_EDITOR:
          self._edit_external(previous)
          self._render(force=True)
          continue
        if event.action is EditorAction.SUBMIT:
          return self.draft.text
        if event.action is EditorAction.COMPLETE:
          line_prefix = self.draft.text[:self.draft.cursor].rsplit("\n", 1)[-1]
          if not line_prefix.strip():
            self.draft.insert("\t")
          elif self.catalog is None:
            self.draft.insert("\t")
          else:
            self.catalog.request()
            schema, message, self.catalog_revision = self.catalog.snapshot()
            suggestions = suggest(self.draft.text, self.draft.cursor, schema, message)
            if suggestions.allowed:
              self.completion.open(self.draft.text, self.draft.cursor, suggestions)
            else:
              self.draft.insert("\t")
          self._render()
          continue
        if event.action is EditorAction.EOF:
          if not self.draft.text:
            return None
        if event.action is EditorAction.INTERRUPT:
          self.draft.text = ""
          self.draft.cursor = 0
        elif event.action is EditorAction.UP:
          if self.draft.text[:self.draft.cursor].count("\n"):
            self._move_vertical(-1)
          else:
            self._browse_older()
        elif event.action is EditorAction.DOWN:
          if self.draft.text[:self.draft.cursor].count("\n") < self.draft.text.count("\n"):
            self._move_vertical(1)
          else:
            self._browse_newer()
        elif event.action is EditorAction.HISTORY_OLDER:
          self._browse_older()
        elif event.action is EditorAction.HISTORY_NEWER:
          self._browse_newer()
        else:
          self.draft.handle(event)
        self._render(force=event.action is EditorAction.REDRAW)
    finally:
      self._erase()
      termios.tcsetattr(0, termios.TCSADRAIN, previous)

  def _edit_external(self, terminal_attributes: List[object]) -> None:
    self._erase()
    termios.tcsetattr(0, termios.TCSADRAIN, terminal_attributes)
    try:
      command = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
      if not command:
        raise ValueError("the editor command is empty")
      with tempfile.TemporaryDirectory(prefix="csql-draft-") as directory:
        path = Path(directory) / "draft.sql"
        # The file's final newline is a terminator, not an extra draft line.
        path.write_text(self.draft.text + "\n", encoding="utf-8")
        returncode = run_terminal_editor([*command, str(path)])
        if returncode:
          print("csql-future: editor exited with status {}; draft kept".format(returncode),
                file=sys.stderr, flush=True)
          return
        text = path.read_text(encoding="utf-8").removesuffix("\n")
        if text != self.draft.text:
          self.draft.text = text
          self.draft.cursor = len(text)
          self.history_index = None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
      print("csql-future: cannot edit draft ({}); draft kept".format(error),
            file=sys.stderr, flush=True)
    finally:
      tty.setraw(0)

  def _move_vertical(self, direction: int) -> None:
    lines = self.draft.text.split("\n")
    before = self.draft.text[:self.draft.cursor]
    row = before.count("\n")
    column = len(before.rsplit("\n", 1)[-1])
    target = row + direction
    if target < 0 or target >= len(lines):
      return
    self.draft.cursor = sum(len(line) + 1 for line in lines[:target]) + min(column, len(lines[target]))

  def _handle_search(self, event: KeyEvent) -> None:
    recalled = self.search.handle(event)
    if recalled is not None:
      self.draft.text = recalled
      self.draft.cursor = len(recalled)
      self.history_index = None

  def _browse_older(self) -> None:
    if self.history_index is None:
      self.history_entries = self.history.entries()
      if not self.history_entries:
        return
      self.unfinished_text = self.draft.text
      self.unfinished_cursor = self.draft.cursor
      self.history_index = 0
    elif self.history_index + 1 < len(self.history_entries):
      self.history_index += 1
    else:
      return
    self.draft.text = self.history_entries[self.history_index]
    self.draft.cursor = 0

  def _browse_newer(self) -> None:
    if self.history_index is None:
      return
    if self.history_index:
      self.history_index -= 1
      self.draft.text = self.history_entries[self.history_index]
      self.draft.cursor = len(self.draft.text)
    else:
      self.history_index = None
      self.draft.text = self.unfinished_text
      self.draft.cursor = self.unfinished_cursor

  def _refresh_completion(self) -> None:
    assert self.catalog is not None
    candidates = self.completion.suggestions.candidates
    selected = candidates[self.completion.selected] if candidates else None
    schema, message, self.catalog_revision = self.catalog.snapshot()
    suggestions = suggest(self.draft.text, self.draft.cursor, schema, message)
    self.completion.open(self.draft.text, self.draft.cursor, suggestions)
    self.completion.active = suggestions.allowed
    self.completion.selected = next(
      (index for index, candidate in enumerate(suggestions.candidates) if candidate == selected), 0,
    )

  def _read_key(self) -> KeyEvent:
    while True:
      if self.catalog is not None and self.completion.active:
        _, _, revision = self.catalog.snapshot()
        if revision != self.catalog_revision:
          self._refresh_completion()
          return KeyEvent(EditorAction.REDRAW)
      if self.consume_resize():
        return KeyEvent(EditorAction.REDRAW)
      ready, _, _ = select.select([0], [], [], 0.05)
      if ready:
        break
    first = os.read(0, 1)
    external_editor = self.editor_prefix and first == b"\x05"
    self.editor_prefix = first == b"\x18"
    if external_editor:
      return KeyEvent(EditorAction.EXTERNAL_EDITOR)
    action = {
      b"\x01": EditorAction.HOME,
      b"\x02": EditorAction.LEFT,
      b"\x03": EditorAction.INTERRUPT,
      b"\x04": EditorAction.EOF,
      b"\x05": EditorAction.END,
      b"\x06": EditorAction.RIGHT,
      b"\x08": EditorAction.BACKSPACE,
      b"\x0a": EditorAction.NEWLINE,
      b"\x0b": EditorAction.KILL_END,
      b"\x0c": EditorAction.REDRAW,
      b"\x0d": EditorAction.SUBMIT,
      b"\x0e": EditorAction.HISTORY_NEWER,
      b"\x10": EditorAction.HISTORY_OLDER,
      b"\x11": EditorAction.QUIT,
      b"\x12": EditorAction.SEARCH,
      b"\x14": EditorAction.TRANSPOSE,
      b"\x15": EditorAction.KILL_START,
      b"\x17": EditorAction.KILL_WORD,
      b"\x19": EditorAction.YANK,
      b"\x7f": EditorAction.BACKSPACE,
    }.get(first)
    if action is not None:
      return KeyEvent(action)
    if first == b"\x09":
      if self.search.active:
        return KeyEvent(EditorAction.INSERT, "\t")
      return KeyEvent(EditorAction.COMPLETE)
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
    if second == b"O":
      ready, _, _ = select.select([0], [], [], 0.05)
      if ready and os.read(0, 1) == b"P":
        return KeyEvent(EditorAction.HELP)
      return KeyEvent(EditorAction.IGNORE)
    if second != b"[":
      return KeyEvent(EditorAction.INSERT, second.decode("utf-8", errors="ignore"))

    sequence = bytearray()
    while len(sequence) < 32:
      ready, _, _ = select.select([0], [], [], 0.01)
      if not ready:
        break
      sequence.extend(os.read(0, 1))
      # Every CSI sequence ends at a byte in this range, including CSI-u.
      if 0x40 <= sequence[-1] <= 0x7e:
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
      b"5~": EditorAction.PAGE_UP,
      b"6~": EditorAction.PAGE_DOWN,
      b"7~": EditorAction.HOME,
      b"8~": EditorAction.END,
      b"11~": EditorAction.HELP,
      b"1;1P": EditorAction.HELP,
      b"13;5u": EditorAction.NEWLINE,
      b"27;5;13~": EditorAction.NEWLINE,
    }.get(bytes(sequence), EditorAction.IGNORE)
    return KeyEvent(action)

  def _render(self, force: bool = False) -> None:
    lines = self.draft.text.split("\n")
    before = self.draft.text[:self.draft.cursor]
    cursor_row = before.count("\n")
    cursor_offset = len(before.rsplit("\n", 1)[-1])
    terminal_size = os.get_terminal_size(0)
    columns = max(2, terminal_size.columns)
    content_width = columns - 1
    prompt = self._truncate("csql-future>", max(0, content_width - 1))
    prefix = prompt + " "
    prefix_width = len(prefix)

    visual_lines = []
    cursor_visual_row = 0
    cursor_column = 0
    for row, line in enumerate(lines):
      # Include the prompt in wrapping so the input cursor shares its first row.
      displayed = prefix + line if row == 0 else line
      wrapped, positions = self._wrap_line(displayed, content_width)
      if row < cursor_row:
        cursor_visual_row += len(wrapped)
      elif row == cursor_row:
        local_row, cursor_column = positions[cursor_offset + (prefix_width if row == 0 else 0)]
        cursor_visual_row += local_row
      visual_lines.extend(wrapped)

    status = self._search_status(content_width) if self.search.active else self._status(len(lines), content_width)
    reserved_rows = 5 if self.completion.active else len(status) + (4 if self.search.active else 1)
    if self.show_help:
      # A bounded preview keeps the draft visible and never grows while scrolling.
      reserved_rows = min(14, max(2, terminal_size.lines - 1))
    draft_rows = max(1, terminal_size.lines - reserved_rows)
    first_visual_row = min(
      max(0, cursor_visual_row - draft_rows // 2),
      max(0, len(visual_lines) - draft_rows),
    )
    visible_visual_lines = visual_lines[first_visual_row:first_visual_row + draft_rows]
    cursor_visual_row -= first_visual_row

    output = list(visible_visual_lines)
    if first_visual_row:
      # Keep the prompt visible when a tall draft scrolls past its first row.
      output.insert(0, PROMPT_STYLE + prompt + RESET)
      cursor_visual_row += 1
    else:
      output[0] = PROMPT_STYLE + prompt + RESET + output[0][len(prompt):]
    if self.show_help:
      self._render_help(output, content_width, min(reserved_rows, terminal_size.lines - len(output)))
    elif self.completion.active:
      suggestions = self.completion.suggestions
      available = max(1, min(6, terminal_size.lines - len(output) - 1))
      start = max(0, self.completion.selected - available + 1)
      if suggestions.candidates:
        for index, candidate in enumerate(suggestions.candidates[start:start + available], start):
          marker = "> " if index == self.completion.selected else "  "
          label = marker + candidate.text + "  " + candidate.detail
          label = ''.join(character if character.isprintable() else repr(character)[1:-1] for character in label)
          output.append(self._truncate(label, content_width))
      else:
        output.append(self._truncate("(no completions)", content_width))
      status = " Completion | "
      if suggestions.message:
        status += suggestions.message + " | "
      status += "Ctrl+N/P select | Enter accepts | Esc cancels "
      output.append(STATUS_STYLE + self._truncate(status, content_width) + RESET)
    elif self.search.active:
      output.append(PROMPT_STYLE + "History search:" + RESET)
      cursor_visual_row = len(output)
      query_prefix = self.search.query.text[:self.search.query.cursor]
      # Keep the insertion point visible when a search is wider than the terminal.
      query_start = 0
      while self._text_width(query_prefix[query_start:]) > content_width:
        query_start += 1
      output.append(self._truncate(self.search.query.text[query_start:], content_width))
      if self.search.matches:
        result_rows = max(1, min(6, terminal_size.lines - len(output) - len(status)))
        start = max(0, self.search.selected - result_rows + 1)
        visible_matches = self.search.matches[start:start + result_rows]
        for index, match in enumerate(visible_matches, start):
          marker = "> " if index == self.search.selected else "  "
          age_text = format_history_age(match.submitted_at)
          if content_width < 40:
            age_text = age_text.replace("just now", "now").replace("time unknown", "unknown")
          age = "({})".format(age_text)
          age = self._truncate(age, max(0, content_width - len(marker) - 2))
          command_width = max(0, content_width - len(marker) - len(age) - 1)
          command = self._truncate(match.command.replace("\n", " ↵ "), command_width)
          padding = " " * max(1, command_width - self._text_width(command) + 1)
          output.append(marker + command + padding + HISTORY_TIME_STYLE + age + RESET)
      else:
        output.append(self._truncate("(no matches)", content_width))
      output.extend(status)
      cursor_column = self._text_width(query_prefix[query_start:])
    else:
      output.extend(status)
    self._draw(output, cursor_visual_row, cursor_column, columns, force)

  def _render_help(self, output: List[str], width: int, height: int) -> None:
    if self.completion.active:
      shortcuts, mode, compact_title = self.COMPLETION_SHORTCUTS, "Completion mode", "Completion help"
    elif self.search.active:
      shortcuts, mode, compact_title = self.SEARCH_SHORTCUTS, "History search mode", "Search help"
    else:
      shortcuts, mode, compact_title = self.INPUT_SHORTCUTS, "Input mode", "Input help"
    shortcuts += ("Text editing:",) + self.EDITING_SHORTCUTS
    help_lines = []
    for shortcut in shortcuts:
      wrapped, _ = self._wrap_line(shortcut, width)
      for index, line in enumerate(wrapped):
        if shortcut.endswith(":"):
          line = PROMPT_STYLE + line + RESET
        elif index == 0:
          key, separator, description = line.partition(":")
          line = HELP_KEY_STYLE + key + RESET + separator + description
        help_lines.append(line)
    available = max(1, height - 2)
    self.help_page_rows = available
    self.help_max_scroll = max(0, len(help_lines) - available)
    self.help_scroll = min(self.help_scroll, self.help_max_scroll)
    position = "{}-{}/{}".format(
      self.help_scroll + 1, min(len(help_lines), self.help_scroll + available), len(help_lines),
    )
    title = "Shortcuts: " + mode
    if len(title) + len(position) + 1 > width:
      title = compact_title
    title = self._truncate(title, max(0, width - len(position) - 1))
    output.append(PROMPT_STYLE + title.ljust(max(0, width - len(position))) + position + RESET)
    output.extend(help_lines[self.help_scroll:self.help_scroll + available])
    if width >= 76:
      footer = " ?/F1/Esc close | Up/Down scroll | PgUp/PgDn page | Home/End | Ctrl+Q quit "
    elif width >= 50:
      footer = " Esc close | Up/Down scroll | PgUp/PgDn | Ctrl+Q quit "
    else:
      footer = " Esc close | Up/Down scroll "
    output.append(STATUS_STYLE + self._truncate(footer, width).ljust(width) + RESET)

  def _draw(
    self, lines: List[str], cursor_row: int, cursor_column: int, columns: int, force: bool,
  ) -> None:
    output = []
    if self.rendered_rows and columns != self.rendered_columns:
      output.append(self._erase_sequence())
    row = self.rendered_rows - 1 - self.cursor_to_bottom if self.rendered_rows else 0
    column = self.rendered_cursor_column

    def move(target_row: int, target_column: int = 0) -> None:
      nonlocal row, column
      if target_row < row:
        output.append("\033[{}A".format(row - target_row))
      elif target_row > row:
        # Newlines also allocate space when the editor grows at the screen bottom.
        output.append("\r\n" * (target_row - row))
      if target_row != row or target_column != column:
        output.append("\r")
        if target_column:
          output.append("\033[{}C".format(target_column))
      row, column = target_row, target_column

    for index in range(max(len(lines), self.rendered_rows)):
      line = lines[index] if index < len(lines) else ""
      if not force and index < len(self.rendered_lines) and self.rendered_lines[index] == line:
        continue
      move(index)
      output.extend((line, "\033[K"))
      # Styles do not occupy columns; use carriage return before the next move.
      output.append("\r")
      column = 0
    move(cursor_row, cursor_column)
    if output:
      # Never expose a separate blank frame between erasing and drawing.
      os.write(1, "".join(output).encode("utf-8"))
    self.rendered_lines = lines
    self.rendered_columns = columns
    self.rendered_rows = len(lines)
    self.cursor_to_bottom = len(lines) - 1 - cursor_row
    self.rendered_cursor_column = cursor_column

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

  def _search_status(self, width: int) -> List[str]:
    return self._status_lines("History search mode", (
      ("Ctrl+Q", " quit"), ("Enter", " recall" if width >= 26 else ""),
    ), width, hints=(("Esc", " back"),))

  def _status(self, line_count: int, width: int) -> List[str]:
    return self._status_lines("Input mode", (
      ("Ctrl+R", " history"), ("Ctrl+Q", " quit"),
    ), width, " | {} lines".format(line_count))

  def _status_lines(
    self, mode: str, actions: Sequence[Tuple[str, str]], width: int, detail: str = "",
    hints: Sequence[Tuple[str, str]] = (),
  ) -> List[str]:
    groups = [("", " " + mode if len(mode) < width else mode, True)]
    groups.extend((key, label, True) for key, label in actions)
    groups.extend((key, label, False) for key, label in (*hints, ("?", " shortcuts")))
    lines = []
    line = ""
    used = 0
    for key, label, required in groups:
      length = len(key + label)
      separator = " | " if used else ""
      if used and used + len(separator) + length > width:
        if not required:
          continue
        lines.append(line + STATUS_STYLE + " " * (width - used) + RESET)
        line, used, separator = "", 0, ""
      if length > width:
        key = self._truncate(key, width)
        label = self._truncate(label, width - len(key))
        length = len(key + label)
      line += STATUS_STYLE + separator + STATUS_KEY_STYLE + key + STATUS_STYLE + label
      used += len(separator) + length
    if used + len(detail) <= width:
      line += STATUS_STYLE + detail
      used += len(detail)
    lines.append(line + STATUS_STYLE + " " * (width - used) + RESET)
    if self.history.mode is HistoryMode.MEMORY_ONLY:
      lines.insert(0, STATUS_STYLE + self._truncate(MEMORY_ONLY_STATUS, width).ljust(width) + RESET)
    return lines

  def _erase(self) -> None:
    output = self._erase_sequence()
    if output:
      os.write(1, output.encode("ascii"))

  def _erase_sequence(self) -> str:
    if not self.rendered_rows:
      return ""
    output = []
    if self.cursor_to_bottom:
      output.append("\033[{}B".format(self.cursor_to_bottom))
    output.append("\r")
    for row in range(self.rendered_rows):
      output.append("\033[2K")
      if row + 1 < self.rendered_rows:
        output.append("\033[1A")
    output.append("\r")
    self.rendered_rows = 0
    self.cursor_to_bottom = 0
    self.rendered_lines = []
    self.rendered_cursor_column = 0
    return "".join(output)


def run_terminal_editor(command: Sequence[str]) -> int:
  """Give an editor the foreground terminal and reap it before returning."""
  previous_group = os.tcgetpgrp(0)
  previous_attributes = termios.tcgetattr(0)
  previous_ttou = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
  previous_int = signal.signal(signal.SIGINT, lambda _signum, _frame: None)
  previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, TERMINATION_SIGNALS)
  process: Optional[subprocess.Popen] = None

  def prepare_child() -> None:
    os.setpgrp()
    os.tcsetpgrp(0, os.getpgrp())
    signal.signal(signal.SIGTTOU, signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)

  try:
    process = subprocess.Popen(command, preexec_fn=prepare_child)
    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    return process.wait()
  finally:
    try:
      if process is not None and process.poll() is None:
        try:
          os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
          pass
        try:
          process.wait(timeout=1)
        except subprocess.TimeoutExpired:
          os.killpg(process.pid, signal.SIGKILL)
          process.wait()
    finally:
      os.tcsetpgrp(0, previous_group)
      termios.tcsetattr(0, termios.TCSADRAIN, previous_attributes)
      signal.signal(signal.SIGINT, previous_int)
      signal.signal(signal.SIGTTOU, previous_ttou)
      signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


class CsqlTerminal:

  def __init__(
    self,
    executable: str,
    arguments: Sequence[str],
    child_signal_mask: set[signal.Signals],
  ) -> None:
    self.prompt_base = "__CSQL_FUTURE_{}__".format(uuid.uuid4().hex)
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
  completion = True
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
    if argument == "--no-completion":
      completion = False
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

  options = WrapperOptions(history_file.resolve(strict=False), history_limit, no_history, completion)
  return options, forwarded


def _integer_limit(value: str) -> int:
  try:
    return int(value, 10)
  except ValueError as error:
    raise OptionError("--history-limit must be an integer") from error


def find_csql() -> Optional[str]:
  # Follow the selected CUBRID environment, including csql.sh's verified client.
  return shutil.which("csql")


def completion_connection(arguments: Sequence[str]) -> Optional[Connection]:
  """Copy only connection options, never output, SQL, or utility actions."""
  values = {}
  databases = []
  standalone = False
  index = 0
  while index < len(arguments):
    argument = arguments[index]
    if argument == '--':
      databases.extend(arguments[index + 1:])
      break
    if argument.startswith('--'):
      option = _resolved_csql_long_option(argument)
      if option is None or option in ('sysadm', 'sysadm-rebuild-catalog', 'write-on-standby'):
        return None
      if option in ('SA-mode', 'CS-mode'):
        standalone = option == 'SA-mode'
      if option in CSQL_LONG_OPTIONS_WITH_VALUE:
        if '=' in argument:
          value = argument.split('=', 1)[1]
        elif index + 1 < len(arguments):
          index += 1
          value = arguments[index]
        else:
          return None
        if option in ('user', 'password'):
          values[option] = value
    elif argument.startswith('-') and argument != '-':
      for position, option in enumerate(argument[1:], 1):
        if option in ('S', 'C'):
          standalone = option == 'S'
        elif option in CSQL_SHORT_OPTIONS_WITH_VALUE:
          value = argument[position + 1:]
          if not value:
            if index + 1 >= len(arguments):
              return None
            index += 1
            value = arguments[index]
          if option in ('u', 'p'):
            values['user' if option == 'u' else 'password'] = value
          break
        elif option not in {'e', 's', 'l', 'r', 't', 'N', 'q', 'd'}:
          return None
    else:
      databases.append(argument)
    index += 1
  if len(databases) != 1 or databases[0].startswith('-'):
    return None
  copied = ['-S' if standalone else '-C']
  for key, value in values.items():
    copied.extend(['--' + key + '=' + value])
  copied.append(databases[0])
  return Connection(tuple(copied), standalone)


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
  catalog: Optional[CatalogCache] = None
  signal_mask_restored = False
  try:
    if options.completion:
      catalog = CatalogCache(executable, completion_connection(arguments))
      # Passwords remain csql-owned. Batch lookup uses only explicit credentials.
      # A failed snapshot must finish before interactive authentication begins.
      catalog.prepare_standalone()
    terminal = CsqlTerminal(executable, arguments, previous_signal_mask)
    signal_mask_restored = True
    signal.pthread_sigmask(signal.SIG_SETMASK, previous_signal_mask)
    if not terminal.relay_until_input():
      return terminal.returncode()

    history = SubmissionHistory(options.history_file, options.history_limit, options.no_history)
    editor = DraftEditor(history, terminal.consume_resize, catalog)
    while True:
      submission = editor.read()
      # A foreground editor receives SIGWINCH itself. Refresh csql's private
      # terminal before handing input back, including those intervening resizes.
      terminal.resize()
      if submission is None:
        if not terminal.send_eof():
          break
      else:
        if catalog is not None and submission.strip() == ';refresh-completions':
          catalog.request(force=True)
          continue
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
    if catalog is not None:
      catalog.close()
    if terminal is not None:
      terminal.close()


def main(arguments: Optional[Sequence[str]] = None) -> int:
  if arguments is None:
    arguments = sys.argv[1:]
  if list(arguments) == ["--help"]:
    print("""Usage: csql-future [WRAPPER OPTIONS] [CSQL OPTIONS] DATABASE

Searchable history, schema-aware completion, and multiline editing for CUBRID csql.
Uses the csql executable selected by PATH in your active CUBRID environment.

Wrapper options:
  --history-file PATH   SQLite history file (default: ./.csql_history.sqlite3)
  --history-limit N     Retain the latest N unique commands (default: 10000)
  --no-history          Recall existing history without saving new submissions
  --no-completion       Disable schema lookups and keep literal Tab input
  --help               Show this help without requiring CUBRID
  --version            Show the installed wrapper version
  --                   Forward remaining arguments to csql unchanged

Input mode: ?/F1 shortcuts, Ctrl+R history search, Ctrl+X Ctrl+E external editor.
History search mode: Ctrl+N/P selects, Enter recalls for editing, Esc restores the draft.
Editor selection: $VISUAL, then $EDITOR, then vi. Save and exit to return to the draft.
Enter submits after the completion menu closes. ? opens help in an empty field; F1 opens it at any time.
Ctrl+Enter/Ctrl+J inserts a newline. Ctrl+Q quits from either mode or help.
Completion mode: Tab opens, Ctrl+N/P selects, Enter accepts, Esc cancels.
Other arguments pass through to csql. Run csql directly for its native usage.""")
    return 0
  if list(arguments) == ["--version"]:
    from importlib.metadata import version
    print("csql-future " + version("csql-future"))
    return 0
  launch_directory = Path.cwd()
  try:
    options, csql_arguments = parse_options(arguments, launch_directory)
  except OptionError as error:
    print("csql-future: {}".format(error), file=sys.stderr)
    return 2

  executable = find_csql()
  if executable is None:
    print("csql-future: installed csql executable not found", file=sys.stderr)
    return 127

  if is_interactive(csql_arguments):
    return run_interactive(executable, csql_arguments, options)

  try:
    os.execv(executable, ["csql", *csql_arguments])
  except OSError as error:
    print("csql-future: cannot execute csql: {}".format(error), file=sys.stderr)
    return 126
  return 126


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))

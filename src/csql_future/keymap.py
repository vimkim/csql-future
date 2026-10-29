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
"""Load editor shortcuts and resolve terminal key sequences."""

from __future__ import annotations

from enum import Enum, auto
from itertools import product
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


try:
  import tomllib
except ModuleNotFoundError:
  import tomli as tomllib


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
  HELP_EMPTY = auto()
  EXTERNAL_EDITOR = auto()
  COMPLETE = auto()
  CANCEL = auto()
  IGNORE = auto()


DEFAULT_BINDINGS = {
  "submit": ["Enter"],
  "eof": ["Ctrl+D"],
  "quit": ["Ctrl+Q"],
  "interrupt": ["Ctrl+C"],
  "newline": ["Ctrl+Enter", "Ctrl+J", "Alt+Enter"],
  "backspace": ["Backspace", "Ctrl+H"],
  "delete": ["Delete"],
  "left": ["Ctrl+B", "Left"],
  "right": ["Ctrl+F", "Right"],
  "up": ["Up"],
  "down": ["Down"],
  "page_up": ["PageUp"],
  "page_down": ["PageDown"],
  "home": ["Ctrl+A", "Home"],
  "end": ["Ctrl+E", "End"],
  "kill_word": ["Ctrl+W"],
  "kill_start": ["Ctrl+U"],
  "kill_end": ["Ctrl+K"],
  "yank": ["Ctrl+Y"],
  "transpose": ["Ctrl+T"],
  "history_older": ["Ctrl+P"],
  "history_newer": ["Ctrl+N"],
  "redraw": ["Ctrl+L"],
  "search": ["Ctrl+R"],
  "help": ["F1"],
  "help_empty": ["?"],
  "external_editor": ["Ctrl+X Ctrl+E"],
  "complete": ["Tab"],
  "cancel": ["Esc"],
}

# Each tuple contains equivalent encodings of one physical key.
NAMED_KEYS = {
  "enter": (b"\r",),
  "tab": (b"\t",),
  "esc": (b"\x1b",),
  "space": (b" ",),
  "backspace": (b"\x7f",),
  "delete": (b"\x1b[3~",),
  "insert": (b"\x1b[2~",),
  "up": (b"\x1b[A", b"\x1bOA"),
  "down": (b"\x1b[B", b"\x1bOB"),
  "right": (b"\x1b[C", b"\x1bOC"),
  "left": (b"\x1b[D", b"\x1bOD"),
  "home": (b"\x1b[H", b"\x1b[1~", b"\x1b[7~", b"\x1bOH"),
  "end": (b"\x1b[F", b"\x1b[4~", b"\x1b[8~", b"\x1bOF"),
  "pageup": (b"\x1b[5~",),
  "pagedown": (b"\x1b[6~",),
  "f1": (b"\x1bOP", b"\x1b[11~", b"\x1b[1;1P"),
  "f2": (b"\x1bOQ", b"\x1b[12~"),
  "f3": (b"\x1bOR", b"\x1b[13~"),
  "f4": (b"\x1bOS", b"\x1b[14~"),
  "ctrl+enter": (b"\n", b"\x1b[13;5u", b"\x1b[27;5;13~"),
  "alt+enter": (b"\x1b\r", b"\x1b\n"),
}
for number, code in zip(range(5, 13), (15, 17, 18, 19, 20, 21, 23, 24)):
  NAMED_KEYS["f{}".format(number)] = ("\x1b[{}~".format(code).encode(),)


class KeymapError(ValueError):
  pass


def _stroke(token: str) -> Tuple[bytes, ...]:
  normalized = token.casefold()
  if normalized in NAMED_KEYS:
    return NAMED_KEYS[normalized]
  if normalized.startswith("ctrl+") and len(normalized) == 6:
    character = normalized[-1]
    if "a" <= character <= "z" or character in "@[\\]^_":
      return (bytes([ord(character.upper()) & 0x1f]),)
  if normalized == "ctrl+space":
    return (b"\x00",)
  if normalized.startswith("alt+") and len(normalized) == 5:
    character = token[-1]
    if character.isascii() and character.isalnum() and character != "O":
      return (b"\x1b" + character.encode(),)
  if len(token) == 1 and token.isprintable():
    return (token.encode("utf-8"),)
  raise KeymapError("unknown key {!r}".format(token))


class Keymap:

  def __init__(self, overrides: Optional[dict] = None) -> None:
    self.bindings: Dict[str, List[str]] = {action: list(keys) for action, keys in DEFAULT_BINDINGS.items()}
    if overrides is not None:
      if not isinstance(overrides, dict):
        raise KeymapError("keymap must map actions to key lists")
      for action, keys in overrides.items():
        if action not in DEFAULT_BINDINGS:
          raise KeymapError("unknown action {!r}; use --print-keymap to list actions".format(action))
        if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
          raise KeymapError("{} must be a list of key strings".format(action))
        self.bindings[action] = keys
    self.actions: Dict[Tuple[bytes, ...], EditorAction] = {}
    self.prefixes = set()
    owners = {}
    for action, keys in self.bindings.items():
      for key in keys:
        tokens = key.split()
        if not tokens:
          raise KeymapError("{} contains an empty shortcut".format(action))
        if action == "help_empty" and not (len(key) == 1 and key.isprintable() and not key.isspace()):
          raise KeymapError("help_empty requires a single printable character, such as ?")
        for sequence in product(*(_stroke(token) for token in tokens)):
          previous = self.actions.get(sequence)
          target = EditorAction[action.upper()]
          if previous is not None and previous is not target:
            raise KeymapError("{!r} for {} conflicts with {} ({})".format(
              key, action, previous.name.lower(), owners[sequence],
            ))
          self.actions[sequence] = target
          owners[sequence] = key
    for sequence in self.actions:
      for length in range(1, len(sequence)):
        prefix = sequence[:length]
        if prefix in self.actions:
          raise KeymapError("{!r} is a prefix of {!r}; remove one binding".format(
            owners[prefix], owners[sequence],
          ))
        self.prefixes.add(prefix)

  def label(self, action: str, first: bool = False) -> str:
    keys = self.bindings[action]
    if action == "newline" and keys == DEFAULT_BINDINGS[action]:
      keys = keys[:-1]  # Keep the legacy Alt+Enter alias out of the hints.
    if not keys:
      return "Unbound"
    return keys[0] if first else " / ".join(keys)


def default_keymap_path() -> Path:
  directory = os.environ.get("XDG_CONFIG_HOME")
  return (Path(directory) if directory else Path.home() / ".config") / "csql-future" / "keymap.toml"


def load_keymap(path: Optional[Path] = None) -> Keymap:
  selected = default_keymap_path() if path is None else path
  try:
    text = selected.read_text(encoding="utf-8")
  except FileNotFoundError as error:
    if path is None:
      return Keymap()
    raise KeymapError("cannot read keymap {}: {}".format(selected, error)) from error
  except (OSError, UnicodeError) as error:
    raise KeymapError("cannot read keymap {}: {}".format(selected, error)) from error
  try:
    return Keymap(tomllib.loads(text))
  except (ValueError, RecursionError) as error:
    raise KeymapError("invalid keymap {}: {}".format(selected, error)) from error

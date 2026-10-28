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
"""Shared external-process PTY harness for csql-future tests."""

from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import termios
import time
from typing import Optional, Sequence


def wait_for_process_exit(process_id: int, timeout: float = 2.0) -> bool:
  process_path = Path("/proc/{}".format(process_id))
  deadline = time.monotonic() + timeout
  while process_path.exists() and time.monotonic() < deadline:
    time.sleep(0.02)
  return not process_path.exists()


class AnsiScreen:

  CSI = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])")

  def __init__(self, rows: int = 24, columns: int = 100):
    self.rows = rows
    self.columns = columns
    self.cells = [[" "] * columns for _ in range(rows)]
    self.row = 0
    self.column = 0

  def feed(self, data: bytes) -> None:
    text = data.decode("utf-8", errors="replace")
    index = 0
    while index < len(text):
      if text[index] == "\x1b":
        match = self.CSI.match(text, index)
        if match:
          self._control(match.group(1), match.group(2))
          index = match.end()
          continue
      character = text[index]
      index += 1
      if character == "\r":
        self.column = 0
      elif character == "\n":
        self._line_feed()
      elif character >= " ":
        if self.column >= self.columns:
          self.column = 0
          self._line_feed()
        self.cells[self.row][self.column] = character
        self.column += 1

  def display(self) -> list[str]:
    return ["".join(line).rstrip() for line in self.cells]

  def resize(self, rows: int, columns: int) -> None:
    resized = []
    for row in self.cells[:rows]:
      resized.append((row[:columns] + [" "] * columns)[:columns])
    while len(resized) < rows:
      resized.append([" "] * columns)
    self.rows = rows
    self.columns = columns
    self.cells = resized
    self.row = min(self.row, rows - 1)
    self.column = min(self.column, columns - 1)

  def _control(self, parameters: str, command: str) -> None:
    values = [int(value) if value else 0 for value in parameters.split(";")] if parameters else [0]
    amount = values[0] or 1
    if command == "A":
      self.row = max(0, self.row - amount)
    elif command == "B":
      self.row = min(self.rows - 1, self.row + amount)
    elif command == "C":
      self.column = min(self.columns - 1, self.column + amount)
    elif command == "D":
      self.column = max(0, self.column - amount)
    elif command == "K":
      mode = values[0]
      if mode == 2:
        self.cells[self.row] = [" "] * self.columns
      elif mode == 1:
        self.cells[self.row][:self.column + 1] = [" "] * (self.column + 1)
      else:
        self.cells[self.row][self.column:] = [" "] * (self.columns - self.column)

  def _line_feed(self) -> None:
    if self.row + 1 < self.rows:
      self.row += 1
    else:
      self.cells.pop(0)
      self.cells.append([" "] * self.columns)


class TerminalSession:

  def __init__(self, command: Sequence[str], cwd: Path, environment: dict[str, str]):
    process_id, terminal_fd = pty.fork()
    if process_id == 0:
      os.chdir(cwd)
      os.execve(command[0], list(command), environment)

    self.process_id = process_id
    self.terminal_fd = terminal_fd
    self.output = bytearray()
    self.read_position = 0
    self.wait_status: Optional[int] = None
    self.initial_attributes = termios.tcgetattr(terminal_fd)
    self.set_size(24, 100)

  def send(self, data: bytes) -> None:
    os.write(self.terminal_fd, data)

  def set_size(self, rows: int, columns: int) -> None:
    fcntl.ioctl(self.terminal_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))

  def read_until(self, expected: bytes, timeout: float = 3.0) -> bytes:
    deadline = time.monotonic() + timeout
    while expected not in self.output[self.read_position:]:
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        self.fail("timed out waiting for {!r}".format(expected))
      ready, _, _ = select.select([self.terminal_fd], [], [], min(0.05, remaining))
      if ready:
        self._read()
    end = self.output.index(expected, self.read_position) + len(expected)
    result = bytes(self.output[self.read_position:end])
    self.read_position = end
    return result

  def read_for(self, duration: float) -> bytes:
    deadline = time.monotonic() + duration
    start = self.read_position
    while True:
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        break
      ready, _, _ = select.select([self.terminal_fd], [], [], min(0.05, remaining))
      if ready:
        self._read()
    self.read_position = len(self.output)
    return bytes(self.output[start:self.read_position])

  def wait(self, timeout: float = 3.0) -> int:
    deadline = time.monotonic() + timeout
    while self.wait_status is None:
      waited_process, status = os.waitpid(self.process_id, os.WNOHANG)
      if waited_process == self.process_id:
        self.wait_status = status
        break
      if time.monotonic() >= deadline:
        self.fail("process did not exit")
      self.read_for(0.02)
    assert self.wait_status is not None
    if os.WIFEXITED(self.wait_status):
      return os.WEXITSTATUS(self.wait_status)
    return 128 + os.WTERMSIG(self.wait_status)

  def close(self) -> None:
    if self.wait_status is None:
      try:
        os.kill(self.process_id, signal.SIGKILL)
      except ProcessLookupError:
        pass
      try:
        _, self.wait_status = os.waitpid(self.process_id, 0)
      except ChildProcessError:
        pass
    os.close(self.terminal_fd)

  def terminal_attributes(self) -> list[object]:
    return termios.tcgetattr(self.terminal_fd)

  def fail(self, message: str) -> None:
    rendered = bytes(self.output).decode(errors="replace")
    raise AssertionError("{}\nterminal output:\n{}".format(message, rendered))

  def _read(self) -> None:
    try:
      chunk = os.read(self.terminal_fd, 65536)
    except OSError as error:
      if error.errno == errno.EIO:
        return
      raise
    self.output.extend(chunk)

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
"""Exercise editable sessions against an isolated real csql runtime."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pty_test_support import AnsiScreen, TerminalSession, wait_for_process_exit
from verify_real_csql import isolate_runtime, require_program

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = Path(os.environ.get("CSQL_WITH_HISTORY_TEST_COMMAND", str(PROJECT_ROOT / ".venv/bin/csql-with-history")))


class CatalogInterruptObservation(NamedTuple):
  cancelled_and_returned: bool
  plan_generated: bool


class Session(TerminalSession):

  def __init__(self, arguments: Sequence[str], environment: dict[str, str], cwd: Path):
    super().__init__([str(WRAPPER), *arguments], cwd, environment)
    self.set_size(30, 100)
    self.screen = AnsiScreen(rows=30, columns=100)
    self.screen_position = 0
    self.diagnostic_redactions: list[str] = []

  def expect(self, text: str, timeout: float = 15.0) -> bytes:
    return self.read_until(text.encode("utf-8"), timeout)

  def fail(self, message: str) -> None:
    rendered = bytes(self.output).decode(errors="replace")
    for secret in self.diagnostic_redactions:
      rendered = rendered.replace(secret, "<redacted>")
    raise AssertionError("{}\nterminal output:\n{}".format(message, rendered))

  def submit(self, text: str, expected: str, timeout: float = 15.0) -> None:
    self.send(text.encode("utf-8") + b"\r")
    self.expect(expected, timeout)
    self.expect("csql-with-history>")

  def submit_to_prompt(self, text: str, timeout: float = 15.0) -> None:
    self.send(text.encode("utf-8") + b"\r")
    self.expect_csql_echo(text, timeout)
    self.expect("csql-with-history>", timeout)

  def expect_csql_echo(self, text: str, timeout: float = 15.0) -> None:
    expected = text.encode("utf-8") + b"\r"
    start = self.read_position
    deadline = time.monotonic() + timeout
    while True:
      normalized = bytes(self.output[start:]).replace(b" \x08", b"")
      if expected in normalized:
        self.read_position = start
        return
      remaining = deadline - time.monotonic()
      if remaining <= 0:
        self.fail("timed out waiting for normalized csql echo {!r}".format(expected))
      self.read_for(min(0.05, remaining))

  def finish(self) -> int:
    self.send(b";exit\r")
    return self.wait(10)

  def update_screen(self) -> list[str]:
    self.screen.feed(bytes(self.output[self.screen_position:]))
    self.screen_position = len(self.output)
    return self.screen.display()

  def reset_screen(self, rows: int, columns: int) -> None:
    self.screen = AnsiScreen(rows=rows, columns=columns)
    self.screen_position = len(self.output)

  def assert_editor_screen(self, expected_output: str) -> None:
    lines = self.update_screen()
    if sum("csql-with-history>" in line for line in lines) != 1:
      raise AssertionError("expected one rendered wrapper prompt: {}".format(lines))
    if sum("SQL  draft" in line for line in lines) != 1:
      raise AssertionError("expected one rendered status bar: {}".format(lines))
    if not any(expected_output in line for line in lines):
      raise AssertionError("expected rendered output {!r}: {}".format(expected_output, lines))


def check_session(label: str, mode: str, database: str, environment: dict[str, str], cwd: Path) -> None:
  session = Session([mode, "-u", "dba", "--no-pager", database], environment, cwd)
  try:
    session.expect("csql-with-history>")
    long_draft = "select '" + "한글" * 40 + "';"
    session.send(long_draft.encode("utf-8"))
    session.read_for(0.2)
    session.set_size(14, 47)
    resized = session.read_for(0.3)
    if b"csql-with-history>" not in resized or "한글".encode("utf-8") not in resized:
      raise AssertionError("enhanced editor did not redraw the multibyte draft after resize")
    session.send(b"\x03")
    session.set_size(30, 100)
    session.read_for(0.2)
    session.reset_screen(30, 100)

    session.submit("select 424242;", "1 row selected")
    session.submit("select no_such_ticket02_column;", "ERROR:")
    session.submit("select 424243;", "1 row selected")

    session.send(b"select\x0a424244;\r")
    session.expect("1 row selected")
    session.expect("csql-with-history>")

    session.submit(";singleline off", "SINGLELINE IS OFF")
    session.send(b"select\r")
    first_fragment = session.read_for(0.3)
    if b"row selected" in first_fragment:
      raise AssertionError("explicit mode executed the first fragment")
    session.send(b"424245;\r")
    second_fragment = session.read_for(0.3)
    if b"row selected" in second_fragment:
      raise AssertionError("explicit mode executed before ;xrun")
    session.submit(";xrun", "1 row selected")
    session.submit(";singleline on", "SINGLELINE IS ON")

    session.submit("select 'csql> prompt-looking output';", "1 row selected")
    session.assert_editor_screen("prompt-looking output")

    session.send(b"select sleep(1);\r")
    session.read_for(0.3)
    running_lines = session.update_screen()
    if any("csql-with-history>" in line or "SQL  draft" in line for line in running_lines):
      raise AssertionError("quiet running work returned to the wrapper editor early: {}".format(running_lines))
    session.expect("1 row selected", timeout=5.0)
    session.expect("csql-with-history>")
    session.assert_editor_screen("1 row selected")
    if session.finish() != 0:
      raise AssertionError("{} session returned a nonzero status".format(label))
    print("PASS {} editable session".format(label))
  finally:
    session.close()


def stored_commands(history_file: Path) -> list[str]:
  with closing(sqlite3.connect(history_file)) as connection:
    return [row[0] for row in connection.execute("SELECT command FROM submissions ORDER BY id")]


def child_process_ids(process_id: int) -> list[int]:
  children_file = Path("/proc/{}/task/{}/children".format(process_id, process_id))
  try:
    return [int(value) for value in children_file.read_text(encoding="ascii").split()]
  except (OSError, ValueError):
    return []


def assert_terminal_program_size(
  session: Session,
  expected_rows: int,
  expected_columns: int,
) -> None:
  deadline = time.monotonic() + 2.0
  while time.monotonic() < deadline:
    csql_processes = child_process_ids(session.process_id)
    if len(csql_processes) == 1:
      for process_id in child_process_ids(csql_processes[0]):
        terminal_path = "/proc/{}/fd/0".format(process_id)
        try:
          terminal_fd = os.open(terminal_path, os.O_RDONLY | os.O_NOCTTY)
          try:
            size = os.get_terminal_size(terminal_fd)
          finally:
            os.close(terminal_fd)
        except OSError:
          continue
        if (size.lines, size.columns) == (expected_rows, expected_columns):
          return
    time.sleep(0.02)
  raise AssertionError(
    "terminal program did not observe size {}x{}".format(
      expected_rows, expected_columns
    )
  )


def check_password_handoff(database: str, environment: dict[str, str], cwd: Path) -> None:
  history_file = cwd / "password-handoff-history.sqlite3"
  username = "cwh_password_{}".format(os.getpid())
  password = secrets.token_urlsafe(18)
  create = subprocess.run(
    ["csql", "-S", "-u", "dba", "--no-pager", database],
    input="CREATE USER {} PASSWORD '{}';\nCOMMIT;\n".format(username, password).encode("utf-8"),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=cwd,
    env=environment,
    check=False,
  )
  if create.returncode != 0 or b"ERROR:" in create.stdout + create.stderr:
    diagnostic = (create.stdout + create.stderr).decode(errors="replace").replace(password, "<redacted>")
    raise AssertionError("could not create the synthetic password-handoff user: {}".format(diagnostic))

  session = Session(
    ["--history-file", str(history_file), "-S", "-u", username, "--no-pager", database],
    environment,
    cwd,
  )
  try:
    session.expect("Password")
    session.diagnostic_redactions.append(password)
    session.send(password.encode("utf-8") + b"\r")
    session.expect("csql-with-history>")
    if password.encode("utf-8") in bytes(session.output):
      raise AssertionError("password input was echoed into the terminal transcript")
    session.submit("select 907001;", "1 row selected")
    session.send(b"\x12907001")
    session.read_for(0.2)
    if "select 907001;" not in "\n".join(session.update_screen()):
      raise AssertionError("enhanced history was unavailable after password authentication")
    session.send(b"\x1b")
    session.read_for(0.1)
    session.send(b"\x03")
    if session.finish() != 0:
      raise AssertionError("password-handoff session returned a nonzero status")
  finally:
    session.close()
    subprocess.run(
      ["csql", "-S", "-u", "dba", "--no-pager", "-c", "DROP USER {};".format(username), database],
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      cwd=cwd,
      env=environment,
      check=False,
    )

  retained = stored_commands(history_file)
  if retained != ["select 907001;", ";exit"] or any(password in command for command in retained):
    diagnostic = repr(retained).replace(password, "<redacted>")
    raise AssertionError("password handoff changed wrapper history boundaries: {}".format(diagnostic))
  print("PASS masked real-csql password handoff and private history")


def check_terminal_program_handoffs(database: str, environment: dict[str, str], cwd: Path) -> None:
  less = require_program("less")
  vi = require_program("vi")
  shell = require_program("sh")
  history_file = cwd / "terminal-program-history.sqlite3"
  program_environment = environment.copy()
  program_environment["LESS"] = "R"
  session = Session(
    ["--history-file", str(history_file), "-S", "-u", "dba", database],
    program_environment,
    cwd,
  )
  try:
    session.expect("csql-with-history>")
    session.submit_to_prompt(";pager_cmd {} -R".format(less))
    pager_query = "select 'ticket07-pager-row-' || rownum from db_class a, db_class b limit 100;"
    session.send(pager_query.encode("utf-8") + b"\r")
    session.expect("ticket07-pager-row-", timeout=20)
    session.read_for(0.3)
    session.set_size(21, 73)
    assert_terminal_program_size(session, 21, 73)
    session.read_for(0.2)
    session.send(b"987654g")
    session.read_for(0.1)
    session.send(b"q")
    session.expect("csql-with-history>", timeout=20)
    session.submit_to_prompt(";pager_cmd cat")

    session.submit(";singleline off", "SINGLELINE IS OFF")
    session.submit_to_prompt("select 'editor-before-ticket07';")
    session.submit_to_prompt(";editor_cmd {} -n".format(vi))
    session.send(b";edit\r")
    session.expect("\x1b[?1049h", timeout=20)
    session.set_size(19, 77)
    assert_terminal_program_size(session, 19, 77)
    editor_deadline = time.monotonic() + 1.0
    while time.monotonic() < editor_deadline:
      output = session.read_for(0.05)
      reports = output.count(b"\x1b[6n")
      if reports:
        session.send(b"\x1b[1;1R" * reports)
    if b"editor-before-ticket07" not in bytes(session.output):
      raise AssertionError("external editor did not receive csql's command buffer")
    session.send(b"\x1b:%s/editor-before-ticket07/editor-external-ticket07/\r:wq\r")
    session.expect("csql-with-history>", timeout=20)
    session.submit(";xrun", "editor-external-ticket07")

    session.submit_to_prompt(";shell_cmd {}".format(shell))
    session.send(b";shell\r")
    session.expect_csql_echo(";shell")
    session.set_size(17, 61)
    assert_terminal_program_size(session, 17, 61)
    session.send(b"stty size\n")
    session.expect("17 61", timeout=5)
    interrupted_at = time.monotonic()
    session.send(b"sleep 10\n")
    session.read_for(0.1)
    session.send(b"\x03")
    session.send(b"printf 'shell-external-ticket07\\n'\nexit 7\n")
    session.expect("shell-external-ticket07", timeout=20)
    if time.monotonic() - interrupted_at >= 3.0:
      raise AssertionError("shell interrupt was not delivered through the terminal handoff")
    session.expect("csql-with-history>", timeout=20)
    session.reset_screen(17, 61)

    missing = cwd / "program-does-not-exist"
    if missing.exists():
      raise AssertionError("missing-program fixture unexpectedly exists: {}".format(missing))
    session.submit_to_prompt(";editor_cmd {}".format(missing))
    session.send(b";edit\r")
    session.expect_csql_echo(";edit", timeout=20)
    session.expect("csql-with-history>", timeout=20)
    session.submit_to_prompt(";pager_cmd {}".format(missing))
    session.send(b"select 907002;\r")
    session.expect_csql_echo("select 907002;", timeout=20)
    session.expect("csql-with-history>", timeout=20)
    session.submit_to_prompt(";shell_cmd {}".format(missing))
    session.send(b";shell\r")
    session.expect_csql_echo(";shell", timeout=20)
    session.expect("csql-with-history>", timeout=20)
    lowered_output = bytes(session.output).lower()
    if b"not found" not in lowered_output and b"no such file" not in lowered_output:
      raise AssertionError("missing terminal programs produced no observable diagnostic")

    session.submit(";singleline on", "SINGLELINE IS ON")
    session.submit("select 907003;", "1 row selected")
    session.assert_editor_screen("907003")
    session.send(b"\x1b[A")
    session.read_for(0.2)
    if "select 907003;" not in "\n".join(session.update_screen()):
      raise AssertionError("history recall was unavailable after terminal handoffs")
    session.send(b"\x03")
    for private_input in ("987654g", "editor-external-ticket07", "shell-external-ticket07"):
      session.send(b"\x12" + private_input.encode("ascii"))
      session.read_for(0.2)
      if "(no matches)" not in "\n".join(session.update_screen()):
        raise AssertionError("terminal-program input appeared in wrapper search: {}".format(private_input))
      session.send(b"\x1b")
      session.read_for(0.1)
    session.send(b"\x03")
    if session.finish() != 0:
      raise AssertionError("terminal-program handoff session returned a nonzero status")
  finally:
    session.close()

  retained = stored_commands(history_file)
  for private_input in ("q", "987654g", "editor-external-ticket07", "shell-external-ticket07"):
    if private_input in retained:
      raise AssertionError("terminal-program input became a history entry: {!r}".format(retained))
  if ";edit" not in retained or "select 'editor-external-ticket07';" in retained:
    raise AssertionError("external editor text was reconstructed in history: {!r}".format(retained))
  print("PASS resized real less/vi/shell handoffs, clean redraw, error exits, and history isolation")


def drive_default_shell(session: TerminalSession, return_prompt: bytes) -> int:
  session.send(b";shell\r")
  cursor_reports = 0
  deadline = time.monotonic() + 2.0
  while time.monotonic() < deadline:
    output = session.read_for(0.1)
    reports = output.count(b"\x1b[6n")
    if reports:
      cursor_reports += reports
      session.send(b"\x1b[1;1R" * reports)
  session.send(b"echo DEFAULT-SHELL-TICKET07\nexit\n")
  start = session.read_position
  deadline = time.monotonic() + 20.0
  while True:
    output = session.read_for(0.05)
    reports = output.count(b"\x1b[6n")
    if reports:
      cursor_reports += reports
      session.send(b"\x1b[1;1R" * reports)
    observed = bytes(session.output[start:])
    marker_at = observed.find(b"DEFAULT-SHELL-TICKET07")
    if marker_at >= 0 and return_prompt in observed[marker_at:]:
      break
    if time.monotonic() >= deadline:
      session.fail("default shell did not return to csql")
  return cursor_reports


def check_default_shell_against_direct_csql(
  database: str,
  environment: dict[str, str],
  cwd: Path,
) -> None:
  csql = require_program("csql")
  configured_shell = environment.get("CUBRID_CSQL_SHELL") or environment.get("SHELL")
  if not configured_shell:
    raise AssertionError("no configured default shell is available for comparison")

  direct_environment = environment.copy()
  direct_environment["CUBRID_CSQL_PROMPT"] = "DIRECT_TICKET07"
  direct = TerminalSession(
    [csql, "-S", "-u", "dba", "--no-pager", database],
    cwd,
    direct_environment,
  )
  try:
    direct.read_until(b"DIRECT_TICKET07> ", 20)
    direct_reports = drive_default_shell(direct, b"DIRECT_TICKET07> ")
    direct.send(b";exit\r")
    if direct.wait(10) != 0:
      raise AssertionError("direct default-shell comparison session returned a nonzero status")
  finally:
    direct.close()

  wrapped = Session(
    ["--no-history", "-S", "-u", "dba", "--no-pager", database],
    environment,
    cwd,
  )
  try:
    wrapped.expect("csql-with-history>")
    wrapped_reports = drive_default_shell(wrapped, b"csql-with-history>")
    if direct_reports != wrapped_reports:
      raise AssertionError(
        "default shell cursor-report behavior differs: direct={} wrapped={}".format(
          direct_reports, wrapped_reports
        )
      )
    wrapped.send(b";exit\r")
    if wrapped.wait(10) != 0:
      raise AssertionError("wrapped default-shell comparison session returned a nonzero status")
  finally:
    wrapped.close()
  print(
    "PASS configured default shell {!r}: direct/wrapped cursor-report requests {}/{}".format(
      configured_shell, direct_reports, wrapped_reports
    )
  )


def check_running_interrupt_against_direct_csql(
  database: str,
  environment: dict[str, str],
  cwd: Path,
) -> None:
  csql = require_program("csql")
  setup = subprocess.run(
    [
      csql,
      "-S",
      "-u",
      "dba",
      "--no-pager",
      "-c",
      "create table ticket08_numbers(n integer); "
      "insert into ticket08_numbers select rownum from db_class a, db_class b limit 1000; "
      "commit;",
      database,
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=cwd,
    env=environment,
    check=False,
  )
  if setup.returncode != 0 or b"ERROR:" in setup.stdout + setup.stderr:
    raise AssertionError(
      "could not prepare the running-interrupt table:\n{}".format(
        (setup.stdout + setup.stderr).decode(errors="replace")
      )
    )

  direct_environment = environment.copy()
  direct_environment["CUBRID_CSQL_PROMPT"] = "DIRECT_INTERRUPT_TICKET08"
  query = b"select count(*) from ticket08_numbers a, ticket08_numbers b, ticket08_numbers c;\r"
  durations = {}
  for label, prompt in (
    ("direct", b"DIRECT_INTERRUPT_TICKET08> "),
    ("wrapped", b"csql-with-history>"),
  ):
    if label == "direct":
      session = TerminalSession(
        [csql, "-S", "-u", "dba", "--no-pager", database],
        cwd,
        direct_environment,
      )
    else:
      session = Session(
        ["--no-history", "-S", "-u", "dba", "--no-pager", database],
        environment,
        cwd,
      )
    try:
      session.read_until(prompt, 20)
      session.read_for(0.1)
      session.send(query)
      session.read_for(0.5)
      interrupted_at = time.monotonic()
      session.send(b"\x03")
      session.read_until(b"Has been interrupted", 15)
      durations[label] = time.monotonic() - interrupted_at
      session.read_until(prompt, 15)
      session.read_for(0.1)
      session.send(b"select 808080;\r")
      session.read_until(b"808080", 10)
      session.read_until(b"1 row selected", 10)
      session.read_until(prompt, 10)
      session.read_for(0.1)
      session.send(b";exit\r")
      if session.wait(10) != 0:
        raise AssertionError("{} interrupt comparison session returned a nonzero status".format(label))
      if session.terminal_attributes() != session.initial_attributes:
        raise AssertionError("{} interrupt comparison did not restore terminal settings".format(label))
    finally:
      session.close()

  if durations["wrapped"] > max(3.0, durations["direct"] * 3):
    raise AssertionError("wrapper delayed running-query cancellation: {!r}".format(durations))
  print("PASS running Ctrl+C direct/wrapped comparison and follow-up query: {!r}".format(durations))


def check_signal_cleanup_against_direct_csql(
  database: str,
  environment: dict[str, str],
  cwd: Path,
) -> None:
  csql = require_program("csql")
  direct_environment = environment.copy()
  direct_environment["CUBRID_CSQL_PROMPT"] = "DIRECT_SIGNAL_TICKET08"
  direct = TerminalSession(
    [csql, "-S", "-u", "dba", "--no-pager", database],
    cwd,
    direct_environment,
  )
  try:
    direct.read_until(b"DIRECT_SIGNAL_TICKET08> ", 20)
    os.kill(direct.process_id, signal.SIGTERM)
    direct_status = direct.wait(10)
    if direct.terminal_attributes() != direct.initial_attributes:
      raise AssertionError("direct csql SIGTERM did not preserve the parent terminal settings")
  finally:
    direct.close()

  wrapped = Session(
    ["--no-history", "-S", "-u", "dba", "--no-pager", database],
    environment,
    cwd,
  )
  try:
    wrapped.expect("csql-with-history>")
    children_file = Path(
      "/proc/{}/task/{}/children".format(wrapped.process_id, wrapped.process_id)
    )
    child_ids = [int(value) for value in children_file.read_text(encoding="ascii").split()]
    if len(child_ids) != 1:
      raise AssertionError("expected one real csql child, found {!r}".format(child_ids))
    csql_process_id = child_ids[0]
    os.kill(wrapped.process_id, signal.SIGTERM)
    wrapped_status = wrapped.wait(10)
    if wrapped.terminal_attributes() != wrapped.initial_attributes:
      raise AssertionError("wrapped csql SIGTERM did not preserve the parent terminal settings")
    if not wait_for_process_exit(csql_process_id):
      raise AssertionError("terminated wrapper left csql waiting for terminal input")
  finally:
    wrapped.close()

  if direct_status != 128 + signal.SIGTERM or wrapped_status != direct_status:
    raise AssertionError(
      "direct/wrapped SIGTERM status differs: direct={} wrapped={}".format(
        direct_status, wrapped_status
      )
    )
  print("PASS direct/wrapped SIGTERM status, exact terminal restoration, and csql cleanup")


def observe_catalog_interrupt(
  label: str,
  session: TerminalSession,
  prompt: bytes,
) -> CatalogInterruptObservation:
  try:
    session.read_until(prompt, 20)
    session.read_for(0.1)
    session.send(b";plan simple\r")
    session.read_until(prompt, 10)
    session.read_for(0.1)

    query_start = len(session.output)
    session.send(
      b"select count(*) from db_class a, db_class b, db_class c, "
      b"db_class d, db_class e, db_class f;\r"
    )
    session.read_for(0.5)
    session.send(b"\x03")
    deadline = time.monotonic() + 5.0
    cancelled = False
    returned = False
    while time.monotonic() < deadline:
      session.read_for(0.05)
      observed = bytes(session.output[query_start:])
      cancelled = b"Has been interrupted" in observed
      returned = prompt in observed
      if cancelled and returned:
        break

    observed = bytes(session.output[query_start:])
    plan_generated = b"Query plan:" in observed
    if cancelled and returned:
      session.read_for(0.1)
      session.send(b";exit\r")
      if session.wait(10) != 0:
        raise AssertionError("{} catalog probe returned a nonzero status".format(label))
    else:
      os.kill(session.process_id, signal.SIGTERM)
      expected_status = 128 + signal.SIGTERM
      if session.wait(10) != expected_status:
        raise AssertionError("{} catalog probe did not terminate cleanly".format(label))
    if session.terminal_attributes() != session.initial_attributes:
      raise AssertionError("{} catalog probe did not restore terminal settings".format(label))
    return CatalogInterruptObservation(cancelled and returned, plan_generated)
  finally:
    session.close()


def check_catalog_interrupt_phase_against_direct_csql(
  database: str,
  environment: dict[str, str],
  cwd: Path,
) -> None:
  csql = require_program("csql")
  direct_environment = environment.copy()
  direct_environment["CUBRID_CSQL_PROMPT"] = "DIRECT_CATALOG_TICKET08"
  direct = observe_catalog_interrupt(
    "direct",
    TerminalSession(
      [csql, "-S", "-u", "dba", "--no-pager", database],
      cwd,
      direct_environment,
    ),
    b"DIRECT_CATALOG_TICKET08> ",
  )
  wrapped = observe_catalog_interrupt(
    "wrapped",
    Session(
      ["--no-history", "-S", "-u", "dba", "--no-pager", database],
      environment,
      cwd,
    ),
    b"csql-with-history>",
  )
  if wrapped != direct:
    raise AssertionError(
      "catalog interrupt phase differs between direct and wrapped csql: "
      "direct={!r} wrapped={!r}".format(direct, wrapped)
    )
  if direct.cancelled_and_returned:
    classification = "cancelled and returned within five seconds"
  elif direct.plan_generated:
    classification = "did not return within five seconds after generating a plan (execution phase)"
  else:
    classification = "did not return within five seconds before plan generation (compilation/optimization phase)"
  print("PASS catalog cancellation direct/wrapped parity: {}".format(classification))


def check_persistent_history(database: str, environment: dict[str, str], cwd: Path) -> None:
  history_file = cwd / "persistent-history.sqlite3"
  arguments = ["--history-file", str(history_file), "-S", "-u", "dba", "--no-pager", database]

  writer = Session(arguments, environment, cwd)
  try:
    writer.expect("csql-with-history>")
    writer.submit(";singleline off", "SINGLELINE IS OFF")
    for fragment in ("select", "42;"):
      writer.send(fragment.encode("utf-8") + b"\r")
      writer.expect(fragment + "\r")
      writer.expect("csql-with-history>")
    writer.submit(";xrun", "1 row selected")
    writer.submit(";singleline on", "SINGLELINE IS ON")
    writer.submit("select no_such_ticket03_column;", "ERROR:")
    writer.send(b"select\x0a246810;\r")
    writer.expect("1 row selected")
    writer.expect("csql-with-history>")
    writer.submit(" select 112233;", "1 row selected")
    writer.send(b"\x04")
    if writer.wait(10) != 0:
      raise AssertionError("history writer returned a nonzero status")
  finally:
    writer.close()

  stored = stored_commands(history_file)
  expected = [
    ";singleline off",
    "select",
    "42;",
    ";xrun",
    ";singleline on",
    "select no_such_ticket03_column;",
    "select\n246810;",
  ]
  if stored != expected:
    raise AssertionError("unexpected retained submissions: {!r}".format(stored))

  reader = Session(arguments, environment, cwd)
  try:
    reader.expect("csql-with-history>")
    reader.send(b"\x1b[A")
    recalled = reader.read_for(0.3)
    if b"select" not in recalled or b"246810;" not in recalled:
      raise AssertionError("multiline submission was not recalled exactly")
    if b"row selected" in recalled:
      raise AssertionError("recall executed without a later submission")
    reader.send(b"\x1b[F 1 +\r")
    reader.expect("1 row selected")
    reader.expect("csql-with-history>")

    reader.send(b"select 97531;")
    reader.read_for(0.1)
    reader.send(b"\x1b[A\x1b[B\x1b[B\r")
    reader.expect("1 row selected")
    reader.expect("csql-with-history>")

    reader.send(b"unfinished\x12246810\r")
    recalled = reader.read_for(0.2)
    if b"row selected" in recalled:
      raise AssertionError("history search executed a multiline match during recall")
    reader.send(b"\x1b[F 1 +\r")
    reader.expect("1 row selected")
    reader.expect("csql-with-history>")

    reader.send(b"select 13579;\x12no_such_ticket03")
    reader.read_for(0.1)
    reader.send(b"\x1b")
    reader.read_for(0.1)
    reader.send(b"\r")
    reader.expect("13579")
    reader.expect("1 row selected")
    reader.expect("csql-with-history>")

    reader.send(b"select 97532;\x12definitely_missing_history_term\r")
    no_match = reader.read_for(0.2)
    if b"row selected" in no_match:
      raise AssertionError("no-match history search submitted the unfinished draft")
    if "(no matches)" not in "\n".join(reader.update_screen()):
      raise AssertionError("no-match history search did not render its empty result")
    reader.send(b"\x1b")
    reader.read_for(0.1)
    reader.send(b"\r")
    reader.expect("97532")
    reader.expect("1 row selected")
    reader.expect("csql-with-history>")

    reader.submit("select 55551;", "1 row selected")
    reader.submit("select 55552;", "1 row selected")
    reader.submit("select 55551;", "1 row selected")
    reader.send(b"draft\x125555")
    reader.read_for(0.2)
    search_lines = reader.update_screen()
    rendered_search = "\n".join(search_lines)
    overlay = rendered_search.rsplit("History search:", 1)[-1].split("History |", 1)[0]
    if overlay.count("select 55551;") != 1:
      raise AssertionError("repeated search result was not deduplicated: {}".format(search_lines))
    selected = next((line for line in overlay.splitlines() if line.lstrip().startswith("> ")), "")
    if "select 55551;" not in selected:
      raise AssertionError("latest repeated use was not selected first: {}".format(search_lines))
    reader.send(b"\x1b[B\r")
    selected_older = reader.read_for(0.2)
    if b"row selected" in selected_older:
      raise AssertionError("picker selection executed before a separate submit")
    reader.send(b"\r")
    reader.expect("55552")
    reader.expect("1 row selected")
    reader.expect("csql-with-history>")
    reader.send(b"\x04")
    if reader.wait(10) != 0:
      raise AssertionError("history reader returned a nonzero status")
  finally:
    reader.close()

  before_private = stored_commands(history_file)
  private = Session(["--no-history", *arguments], environment, cwd)
  try:
    private.expect("csql-with-history>")
    private.send(b"\x1b[A")
    private.read_for(0.2)
    if "select 55552;" not in "\n".join(private.update_screen()):
      raise AssertionError("--no-history did not allow read-only recall")
    private.send(b"\r")
    private.expect("1 row selected")
    private.expect("csql-with-history>")
    private.submit("select 86420;", "1 row selected")
    private.send(b"\x04")
    if private.wait(10) != 0:
      raise AssertionError("private history session returned a nonzero status")
  finally:
    private.close()
  after_private = stored_commands(history_file)
  if after_private != before_private:
    raise AssertionError("--no-history changed persistent history")
  print("PASS persistent private recall")


def check_shared_history(
  first_database: str,
  second_database: str,
  environment: dict[str, str],
  root: Path,
) -> None:
  first_directory = root / "shared-first"
  second_directory = root / "shared-second"
  first_directory.mkdir()
  second_directory.mkdir()
  history_file = root / "shared-live-history.sqlite3"
  common = ["--history-file", str(history_file), "--history-limit", "3", "-S", "-u", "dba", "--no-pager"]
  first = Session([*common, first_database], environment, first_directory)
  second = Session([*common, second_database], environment, second_directory)
  try:
    first.expect("csql-with-history>")
    second.expect("csql-with-history>")

    first.submit("select 701001;", "1 row selected")
    second.send(b"\x1b[A")
    second.read_for(0.2)
    if "select 701001;" not in "\n".join(second.update_screen()):
      raise AssertionError("live browse did not refresh another database's committed submission")
    second.send(b"\x1b[B")

    first.submit("select 701002;", "1 row selected")
    second.send(b"draft\x12701002")
    second.read_for(0.2)
    if "select 701002;" not in "\n".join(second.update_screen()):
      raise AssertionError("live search did not refresh another database's committed submission")
    second.send(b"\x1b")
    second.read_for(0.1)
    second.send(b"\x03")

    with ThreadPoolExecutor(max_workers=2) as executor:
      futures = (
        executor.submit(first.submit, "select 701003;", "1 row selected"),
        executor.submit(second.submit, "select 701004;", "1 row selected"),
      )
      for future in futures:
        future.result()

    retained = stored_commands(history_file)
    if len(retained) != 3 or set(retained) != {
      "select 701002;",
      "select 701003;",
      "select 701004;",
    }:
      raise AssertionError("unexpected concurrent retained submissions: {!r}".format(retained))
    for command in reversed(retained):
      second.send(b"\x1b[A")
      second.read_for(0.1)
      if command not in "\n".join(second.update_screen()):
        raise AssertionError("retained history was not readable in order: {!r}".format(retained))

    with closing(sqlite3.connect(history_file)) as connection:
      journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    if journal_mode != "wal":
      raise AssertionError("shared history journal mode is not WAL: {!r}".format(journal_mode))

    first.send(b"\x04")
    second.send(b"\x03\x04")
    if first.wait(10) != 0 or second.wait(10) != 0:
      raise AssertionError("shared history wrapper returned a nonzero status")
    print("PASS shared live history and retention")
  finally:
    first.close()
    second.close()


def check_memory_only_history(database: str, environment: dict[str, str], cwd: Path) -> None:
  unavailable_history = cwd / "missing-history-parent" / "unavailable.sqlite3"
  unavailable = Session(
    ["--history-file", str(unavailable_history), "-S", "-u", "dba", "--no-pager", database],
    environment,
    cwd,
  )
  try:
    unavailable.expect("newly retained entries will disappear on exit")
    unavailable.expect("csql-with-history>")
    unavailable.submit("select 801001;", "1 row selected")
    unavailable.send(b"\x1b[A")
    unavailable.read_for(0.2)
    if "select 801001;" not in "\n".join(unavailable.update_screen()):
      raise AssertionError("unavailable-destination submission was not recalled from memory")
    unavailable.send(b"\x03")
    if unavailable.finish() != 0:
      raise AssertionError("unavailable-destination session returned a nonzero status")
    if unavailable_history.exists():
      raise AssertionError("unavailable destination unexpectedly became persistent")
  finally:
    unavailable.close()

  disabled_history = cwd / "unavailable-no-history.sqlite3"
  disabled_history.mkdir()
  disabled = Session(
    ["--history-file", str(disabled_history), "--no-history", "-S", "-u", "dba", "--no-pager", database],
    environment,
    cwd,
  )
  try:
    disabled.expect("history saving remains disabled")
    disabled.expect("csql-with-history>")
    disabled.submit("select 801002;", "1 row selected")
    disabled.send(b"\x12801002")
    disabled.read_for(0.2)
    screen = "\n".join(disabled.update_screen())
    if "(no matches)" not in screen or "MEMORY-ONLY" in screen:
      raise AssertionError("storage failure weakened --no-history: {}".format(screen))
    disabled.send(b"\x1b")
    disabled.read_for(0.1)
    disabled.send(b"\x03")
    if disabled.finish() != 0:
      raise AssertionError("unavailable --no-history session returned a nonzero status")
  finally:
    disabled.close()

  history_file = cwd / "write-failure-history.sqlite3"
  arguments = ["--history-file", str(history_file), "-S", "-u", "dba", "--no-pager", database]
  failed_writer = Session(arguments, environment, cwd)
  try:
    failed_writer.expect("csql-with-history>")
    failed_writer.submit("select 802001;", "1 row selected")
    with closing(sqlite3.connect(history_file)) as blocker:
      blocker.execute("BEGIN IMMEDIATE")
      started = time.monotonic()
      failed_writer.send(b"select 802002;\r")
      failed_writer.expect("newly retained entries will disappear on exit", timeout=3.0)
      failed_writer.expect("1 row selected")
      failed_writer.expect("csql-with-history>")
      elapsed = time.monotonic() - started
      blocker.rollback()
    if elapsed < 0.2 or elapsed >= 1.5:
      raise AssertionError("writer-lock fallback was not bounded: {:.3f}s".format(elapsed))

    failed_writer.submit("select 802003;", "1 row selected")
    failed_writer.send(b"draft\x12802002")
    failed_writer.read_for(0.2)
    screen = "\n".join(failed_writer.update_screen())
    if "select 802002;" not in screen or "MEMORY-ONLY" not in screen:
      raise AssertionError("memory-only search or status was unavailable: {}".format(screen))
    failed_writer.send(b"\x1b")
    failed_writer.read_for(0.1)
    failed_writer.send(b"\x03")
    if failed_writer.finish() != 0:
      raise AssertionError("write-failure session returned a nonzero status")
  finally:
    failed_writer.close()

  if stored_commands(history_file) != ["select 802001;"]:
    raise AssertionError("memory-only submissions were retried or backfilled")
  restarted = Session(arguments, environment, cwd)
  try:
    restarted.expect("csql-with-history>")
    restarted.send(b"\x1b[A")
    restarted.read_for(0.2)
    screen = "\n".join(restarted.update_screen())
    if "select 802001;" not in screen or "802002" in screen or "802003" in screen:
      raise AssertionError("restart did not separate durable and volatile entries: {}".format(screen))
    restarted.send(b"\x03")
    if restarted.finish() != 0:
      raise AssertionError("restarted history session returned a nonzero status")
  finally:
    restarted.close()
  print("PASS memory-only history fallback")


def checked_run(
  command: Sequence[str],
  environment: dict[str, str],
  cwd: Path,
  daemon_may_inherit_output: bool = False,
) -> None:
  result = subprocess.run(
    command,
    stdout=subprocess.DEVNULL if daemon_may_inherit_output else subprocess.PIPE,
    stderr=subprocess.DEVNULL if daemon_may_inherit_output else subprocess.PIPE,
    cwd=cwd,
    env=environment,
    check=False,
    timeout=30,
  )
  if result.returncode != 0:
    stdout = b"" if result.stdout is None else result.stdout
    stderr = b"" if result.stderr is None else result.stderr
    raise RuntimeError("command failed: {}\n{}{}".format(
      " ".join(command), stdout.decode(errors="replace"), stderr.decode(errors="replace")))


def main() -> int:
  cubrid = require_program("cubrid")
  require_program("csql")

  with tempfile.TemporaryDirectory(prefix="csql-with-history-editable-") as temporary:
    root = Path(temporary)
    registry = root / "registry"
    run_directory = root / "run"
    registry.mkdir()
    run_directory.mkdir()
    databases = [
      "cwhe{:08x}a".format(os.getpid() & 0xFFFFFFFF),
      "cwhe{:08x}b".format(os.getpid() & 0xFFFFFFFF),
    ]

    environment = os.environ.copy()
    isolate_runtime(root, environment)
    environment["CUBRID_DATABASES"] = str(registry)
    environment["TERM"] = "xterm-256color"
    for index, database in enumerate(databases):
      database_directory = root / "database-{}".format(index)
      database_directory.mkdir()
      (database_directory / "lob").mkdir()
      checked_run(
        [
          cubrid,
          "createdb",
          "--db-volume-size=32M",
          "--log-volume-size=32M",
          "-F",
          str(database_directory),
          database,
          "en_US.utf8",
        ],
        environment,
        run_directory,
      )

    check_session("standalone", "-S", databases[0], environment, run_directory)
    check_password_handoff(databases[0], environment, run_directory)
    check_terminal_program_handoffs(databases[0], environment, run_directory)
    check_default_shell_against_direct_csql(databases[0], environment, run_directory)
    check_running_interrupt_against_direct_csql(databases[0], environment, run_directory)
    check_signal_cleanup_against_direct_csql(databases[0], environment, run_directory)
    check_catalog_interrupt_phase_against_direct_csql(databases[0], environment, run_directory)
    check_persistent_history(databases[0], environment, run_directory)
    check_shared_history(databases[0], databases[1], environment, root)
    check_memory_only_history(databases[0], environment, run_directory)
    checked_run([cubrid, "server", "start", databases[0]], environment, run_directory, daemon_may_inherit_output=True)
    try:
      check_session("client/server", "-C", databases[0], environment, run_directory)
    finally:
      checked_run(
        [cubrid, "server", "stop", databases[0]],
        environment,
        run_directory,
        daemon_may_inherit_output=True,
      )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

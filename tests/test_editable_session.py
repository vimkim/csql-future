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
"""External-process tests for the editable csql session."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import shlex
import signal
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = Path(os.environ.get("CSQL_WITH_HISTORY_TEST_COMMAND", str(PROJECT_ROOT / ".venv/bin/csql-with-history")))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pty_test_support import AnsiScreen, TerminalSession, wait_for_process_exit


class EditableSessionTest(unittest.TestCase):

  def setUp(self) -> None:
    temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(temporary_directory.cleanup)
    self.root = Path(temporary_directory.name)
    self.bin_directory = self.root / "bin"
    self.bin_directory.mkdir()
    self.csql = self.bin_directory / "csql"
    self.csql.write_text(
      """#!/usr/bin/env python3
import json
import os
import sys
import termios
import time
import tty

if "-c" in sys.argv:
  catalog_log = os.environ.get("SYNTHETIC_CATALOG_LOG")
  if catalog_log:
    with open(catalog_log, "a") as stream:
      stream.write(json.dumps({"pid": os.getpid(), "arguments": sys.argv[1:]}) + "\\n")
  time.sleep(float(os.environ.get("SYNTHETIC_CATALOG_DELAY", "0")))
  failure_file = os.environ.get("SYNTHETIC_CATALOG_FAIL_FILE")
  if os.environ.get("SYNTHETIC_CATALOG_FAIL") or failure_file and os.path.exists(failure_file) or "SYNTHETIC_CATALOG" not in os.environ:
    sys.exit(1)
  catalog_file = os.environ.get("SYNTHETIC_CATALOG_FILE")
  if catalog_file:
    with open(catalog_file) as stream:
      catalog = stream.read()
  else:
    catalog = os.environ["SYNTHETIC_CATALOG"]
  print(catalog, flush=True)
  sys.exit(0)

prompt = os.environ.get("CUBRID_CSQL_PROMPT", "csql") + "> "
command_buffer = []
automatic = True
pid_file = os.environ.get("SYNTHETIC_PID_FILE")
if pid_file is not None:
  with open(pid_file + ".tmp", "w", encoding="ascii") as stream:
    stream.write(str(os.getpid()))
  os.replace(pid_file + ".tmp", pid_file)
expected_password = os.environ.get("SYNTHETIC_PASSWORD")
startup_status = os.environ.get("SYNTHETIC_STARTUP_STATUS")
if startup_status is not None:
  sys.exit(int(startup_status))
if expected_password is not None:
  previous = termios.tcgetattr(0)
  attributes = termios.tcgetattr(0)
  attributes[3] &= ~termios.ECHO
  termios.tcsetattr(0, termios.TCSANOW, attributes)
  try:
    sys.stdout.write("Password: ")
    sys.stdout.flush()
    supplied_password = sys.stdin.readline().rstrip("\\r\\n")
  finally:
    termios.tcsetattr(0, termios.TCSADRAIN, previous)
  if supplied_password != expected_password:
    print("AUTHENTICATION-FAILED", flush=True)
    sys.exit(1)
  print("AUTHENTICATED", flush=True)
print("Synthetic csql ready", flush=True)

while True:
  previous = termios.tcgetattr(0)
  sys.stdout.write(prompt)
  sys.stdout.flush()
  time.sleep(0.03)
  tty.setraw(0)
  line = bytearray()
  while True:
    character = os.read(0, 1)
    if character in (b"\\r", b"\\n"):
      break
    if character == b"\\x04" and not line:
      termios.tcsetattr(0, termios.TCSADRAIN, previous)
      sys.exit(0)
    line.extend(character)
  termios.tcsetattr(0, termios.TCSADRAIN, previous)
  text = line.decode()
  print(text, flush=True)
  if text == ";exit":
    sys.exit(0)
  if text == ";size":
    size = os.get_terminal_size(0)
    print("CSQL-SIZE={}x{}".format(size.lines, size.columns), flush=True)
    continue
  if text == ";singleline off":
    automatic = False
    print("SINGLELINE IS OFF", flush=True)
    continue
  if text == ";singleline on":
    automatic = True
    print("SINGLELINE IS ON", flush=True)
    continue
  if text == ";xrun":
    print("EXECUTED=" + json.dumps(command_buffer), flush=True)
    command_buffer.clear()
    continue
  if text == ";shell":
    status = os.system(os.environ["CUBRID_CSQL_SHELL"])
    print("SHELL-STATUS={}".format(status), flush=True)
    continue
  if text == ";rawhandoff":
    os.system(os.environ["SYNTHETIC_RAW_HANDOFF"])
    continue
  command_buffer.append(text)
  if text == "promptlike;":
    print(prompt, flush=True)
    time.sleep(0.35)
    print("PROMPT-LIKE WORK FINISHED", flush=True)
  elif text == "quiet;":
    time.sleep(0.35)
    print("QUIET WORK FINISHED", flush=True)
  elif text == "slow;":
    try:
      time.sleep(10)
    except KeyboardInterrupt:
      print("ERROR: synthetic interrupted", flush=True)
  elif text == "bad;":
    print("ERROR: synthetic failure", flush=True)
  if automatic and text.rstrip().endswith(";"):
    print("EXECUTED=" + json.dumps(command_buffer), flush=True)
    command_buffer.clear()
""",
      encoding="utf-8",
    )
    self.csql.chmod(0o755)
    self.raw_handoff = self.bin_directory / "raw-handoff"
    self.raw_handoff.write_text(
      """#!/usr/bin/env python3
import os
import sys
import termios
import time
import tty

previous = termios.tcgetattr(0)
try:
  tty.setraw(0)
  sys.stdout.write(os.environ["CUBRID_CSQL_PROMPT"] + "> ")
  sys.stdout.flush()
  time.sleep(0.35)
  size = os.get_terminal_size(0)
  print("RAW-HANDOFF-SIZE={}x{}".format(size.lines, size.columns), flush=True)
  print("RAW-HANDOFF-FINISHED", flush=True)
finally:
  termios.tcsetattr(0, termios.TCSADRAIN, previous)
""",
      encoding="utf-8",
    )
    self.raw_handoff.chmod(0o755)
    self.environment = os.environ.copy()
    self.environment["PATH"] = os.pathsep.join((str(self.bin_directory), self.environment.get("PATH", "")))
    self.environment["SYNTHETIC_RAW_HANDOFF"] = str(self.raw_handoff)
    self.environment["SYNTHETIC_CATALOG_LOG"] = str(self.root / "catalog.log")

  def enable_catalog(self) -> None:
    self.environment['SYNTHETIC_CATALOG'] = '\n'.join((
      'kind\tlogin_name\towner_name\tclass_name\titem_name\titem_type',
      'relation\tDBA\tDBA\tcode\tcode\tCLASS',
      'relation\tDBA\tDBA\tcoding\tcoding\tCLASS',
      'column\tDBA\tDBA\tcode\tname\tINSTANCE',
      'column\tDBA\tDBA\tcoding\tlanguage\tINSTANCE',
    ))

  def start(
    self,
    arguments: list[str] | None = None,
    cwd: Path | None = None,
    database: str = "synthetic_db",
  ) -> TerminalSession:
    session = TerminalSession(
      [str(WRAPPER), *(arguments or []), database],
      cwd or self.root,
      self.environment,
    )
    self.addCleanup(session.close)
    return session

  def stored_commands(self, path: Path | None = None) -> list[str]:
    selected = path or self.root / ".csql_history.sqlite3"
    with closing(sqlite3.connect(selected)) as connection:
      return [row[0] for row in connection.execute("SELECT command FROM submissions ORDER BY id")]

  def rendered_screen(self, session: TerminalSession) -> str:
    screen = AnsiScreen(rows=24, columns=100)
    screen.feed(bytes(session.output))
    return "\n".join(screen.display())

  def configure_editor(self, body: str) -> Path:
    editor = self.bin_directory / "draft editor.py"
    editor.write_text(
      "import json, os, sys, termios, tty\nfrom pathlib import Path\n"
      "path = Path(sys.argv[-1])\n" + body,
      encoding="utf-8",
    )
    self.environment.pop("VISUAL", None)
    self.environment["EDITOR"] = shlex.join([sys.executable, str(editor)])
    return editor

  def test_external_editor_returns_editable_multiline_text_without_execution_or_history(self) -> None:
    record = self.root / "editor-record.json"
    self.environment["EDITOR_RECORD"] = str(record)
    editor = self.configure_editor(
      "attributes = termios.tcgetattr(0)\n"
      "Path(os.environ['EDITOR_RECORD']).write_text(json.dumps({\n"
      "  'text': path.read_text(), 'argv': sys.argv[1:-1], 'path': str(path),\n"
      "  'tty': all(os.isatty(fd) for fd in (0, 1, 2)),\n"
      "  'foreground': os.tcgetpgrp(0) == os.getpgrp(),\n"
      "  'canonical': bool(attributes[3] & termios.ICANON),\n"
      "  'echo': bool(attributes[3] & termios.ECHO)}))\n"
      "input('DRAFT-EDITOR-READY> ')\n"
      "path.write_text(\"select\\n'편집';\\n\", encoding='utf-8')\n"
      "tty.setraw(0)\n"
    )
    self.environment["VISUAL"] = shlex.join([sys.executable, str(editor), "quoted flag"])
    self.environment["EDITOR"] = "/missing/should-not-run"
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send("select\x0a'한글';\x02\x18".encode())
    self.assertNotIn(b"DRAFT-EDITOR-READY", session.read_for(0.05))
    session.send(b"\x05")
    session.read_until(b"DRAFT-EDITOR-READY>")
    captured = json.loads(record.read_text())
    self.assertEqual("select\n'한글';\n", captured["text"])
    self.assertEqual(["quoted flag"], captured["argv"])
    for key in ("tty", "foreground", "canonical", "echo"):
      self.assertTrue(captured[key], captured)
    self.assertEqual([], self.stored_commands())
    session.send(b"private-editor-keys\n")
    returned = session.read_until(b"csql-with-history>") + session.read_for(0.05)
    self.assertNotIn(b"EXECUTED", returned)
    self.assertIn("'편집';", self.rendered_screen(session))
    self.assertFalse(Path(captured["path"]).exists())
    self.assertEqual([], self.stored_commands())
    session.send(b"\x02!\r")
    session.read_until(("EXECUTED=" + json.dumps(["select", "'편집'!;"])).encode())
    session.read_until(b"csql-with-history>")
    self.assertEqual(["select\n'편집'!;"], self.stored_commands())
    session.send(b"\x11")
    self.assertEqual(0, session.wait())
    self.assertEqual(session.initial_attributes, session.terminal_attributes())

  def test_external_editor_failures_preserve_draft_and_cursor(self) -> None:
    cases = (
      ("missing", "", "/no/such/editor", b"cannot edit draft"),
      ("invalid command", "", "'unclosed", b"cannot edit draft"),
      ("empty command", "", "   ", b"cannot edit draft"),
      ("nonzero", "path.write_text('discard changes')\nsys.exit(7)\n", None, b"status 7"),
      ("deleted file", "path.unlink()\n", None, b"cannot edit draft"),
      ("invalid UTF-8", "path.write_bytes(b'\\xff')\n", None, b"cannot edit draft"),
    )
    for label, body, command, expected in cases:
      with self.subTest(case=label):
        self.configure_editor(body)
        if command is not None:
          self.environment["EDITOR"] = command
        session = self.start()
        session.read_until(b"csql-with-history>")
        session.send(b"select 1;\x02\x18\x05")
        session.read_until(expected)
        session.read_until(b"csql-with-history>")
        session.send(b"2\r")
        session.read_until(b'EXECUTED=["select 12;"]')
        session.read_until(b"csql-with-history>")
        session.send(b"\x11")
        self.assertEqual(0, session.wait())
        self.assertEqual(session.initial_attributes, session.terminal_attributes())
    self.assertEqual(["select 12;"], self.stored_commands())

  def test_unchanged_external_edit_preserves_cursor_trailing_newlines_and_empty_draft(self) -> None:
    self.configure_editor("print('UNCHANGED-EDITOR-RETURN', flush=True)\n")
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"\x18\x05")
    session.read_until(b"UNCHANGED-EDITOR-RETURN")
    session.read_until(b"csql-with-history>")
    self.assertEqual([], self.stored_commands())
    session.send(b"select 1;\x0a\x1b[A\x05\x02\x18\x05")
    session.read_until(b"UNCHANGED-EDITOR-RETURN")
    session.read_until(b"csql-with-history>")
    session.send(b"2\r")
    session.read_until(b'EXECUTED=["select 12;"]')
    session.read_until(b"csql-with-history>")
    self.assertEqual(["select 12;\n"], self.stored_commands())

  def test_external_editor_defaults_to_vi_and_prefix_preserves_other_keys(self) -> None:
    editor = self.configure_editor(
      "print('DEFAULT-EDITOR-RETURN', flush=True)\n"
      "path.write_text('select 81;\\n')\n"
    )
    vi = self.bin_directory / "vi"
    vi.write_text("#!/usr/bin/env python3\n" + editor.read_text())
    vi.chmod(0o755)
    self.environment.pop("EDITOR")
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select 4\x182;\r")
    session.read_until(b'EXECUTED=["select 42;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x18\x05")
    session.read_until(b"DEFAULT-EDITOR-RETURN")
    session.read_until(b"csql-with-history>")
    session.send(b"\r")
    session.read_until(b'EXECUTED=["select 81;"]')
    self.assertEqual(["select 42;", "select 81;"], self.stored_commands())

  def test_resize_during_external_edit_restores_one_prompt_at_current_dimensions(self) -> None:
    self.configure_editor(
      "input('RESIZE-EDITOR-READY> ')\n"
      "size = os.get_terminal_size(0)\n"
      "print('EDITOR-SIZE={}x{}'.format(size.lines, size.columns), flush=True)\n"
      "path.write_text('select ' + '7' * 70 + ';\\n')\n"
    )
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    screen = AnsiScreen()
    screen.feed(bytes(session.output))
    session.send(b"\x18")
    screen.feed(session.read_for(0.05))
    session.set_size(12, 50)
    screen.resize(12, 50)
    session.send(b"\x05")
    screen.feed(session.read_until(b"RESIZE-EDITOR-READY>"))
    screen.feed(session.read_for(0.05))
    session.set_size(8, 40)
    screen.resize(8, 40)
    session.send(b"\n")
    screen.feed(session.read_until(b"EDITOR-SIZE=8x40"))
    screen.feed(session.read_until(b"csql-with-history>"))
    screen.feed(session.read_for(0.05))
    self.assertEqual(1, sum("csql-with-history>" in line for line in screen.display()), screen.display())
    self.assertEqual(1, sum("Input mode" in line for line in screen.display()), screen.display())
    self.assertEqual([], self.stored_commands())
    session.send(b"\r")
    session.read_until(b'EXECUTED=["select ' + b"7" * 70 + b';"]')
    session.read_until(b"csql-with-history>")
    session.send(b";size\r")
    session.read_until(b"CSQL-SIZE=8x40")

  def test_interrupted_external_editor_keeps_draft_and_resumes_input(self) -> None:
    self.configure_editor("input('INTERRUPT-EDITOR-READY> ')\n")
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select 42;\x18\x05")
    session.read_until(b"INTERRUPT-EDITOR-READY>")
    session.send(b"\x03")
    session.read_until(b"draft kept")
    session.read_until(b"csql-with-history>")
    session.send(b"\r")
    session.read_until(b'EXECUTED=["select 42;"]')
    self.assertEqual(["select 42;"], self.stored_commands())

  def test_termination_during_external_edit_reaps_editor_and_csql(self) -> None:
    editor_pid = self.root / "editor.pid"
    csql_pid = self.root / "csql.pid"
    record = self.root / "editor-path"
    self.environment.update(EDITOR_PID=str(editor_pid), SYNTHETIC_PID_FILE=str(csql_pid),
                            EDITOR_PATH=str(record))
    self.configure_editor(
      "Path(os.environ['EDITOR_PID']).write_text(str(os.getpid()))\n"
      "Path(os.environ['EDITOR_PATH']).write_text(str(path))\n"
      "input('TERMINATE-EDITOR-READY> ')\n"
    )
    for signum in (signal.SIGHUP, signal.SIGTERM):
      with self.subTest(signal=signum):
        session = self.start()
        session.read_until(b"csql-with-history>")
        session.send(b"unsaved\x18\x05")
        session.read_until(b"TERMINATE-EDITOR-READY>")
        os.kill(session.process_id, signum)
        self.assertEqual(128 + signum, session.wait())
        self.assertEqual(session.initial_attributes, session.terminal_attributes())
        for path in (editor_pid, csql_pid):
          self.assertTrue(wait_for_process_exit(int(path.read_text())))
        self.assertFalse(Path(record.read_text()).exists())
    self.assertEqual([], self.stored_commands())

  def test_ctrl_w_deletes_the_previous_word(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select wrong\x17right;\r")
    session.read_until(b'EXECUTED=["select right;"]')
    self.assertEqual(["select right;"], self.stored_commands())

  def test_completion_menu_accepts_without_execution_and_keeps_history_keys(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"se\t")
    session.read_until(b"Completion |")
    self.assertIn("SELECT", self.rendered_screen(session))
    session.send(b"\x0e\x10\r")
    session.read_for(0.1)
    self.assertEqual([], self.stored_commands())
    self.assertNotIn(b"EXECUTED=", bytes(session.output))
    session.send(b" 42;\r")
    session.read_until(b'EXECUTED=["SELECT 42;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x10\r")
    session.read_until(b'EXECUTED=["SELECT 42;"]')
    self.assertEqual(["SELECT 42;"], self.stored_commands())

  def test_show_syntax_completion_works_without_metadata_and_accepts_before_semicolon(self) -> None:
    session = self.start(['-S'])
    session.read_until(b'csql-with-history>')
    session.send(b'sho\t')
    session.read_until(b'> SHOW  keyword')
    session.send(b'\r ta;\x02\t')
    session.read_until(b'> TABLES  keyword')
    session.send(b'\r')
    session.read_for(0.1)
    self.assertEqual([], self.stored_commands())
    self.assertNotIn(b'EXECUTED=', bytes(session.output))
    self.assertIn('csql-with-history> SHOW TABLES;', self.rendered_screen(session))
    session.send(b'\r')
    session.read_until(b'EXECUTED=["SHOW TABLES;"]')
    self.assertEqual(['SHOW TABLES;'], self.stored_commands())

  def test_show_columns_completion_uses_both_connectors_and_cached_relations(self) -> None:
    self.enable_catalog()
    session = self.start(['-C'])
    session.read_until(b'csql-with-history>')
    commands = []
    for prefix, partial, connector in (('show columns ', b'f', 'FROM'),
                                       ('show full columns ', b'i', 'IN')):
      session.send(prefix.encode() + partial + b'\t')
      session.read_until(('> ' + connector + '  keyword').encode())
      session.send(b'\r co\t')
      session.read_until(b'> code  table DBA')
      session.send(b'\x0e\r')
      session.read_for(0.1)
      self.assertEqual(commands, self.stored_commands())
      command = prefix + connector + ' coding;'
      session.send(b';\r')
      session.read_until(('EXECUTED=' + json.dumps([command])).encode())
      session.read_until(b'csql-with-history>')
      commands.append(command)
    self.assertEqual(commands, self.stored_commands())
    self.assertEqual(1, len((self.root / 'catalog.log').read_text().splitlines()))

  def test_show_completion_cancel_preserves_draft_and_filters_do_not_offer_table_columns(self) -> None:
    self.enable_catalog()
    session = self.start(['-S'])
    session.read_until(b'csql-with-history>')
    session.send(b'show ta\t')
    session.read_until(b'> TABLES  keyword')
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'bles;\r')
    session.read_until(b'EXECUTED=["show tables;"]')
    session.read_until(b'csql-with-history>')
    session.send(b'show columns from code where na\t')
    session.read_until(b'(no completions)')
    self.assertNotIn('name  column', self.rendered_screen(session))
    self.assertEqual(['show tables;'], self.stored_commands())

  def test_completion_help_preserves_selection_and_external_editor_remains_available(self) -> None:
    self.enable_catalog()
    self.configure_editor("print('COMPLETION-EDITOR-RETURN', flush=True)\npath.write_text('select edited;\\n')\n")
    session = self.start(['-C'])
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'> code  table DBA')
    session.send(b'\x0e\x1bOP')
    session.read_for(0.05)
    screen = self.rendered_screen(session)
    self.assertIn('Shortcuts: Completion mode', screen)
    self.assertIn('Enter: accept without executing SQL', screen)
    session.send(b'\x1bOP\r;\r')
    session.read_until(b'EXECUTED=["select * from coding;"]')
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'> code  table DBA')
    session.send(b'\x18\x05')
    session.read_until(b'COMPLETION-EDITOR-RETURN')
    session.read_until(b'csql-with-history>')
    self.assertEqual(['select * from coding;'], self.stored_commands())
    session.send(b'\r')
    session.read_until(b'EXECUTED=["select edited;"]')

  def test_completion_cancel_and_no_match_preserve_the_draft(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"se\t\x0e\x1b")
    session.read_for(0.15)
    session.send(b"lect 43;\r")
    session.read_until(b'EXECUTED=["select 43;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"nonesuch\t\r")
    session.read_until(b"(no completions)")
    session.read_for(0.1)
    self.assertEqual(["select 43;"], self.stored_commands())
    session.send(b"\x1b")
    session.read_for(0.1)
    session.send(b";\r")
    session.read_until(b'EXECUTED=["nonesuch;"]')

  def test_catalog_completion_updates_the_open_menu_and_reuses_the_cache(self) -> None:
    self.enable_catalog()
    session = self.start(['-C', '-u', 'dba'])
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'> code  table DBA')
    self.assertEqual([], self.stored_commands())
    session.send(b'\x0e\r;\r')
    session.read_until(b'EXECUTED=["select * from coding;"]')
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'> code  table DBA')
    self.assertEqual(1, len((self.root / 'catalog.log').read_text().splitlines()))
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'\x03;refresh-completions\r')
    session.read_until(b'csql-with-history>')
    session.read_for(0.2)
    self.assertEqual(2, len((self.root / 'catalog.log').read_text().splitlines()))
    self.assertEqual(['select * from coding;'], self.stored_commands())

  def test_catalog_wait_does_not_block_editing_and_exit_cancels_the_process(self) -> None:
    self.enable_catalog()
    self.environment['SYNTHETIC_CATALOG_DELAY'] = '30'
    session = self.start(['-C'])
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'Loading schema')
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'ding;\r')
    session.read_until(b'EXECUTED=["select * from coding;"]', timeout=1)
    session.send(b'\x11')
    self.assertEqual(0, session.wait(2))
    record = json.loads((self.root / 'catalog.log').read_text().splitlines()[0])
    wait_for_process_exit(record['pid'])

  def test_catalog_deadline_stops_the_query_and_preserves_sql_input(self) -> None:
    self.enable_catalog()
    self.environment['SYNTHETIC_CATALOG_DELAY'] = '30'
    session = self.start(['-C'])
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'Schema unavailable; keywords only', timeout=5)
    record = json.loads((self.root / 'catalog.log').read_text().splitlines()[0])
    wait_for_process_exit(record['pid'])
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'de;\r')
    session.read_until(b'EXECUTED=["select * from code;"]')
    self.assertEqual(['select * from code;'], self.stored_commands())

  def test_no_completion_option_preserves_literal_tab_and_skips_metadata(self) -> None:
    session = self.start(['--no-completion', '-S'])
    session.read_until(b'csql-with-history>')
    session.send(b'select\t42;\r')
    session.read_until(b'EXECUTED=["select\\t42;"]')
    self.assertFalse((self.root / 'catalog.log').exists())

  def test_completion_preserves_literal_tab_on_a_later_line_and_inside_strings(self) -> None:
    session = self.start()
    session.read_until(b'csql-with-history>')
    session.send(b'select\x0a\t42;\r')
    session.read_until(b'EXECUTED=["select", "\\t42;"]')
    session.read_until(b'csql-with-history>')
    session.send(b"select 'co\tding';\r")
    session.read_until(b'EXECUTED=["select \'co\\tding\';"]')

  def test_standalone_snapshot_finishes_before_input_and_never_refreshes_live(self) -> None:
    self.enable_catalog()
    self.environment['SYNTHETIC_CATALOG_DELAY'] = '0.1'
    session = self.start(['-S', '-u', 'dba'])
    session.read_until(b'csql-with-history>')
    record = json.loads((self.root / 'catalog.log').read_text())
    wait_for_process_exit(record['pid'])
    self.assertEqual('-S', record['arguments'][0])
    session.send(b'select * from co\t')
    session.read_until(b'> code  table DBA')
    session.send(b'\x0e\r;\r')
    session.read_until(b'EXECUTED=["select * from coding;"]')
    session.read_until(b'csql-with-history>')
    session.send(b';refresh-completions\r')
    session.read_until(b'csql-with-history>')
    session.read_for(0.1)
    session.send(b'select * from co\t')
    session.read_until(b'restart to refresh schema')
    self.assertEqual(1, len((self.root / 'catalog.log').read_text().splitlines()))

  def test_failed_standalone_snapshot_keeps_interactive_password_input_owned_by_csql(self) -> None:
    self.environment['SYNTHETIC_CATALOG_FAIL'] = '1'
    self.environment['SYNTHETIC_PASSWORD'] = 'test-only-password'
    session = self.start(['-S', '-u', 'dba'])
    session.read_until(b'Password: ')
    session.send(b'test-only-password\r')
    session.read_until(b'csql-with-history>')
    session.send(b'sel\t')
    session.read_until(b'> SELECT  keyword')
    session.send(b'\r 42;\r')
    session.read_until(b'EXECUTED=["SELECT 42;"]')
    self.assertEqual(['SELECT 42;'], self.stored_commands())
    self.assertNotIn(b'test-only-password', bytes(session.output))

  def test_refresh_failure_keeps_cached_names_and_a_later_refresh_recovers(self) -> None:
    self.enable_catalog()
    failure_file = self.root / 'fail-catalog'
    catalog_file = self.root / 'catalog.tsv'
    catalog_file.write_text(self.environment['SYNTHETIC_CATALOG'])
    self.environment['SYNTHETIC_CATALOG_FAIL_FILE'] = str(failure_file)
    self.environment['SYNTHETIC_CATALOG_FILE'] = str(catalog_file)
    session = self.start(['-C'])
    session.read_until(b'csql-with-history>')
    session.send(b'select * from co\t')
    session.read_until(b'> code  table DBA')
    failure_file.touch()
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'\x03;refresh-completions\r')
    session.read_for(0.15)
    session.send(b'select * from co\t')
    session.read_until(b'Schema refresh failed; using cached names')
    self.assertIn('coding', self.rendered_screen(session))
    failure_file.unlink()
    catalog_file.write_text(self.environment['SYNTHETIC_CATALOG'].replace('coding', 'coder'))
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'\x03;refresh-completions\r')
    session.read_for(0.15)
    session.send(b'select * from co\t')
    session.read_until(b'coder  table DBA')
    self.assertEqual([], self.stored_commands())

  def test_completion_menu_resizes_and_keeps_multiline_draft_and_help_search_modes(self) -> None:
    self.enable_catalog()
    session = self.start(['-C'])
    session.read_until(b'csql-with-history>')
    session.send(b'select *\x0afrom co\t')
    session.read_until(b'> code  table DBA')
    position = len(session.output)
    session.set_size(7, 38)
    resized = session.read_for(0.15)
    self.assertIn(b'Completion', resized)
    session.send(b'\x0e\r;\r')
    session.read_until(b'EXECUTED=["select *", "from coding;"]')
    session.read_until(b'csql-with-history>')
    session.read_for(0.05)
    screen = AnsiScreen(rows=7, columns=38)
    screen.feed(bytes(session.output[position:]))
    self.assertEqual(1, sum('csql-with-history>' in line for line in screen.display()))
    session.send(b'\x12coding')
    session.read_until(b'History search:')
    session.send(b'\r')
    session.read_for(0.1)
    session.send(b'\r')
    session.read_until(b'EXECUTED=["select *", "from coding;"]')

  def test_unix_editing_keys_preserve_the_draft_around_the_cursor(self) -> None:
    cases = (
      (b"select 12;\x01\x06\x06\x05\x02\x02\x04\r", "select 1;"),
      (b"select 12;\x08\x7f;\r", "select 1;"),
      (b"select wrong   \x17right;\r", "select right;"),
      (b"wrong tail;\x01\x06\x06\x06\x06\x06\x15select\x05\r", "select tail;"),
      (b"select wrong;\x01\x06\x06\x06\x06\x06\x06\x06\x0b42;\r", "select 42;"),
      (b"select 42;\x17\x19\r", "select 42;"),
      (b"seletc\x14 42;\r", "select 42;"),
      ("select 한글".encode() + b"\x08;\r", "select 한;"),
    )
    session = self.start()
    session.read_until(b"csql-with-history>")
    for keys, expected in cases:
      with self.subTest(keys=keys):
        session.send(keys)
        # Synthetic csql uses json.dumps' default ASCII escaping for Unicode.
        session.read_until(("EXECUTED=" + json.dumps([expected])).encode())
        session.read_until(b"csql-with-history>")

    session.send(b"select\x0awrong\x15right;\r")
    session.read_until(b'EXECUTED=["select", "right;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"select\x0awrong\x01\x0b42;\r")
    session.read_until(b'EXECUTED=["select", "42;"]')

  def test_ctrl_enter_encodings_insert_newlines_without_consuming_following_text(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    for newline in (b"\n", b"\x1b[13;5u", b"\x1b[27;5;13~"):
      with self.subTest(newline=newline):
        session.send(b"select" + newline + b"42;\r")
        session.read_until(b'EXECUTED=["select", "42;"]')
        session.read_until(b"csql-with-history>")
    self.assertEqual(["select\n42;"], self.stored_commands())

  def test_ctrl_n_and_ctrl_p_select_history_and_restore_a_multiline_draft(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    for command in (b"select older;", b"select newer;"):
      session.send(command + b"\r")
      session.read_until(b'EXECUTED=["' + command + b'"]')
      session.read_until(b"csql-with-history>")
    session.send(b"select\x0adraft;\x02\x10\x10\x0e\x0e!\r")
    session.read_until(b'EXECUTED=["select", "draft!;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"unfinished\x12select\x0e\x0e\x10\r")
    recalled = session.read_for(0.05)
    self.assertNotIn(b"EXECUTED", recalled)
    self.assertNotIn("History search:", self.rendered_screen(session))
    session.send(b"\r")
    session.read_until(b'EXECUTED=["select newer;"]')

  def test_unix_editing_keys_work_in_the_history_query(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select target;\r")
    session.read_until(b'EXECUTED=["select target;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x12wrong\x17targt\x02e\x05\r\r")
    session.read_until(b'EXECUTED=["select target;"]')

  def test_long_history_query_keeps_the_cursor_visible_while_editing(self) -> None:
    session = self.start()
    session.set_size(8, 28)
    session.read_until(b"csql-with-history>")
    session.send(b"select " + b"x" * 50 + b";\r")
    session.read_until(b'EXECUTED=["select ' + b"x" * 50 + b';"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x12" + b"x" * 50)
    screen = AnsiScreen(rows=8, columns=28)
    screen.feed(session.read_for(0.05))
    self.assertLess(screen.column, 28)
    session.send(b"\x01\x06\x06\x06")
    screen.feed(session.read_for(0.05))
    self.assertEqual(3, screen.column)
    session.send(b"\x15\x0btarget\x17\x19")
    screen.feed(session.read_for(0.05))
    self.assertEqual(6, screen.column)

  def test_question_mark_opens_shortcuts_and_leaves_sql_question_marks_literal(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    initial = self.rendered_screen(session)
    self.assertIn("? shortcuts", initial)
    self.assertNotIn("Alt+Enter", initial)
    session.send(b"?")
    session.read_for(0.05)
    help_screen = self.rendered_screen(session)
    for key in ("Shortcuts: Input mode", "Ctrl+R", "Ctrl+Enter", "Ctrl+X Ctrl+E", "Ctrl+Q", "Ctrl+N", "Ctrl+P"):
      self.assertIn(key, help_screen)
    self.assertNotIn("Enter: recall", help_screen)
    self.assertNotIn("csql-with-history> ?", help_screen)
    session.send(b"\x1b[6~")
    session.read_for(0.05)
    self.assertIn("Text editing:", self.rendered_screen(session))
    self.assertIn("Ctrl+W", self.rendered_screen(session))
    session.send(b"\x1b")
    session.read_for(0.1)
    self.assertNotIn("Shortcuts", self.rendered_screen(session))
    session.send(b"select '?';\r")
    session.read_until(b"EXECUTED=[\"select '?';\"]")
    self.assertEqual(["select '?';"], self.stored_commands())

  def test_status_keeps_history_search_and_quit_discoverable(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    screen = self.rendered_screen(session)
    self.assertIn("Ctrl+R history", screen)
    self.assertIn("Ctrl+Q quit", screen)
    session.send(b"\x12")
    session.read_for(0.05)
    screen = self.rendered_screen(session)
    self.assertIn("Ctrl+Q quit", screen)
    self.assertIn("Enter recall", screen)
    self.assertIn("Esc back", screen)

  def test_primary_status_keys_remain_visible_in_a_narrow_terminal(self) -> None:
    session = self.start()
    session.set_size(8, 28)
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    screen = AnsiScreen(rows=8, columns=28)
    screen.feed(bytes(session.output))
    for hint in ("Input mode", "Ctrl+R history", "Ctrl+Q quit"):
      self.assertIn(hint, "\n".join(screen.display()))
    session.send(b"\x12")
    screen.feed(session.read_for(0.05))
    for hint in ("History search mode", "Ctrl+Q quit", "Enter recall"):
      self.assertIn(hint, "\n".join(screen.display()))

  def test_history_search_displays_persisted_age_and_recalls_only_query_text(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select timestamped;\r")
    session.read_until(b'EXECUTED=["select timestamped;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x11")
    self.assertEqual(0, session.wait())
    with closing(sqlite3.connect(self.root / ".csql_history.sqlite3")) as connection:
      connection.execute("UPDATE submissions SET submitted_at=?", (time.time() - 180,))
      connection.commit()
    restarted = self.start()
    restarted.read_until(b"csql-with-history>")
    restarted.send(b"\x12timestamped")
    restarted.read_for(0.05)
    self.assertIn("(3 min ago)", self.rendered_screen(restarted))
    restarted.send(b"\r\r")
    restarted.read_until(b'EXECUTED=["select timestamped;"]')
    restarted.read_until(b"csql-with-history>")
    restarted.send(b"\x12")
    restarted.read_for(0.05)
    self.assertIn("(just now)", self.rendered_screen(restarted))
    self.assertEqual(["select timestamped;"], self.stored_commands())

  def test_short_help_preview_starts_with_history_search_and_scrolls_in_place(self) -> None:
    session = self.start()
    session.set_size(8, 80)
    session.read_until(b"csql-with-history>")
    session.send(b"?")
    session.read_for(0.05)
    screen = AnsiScreen(rows=8, columns=80)
    screen.feed(bytes(session.output))
    self.assertIn("Ctrl+R: Search query history (enters history search mode)", "\n".join(screen.display()))
    title_row = next(row for row, line in enumerate(screen.display()) if "Shortcuts:" in line)
    session.send(b"\x1b[6~")
    screen.feed(session.read_for(0.05))
    self.assertIn("Shortcuts: Input mode", screen.display()[title_row])
    self.assertNotIn("Ctrl+R: Search query history", "\n".join(screen.display()))
    session.send(b"\x1b[F")
    screen.feed(session.read_for(0.05))
    self.assertIn("Ctrl+L: redraw", "\n".join(screen.display()))
    session.send(b"\x1b[H")
    screen.feed(session.read_for(0.05))
    self.assertIn("Ctrl+R: Search query history", "\n".join(screen.display()))
    self.assertNotIn(b"\x1b[?1049", session.output)

  def test_help_preview_preserves_draft_and_frame_through_scroll_and_resize(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select transcript;\r")
    session.read_until(b'EXECUTED=["select transcript;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"select 1;\x02\x1bOP")
    session.read_for(0.05)
    screen = AnsiScreen()
    screen.feed(bytes(session.output))
    self.assertIn('EXECUTED=["select transcript;"]', "\n".join(screen.display()))
    draft_row = next(row for row, line in enumerate(screen.display()) if "csql-with-history>" in line)
    title_row = draft_row + 1
    footer_row = next(row for row, line in enumerate(screen.display()) if "PgUp/PgDn page" in line)
    footer = screen.display()[footer_row]
    session.send(b"\x1b[F")
    screen.feed(session.read_for(0.05))
    self.assertIn("select 1;", screen.display()[draft_row])
    self.assertIn("Shortcuts: Input mode", screen.display()[title_row])
    self.assertEqual(footer, screen.display()[footer_row])
    self.assertIn("Ctrl+L: redraw", "\n".join(screen.display()))
    session.send(b"\x1b[5~\x1b[H")
    screen.feed(session.read_for(0.05))
    self.assertIn("Ctrl+R: Search query history", "\n".join(screen.display()))
    session.set_size(9, 40)
    screen.resize(9, 40)
    screen.feed(session.read_for(0.1))
    self.assertEqual(1, sum("csql-with-history>" in line for line in screen.display()))
    self.assertIn("Shortcuts: Input mode", "\n".join(screen.display()))
    session.send(b"\x1b[F")
    screen.feed(session.read_for(0.05))
    self.assertIn("Ctrl+L: redraw", "\n".join(screen.display()))
    session.send(b"\x1b")
    session.read_for(0.1)
    session.send(b"2\r")
    session.read_until(b'EXECUTED=["select 12;"]')
    self.assertEqual(["select transcript;", "select 12;"], self.stored_commands())

  def test_search_help_preserves_query_selection_draft_and_cursor(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    for command in (b"select '?older';", b"select '?newer';"):
      session.send(command + b"\r")
      session.read_until(b"EXECUTED=")
      session.read_until(b"csql-with-history>")
    session.send(b"select 1;\x02\x12?")
    session.read_for(0.05)
    help_screen = self.rendered_screen(session)
    self.assertIn("Shortcuts: History search mode", help_screen)
    self.assertIn("Enter: recall for editing, without executing", help_screen)
    self.assertIn("Esc: return to Input mode", help_screen)
    self.assertNotIn("Enter: submit draft", help_screen)
    self.assertNotIn("Ctrl+X Ctrl+E", help_screen)
    session.send(b"?select '?\x0e\x1bOP")
    session.read_for(0.05)
    self.assertIn("Shortcuts: History search mode", self.rendered_screen(session))
    session.send(b"\x1bOP")
    session.read_for(0.05)
    screen = self.rendered_screen(session)
    self.assertIn("History search mode |", screen)
    self.assertIn("select '?", screen)
    self.assertIn("> select '?older';", screen)
    session.send(b"\x1b")
    session.read_for(0.1)
    session.send(b"2\x1b[11~")
    session.read_for(0.05)
    self.assertIn("Shortcuts: Input mode", self.rendered_screen(session))
    session.send(b"\r\r")
    session.read_until(b'EXECUTED=["select 12;"]')
    self.assertEqual(["select '?older';", "select '?newer';", "select 12;"], self.stored_commands())

  def test_shortcuts_scroll_and_close_cleanly_in_a_small_terminal(self) -> None:
    session = self.start()
    session.set_size(7, 30)
    session.read_until(b"csql-with-history>")
    session.send(b"?")
    session.read_for(0.05)
    session.send(b"\x1b[F")
    session.read_for(0.05)
    screen = AnsiScreen(rows=7, columns=30)
    screen.feed(bytes(session.output))
    self.assertTrue(any("Ctrl+L: redraw" in line for line in screen.display()), screen.display())
    session.send(b"?select 42;\r")
    session.read_until(b'EXECUTED=["select 42;"]')
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    screen = AnsiScreen(rows=7, columns=30)
    screen.feed(bytes(session.output))
    self.assertEqual(1, sum("csql-with-history>" in line for line in screen.display()))
    self.assertEqual(1, sum("Input mode" in line for line in screen.display()))
    self.assertFalse(any("Shortcuts" in line for line in screen.display()))

  def test_ctrl_q_discards_draft_quits_from_picker_and_help_and_restores_terminal(self) -> None:
    pid_file = self.root / "quit-csql.pid"
    self.environment["SYNTHETIC_PID_FILE"] = str(pid_file)
    for draft in (b"", b"unfinished", b"unfinished\x12query", b"?"):
      with self.subTest(draft=draft):
        session = self.start()
        session.read_until(b"csql-with-history>")
        csql_process_id = int(pid_file.read_text(encoding="ascii"))
        session.send(draft + b"\x11")
        self.assertEqual(0, session.wait())
        self.assertEqual(session.initial_attributes, session.terminal_attributes())
        self.assertTrue(wait_for_process_exit(csql_process_id))
    self.assertEqual([], self.stored_commands())

  def test_cursor_starts_after_prompt_and_tracks_inline_multiline_edits(self) -> None:
    # Shell-exported dimensions must not override the live PTY geometry.
    self.environment.update(COLUMNS="140", LINES="40")
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    screen = AnsiScreen()
    screen.feed(bytes(session.output))
    prompt_row = next(i for i, line in enumerate(screen.display()) if "csql-with-history>" in line)
    self.assertEqual((prompt_row, len("csql-with-history> ")), (screen.row, screen.column))

    session.send(b"select\x0a42;\x1b[A\x1b[H")
    screen.feed(session.read_for(0.1))
    self.assertIn("csql-with-history> select", screen.display()[prompt_row])
    self.assertEqual((prompt_row, len("csql-with-history> ")), (screen.row, screen.column))
    session.send(b"\x1b[B\x1b[F\r")
    session.read_until(b'EXECUTED=["select", "42;"]')

  def test_typing_and_navigation_do_not_erase_or_repaint_unchanged_rows(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    session.send(b"s")
    typed = session.read_for(0.05)
    self.assertIn(b"s", typed)
    self.assertNotIn(b"\x1b[2K", typed)
    self.assertNotIn(b"Input mode", typed)

    session.send(b"\x1b[D")
    moved = session.read_for(0.05)
    self.assertNotIn(b"csql-with-history>", moved)
    self.assertNotIn(b"\x1b[K", moved)
    self.assertNotIn(b"\x1b[2K", moved)
    session.send(b"\x1b[D\x7f\x01")
    self.assertEqual(b"", session.read_for(0.05))
    session.send(b"\x0c")
    refreshed = session.read_for(0.05)
    self.assertIn(b"csql-with-history>", refreshed)
    self.assertIn(b"Input mode", refreshed)
    session.send(b"\x12")
    session.read_for(0.05)
    session.send(b"\x0c")
    self.assertIn(b"History search:", session.read_for(0.05))

  def test_wrapping_and_shrinking_keep_cursor_and_status_aligned_at_screen_bottom(self) -> None:
    session = self.start()
    session.set_size(8, 40)
    session.read_until(b"csql-with-history>")
    for number in range(4):
      session.send("select {};\r".format(number).encode("ascii"))
      session.read_until('EXECUTED=["select {};"]'.format(number).encode("ascii"))
      session.read_until(b"csql-with-history>")
    session.read_for(0.05)
    screen = AnsiScreen(rows=8, columns=40)
    screen.feed(bytes(session.output))

    session.send(b"x" * 60)
    screen.feed(session.read_for(0.1))
    lines = screen.display()
    prompt_row = next(i for i, line in enumerate(lines) if "csql-with-history>" in line)
    self.assertEqual((prompt_row + 2, 1), (screen.row, screen.column))
    self.assertEqual(1, sum("Input mode" in line for line in lines), lines)

    session.send(b"\x1b[H" + b"\x04" * 60)
    screen.feed(session.read_for(0.1))
    lines = screen.display()
    self.assertFalse(any("x" in line for line in lines), lines)
    self.assertEqual(1, sum("Input mode" in line for line in lines), lines)
    self.assertEqual((prompt_row, len("csql-with-history> ")), (screen.row, screen.column))
    session.send(b"select after_shrink;\r")
    session.read_until(b'EXECUTED=["select after_shrink;"]')

  def test_multiline_history_survives_restart_and_recall_is_editable(self) -> None:
    first = self.start()
    first.read_until(b"csql-with-history>")
    first.send(b"select\x0a42;\r")
    first.read_until(b'EXECUTED=["select", "42;"]')
    first.read_until(b"csql-with-history>")
    first.send(b"\x04")
    self.assertEqual(0, first.wait())

    restarted = self.start()
    restarted.read_until(b"csql-with-history>")
    restarted.send(b"\x1b[A")
    recalled = restarted.read_for(0.1)
    self.assertIn(b"select", recalled)
    self.assertIn(b"42;", recalled)
    self.assertNotIn(b"EXECUTED", recalled)

    restarted.send(b"\x1b[F changed\r")
    restarted.read_until(b'EXECUTED=["select changed", "42;"]')

  def test_history_search_escape_restores_draft_and_cursor(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select searchable;\r")
    session.read_until(b'EXECUTED=["select searchable;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"select tail;\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x1b[D\x12search\x1b")
    session.read_for(0.1)
    session.send(b" restored\r")
    session.read_until(b'EXECUTED=["select restored tail;"]')

  def test_history_search_matches_all_terms_across_multiline_and_recalls_for_editing(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"SELECT Alpha\x0aFROM Multiline;\r")
    session.read_until(b'EXECUTED=["SELECT Alpha", "FROM Multiline;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"select unrelated;\r")
    session.read_until(b'EXECUTED=["select unrelated;"]')
    session.read_until(b"csql-with-history>")

    before = len(session.output)
    session.send(b"unfinished\x12alpha MULTILINE")
    session.read_for(0.1)
    screen = self.rendered_screen(session)
    self.assertIn("SELECT Alpha", screen)
    self.assertIn("FROM Multiline;", screen)
    session.send(b"\r")
    recalled = session.read_for(0.1)
    self.assertNotIn(b"EXECUTED", bytes(session.output[before:]) + recalled)
    session.send(b"\x7f changed;\r")
    session.read_until(b'EXECUTED=["SELECT Alpha", "FROM Multiline changed;"]')

  def test_history_search_deduplicates_by_latest_use_and_down_selects_older_match(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    for command in ("select target_repeat;", "select target_distinct;", "select target_repeat;"):
      session.send(command.encode("ascii") + b"\r")
      session.read_until(('EXECUTED=["{}"]'.format(command)).encode("ascii"))
      session.read_until(b"csql-with-history>")

    self.assertEqual(
      ["select target_distinct;", "select target_repeat;"],
      self.stored_commands(),
    )
    session.send(b"draft\x12target")
    session.read_for(0.1)
    screen = self.rendered_screen(session)
    overlay = screen.split("History search:", 1)[1].split("History search mode |", 1)[0]
    self.assertEqual(1, overlay.count("select target_repeat;"), screen)
    self.assertEqual(1, overlay.count("select target_distinct;"), screen)
    selected = next(line for line in overlay.splitlines() if line.lstrip().startswith("> "))
    self.assertIn("select target_repeat;", selected)

    session.send(b"\x1b[B\r")
    recalled = session.read_for(0.1)
    self.assertNotIn(b"EXECUTED", recalled)
    self.assertIn("select target_distinct;", self.rendered_screen(session))
    session.send(b"\r")
    session.read_until(b'EXECUTED=["select target_distinct;"]')

  def test_configured_retention_counts_unique_commands_and_keeps_latest_use_order(self) -> None:
    session = self.start(["--history-limit", "3"])
    session.read_until(b"csql-with-history>")
    for command in ("select first;", "select repeat;", "select middle;", "select repeat;"):
      session.send(command.encode("ascii") + b"\r")
      session.read_until(('EXECUTED=["{}"]'.format(command)).encode("ascii"))
      session.read_until(b"csql-with-history>")

    self.assertEqual(
      ["select first;", "select middle;", "select repeat;"],
      self.stored_commands(),
    )
    session.send(b"\x1b[A")
    session.read_for(0.05)
    self.assertIn("select repeat;", self.rendered_screen(session))
    session.send(b"\x1b[A")
    session.read_for(0.05)
    self.assertIn("select middle;", self.rendered_screen(session))
    session.send(b"\x1b[A")
    session.read_for(0.05)
    self.assertIn("select first;", self.rendered_screen(session))

  def test_default_retention_keeps_latest_ten_thousand_and_deduplicates_recall(self) -> None:
    history_file = self.root / "default-retention.sqlite3"
    arguments = ["--history-file", str(history_file)]
    initializer = self.start(arguments)
    initializer.read_until(b"csql-with-history>")
    initializer.send(b"\x04")
    self.assertEqual(0, initializer.wait())

    seeded = [
      ("select boundary_{:05d};".format(number),)
      for number in range(9_999)
    ]
    with closing(sqlite3.connect(history_file)) as connection:
      with connection:
        connection.executemany("INSERT INTO submissions(command) VALUES (?)", seeded)

    first = self.start(arguments, database="default_target_one")
    second = self.start(arguments, database="default_target_two")
    first.read_until(b"csql-with-history>")
    second.read_until(b"csql-with-history>")

    def submit_duplicate(session: TerminalSession) -> None:
      session.send(b"select newest_default;\r")
      session.read_until(b'EXECUTED=["select newest_default;"]')
      session.read_until(b"csql-with-history>")

    with ThreadPoolExecutor(max_workers=2) as executor:
      futures = (
        executor.submit(submit_duplicate, first),
        executor.submit(submit_duplicate, second),
      )
      for future in futures:
        future.result()

    retained = self.stored_commands(history_file)
    self.assertEqual(10_000, len(retained))
    self.assertEqual("select boundary_00000;", retained[0])
    self.assertEqual("select newest_default;", retained[-1])
    self.assertEqual(10_000, len(set(retained)))

    second.send(b"select newest_extra;\r")
    second.read_until(b'EXECUTED=["select newest_extra;"]')
    second.read_until(b"csql-with-history>")
    retained = self.stored_commands(history_file)
    self.assertEqual(10_000, len(retained))
    self.assertEqual("select boundary_00001;", retained[0])
    self.assertEqual(["select newest_default;", "select newest_extra;"], retained[-2:])

    first.send(b"\x12newest_default")
    first.read_for(0.05)
    overlay = self.rendered_screen(first).split("History search:", 1)[1].split("History search mode |", 1)[0]
    self.assertEqual(1, overlay.count("select newest_default;"))

  def test_history_search_no_match_and_navigation_boundaries_never_submit_the_draft(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select retained;\r")
    session.read_until(b'EXECUTED=["select retained;"]')
    session.read_until(b"csql-with-history>")

    before = len(session.output)
    session.send(b"select safe;\x12missing\x1b[A\x1b[B\r")
    session.read_for(0.1)
    self.assertIn("(no matches)", self.rendered_screen(session))
    self.assertNotIn(b"EXECUTED", bytes(session.output[before:]))
    session.send(b"\x1b")
    session.read_for(0.1)
    session.send(b"\r")
    session.read_until(b'EXECUTED=["select safe;"]')

  def test_ctrl_c_closes_the_picker_and_clears_the_unfinished_draft(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select retained;\r")
    session.read_until(b'EXECUTED=["select retained;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"discard this draft\x12retained")
    session.read_for(0.1)
    self.assertIn("History search:", self.rendered_screen(session))
    session.send(b"\x03select after_picker_interrupt;\r")
    completed = session.read_until(b'EXECUTED=["select after_picker_interrupt;"]')
    self.assertNotIn(b"discard this draft\r\n", completed)
    session.read_until(b"csql-with-history>")
    self.assertEqual(
      ["select retained;", "select after_picker_interrupt;"],
      self.stored_commands(),
    )

  def test_history_picker_is_prompt_oriented_and_closes_cleanly_in_a_narrow_window(self) -> None:
    session = self.start()
    session.set_size(16, 30)
    session.read_until(b"csql-with-history>")
    session.send(b"select 7;\r")
    session.read_until(b'EXECUTED=["select 7;"]')
    session.read_until(b"csql-with-history>")
    session.send("미완성-draft-abcdefghijklmnopqrstuvwxyz".encode("utf-8") + b"\x12select")
    session.read_for(0.1)

    picker = AnsiScreen(rows=16, columns=30)
    picker.feed(bytes(session.output))
    picker_lines = picker.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in picker_lines), picker_lines)
    self.assertEqual(1, sum("History search:" in line for line in picker_lines), picker_lines)
    self.assertEqual(1, sum("History search mode" in line for line in picker_lines), picker_lines)
    self.assertTrue(any("> select 7;" in line for line in picker_lines), picker_lines)

    session.send(b"\x1b")
    session.read_for(0.1)
    editor = AnsiScreen(rows=16, columns=30)
    editor.feed(bytes(session.output))
    editor_lines = editor.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in editor_lines), editor_lines)
    self.assertEqual(1, sum("Input mode" in line for line in editor_lines), editor_lines)
    self.assertEqual(0, sum("History search:" in line for line in editor_lines), editor_lines)
    self.assertTrue(any('EXECUTED=["select 7;"]' in line for line in editor_lines), editor_lines)

  def test_up_and_down_edit_logical_lines_before_browsing_history(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select older;\r")
    session.read_until(b'EXECUTED=["select older;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"abcde\x0axy\x0a12345;\x1b[A!\x1b[A!\x1b[B\x1b[B!\r")
    session.read_until(b'EXECUTED=["abc!de", "xy!", "123!45;"]')

  def test_history_picker_keeps_prompt_and_selected_match_visible_in_a_short_window(self) -> None:
    session = self.start()
    session.set_size(8, 28)
    session.read_until(b"csql-with-history>")
    for number in range(8):
      command = "select window_{};".format(number)
      session.send(command.encode("ascii") + b"\r")
      session.read_until(('EXECUTED=["{}"]'.format(command)).encode("ascii"))
      session.read_until(b"csql-with-history>")

    session.send(b"draft\x12window")
    session.read_for(0.1)
    opened = AnsiScreen(rows=8, columns=28)
    opened.feed(bytes(session.output))
    opened_lines = opened.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in opened_lines), opened_lines)
    self.assertEqual(1, sum("History search mode" in line for line in opened_lines), opened_lines)

    session.send(b"\x1b[B" * 7)
    session.read_for(0.1)
    moved = AnsiScreen(rows=8, columns=28)
    moved.feed(bytes(session.output))
    moved_lines = moved.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in moved_lines), moved_lines)
    self.assertTrue(any("> select window_0;" in line for line in moved_lines), moved_lines)
    session.send(b"\r\r")
    session.read_until(b'EXECUTED=["select window_0;"]')

  def test_history_picker_keeps_prompt_visible_with_a_tall_multibyte_draft(self) -> None:
    session = self.start()
    session.set_size(8, 20)
    session.read_until(b"csql-with-history>")
    session.send(b"select retained;\r")
    session.read_until(b'EXECUTED=["select retained;"]')
    session.read_until(b"csql-with-history>")

    draft = "select '" + "한글" * 30 + "';"
    session.send(draft.encode("utf-8") + b"\x12retained")
    session.read_for(0.1)
    picker = AnsiScreen(rows=8, columns=20)
    picker.feed(bytes(session.output))
    picker_lines = picker.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in picker_lines), picker_lines)
    self.assertEqual(1, sum("History search mode" in line for line in picker_lines), picker_lines)
    self.assertTrue(any("한글" in line for line in picker_lines), picker_lines)

    session.send(b"\x1b")
    session.read_for(0.1)
    editor = AnsiScreen(rows=8, columns=20)
    editor.feed(bytes(session.output))
    editor_lines = editor.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in editor_lines), editor_lines)
    self.assertEqual(1, sum("Input mode" in line for line in editor_lines), editor_lines)

  def test_submission_boundaries_duplicates_failed_commands_and_draft_restoration(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    submissions = (
      (b";singleline off\r", b"SINGLELINE IS OFF"),
      (b"select\r", b"select\r"),
      (b"42;\r", b"42;\r"),
      (b";xrun\r", b'EXECUTED=["select", "42;"]'),
      (b";singleline on\r", b"SINGLELINE IS ON"),
      (b"bad;\r", b"ERROR: synthetic failure"),
      (b"select\x0a84;\r", b'EXECUTED=["select", "84;"]'),
      (b"bad;\r", b"ERROR: synthetic failure"),
    )
    for keys, expected in submissions:
      session.send(keys)
      session.read_until(expected)
      session.read_until(b"csql-with-history>")
    session.send(b"\x04")
    self.assertEqual(0, session.wait())

    self.assertEqual(
      [
        ";singleline off",
        "select",
        "42;",
        ";xrun",
        ";singleline on",
        "select\n84;",
        "bad;",
      ],
      self.stored_commands(),
    )

    recalled = self.start()
    recalled.read_until(b"csql-with-history>")
    recalled.send(b"unfinished")
    recalled.read_for(0.05)
    recalled.send(b"\x1b[A")
    recalled.read_for(0.05)
    self.assertIn("bad;", self.rendered_screen(recalled))
    recalled.send(b"\x1b[A\x1b[A")
    recalled.read_for(0.05)
    self.assertIn(";singleline on", self.rendered_screen(recalled))
    recalled.send(b"\x1b[B\x1b[B\x1b[B")
    recalled.read_for(0.05)
    self.assertIn("unfinished", self.rendered_screen(recalled))

  def test_leading_space_and_no_history_do_not_save_but_existing_history_is_recalled(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b"select retained;\r")
    session.read_until(b'EXECUTED=["select retained;"]')
    session.read_until(b"csql-with-history>")
    session.send(b" select hidden;\r")
    session.read_until(b'EXECUTED=[" select hidden;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x04")
    self.assertEqual(0, session.wait())
    before = self.stored_commands()
    self.assertEqual(["select retained;"], before)

    private = self.start(["--no-history"])
    private.read_until(b"csql-with-history>")
    private.send(b"\x1b[A")
    private.read_for(0.05)
    self.assertIn("select retained;", self.rendered_screen(private))
    private.send(b"\r")
    private.read_until(b'EXECUTED=["select retained;"]')
    private.read_until(b"csql-with-history>")
    private.send(b"select disabled;\r")
    private.read_until(b'EXECUTED=["select disabled;"]')
    private.read_until(b"csql-with-history>")
    private.send(b"\x04")
    self.assertEqual(0, private.wait())
    self.assertEqual(before, self.stored_commands())

  def test_default_directories_are_isolated_and_relative_explicit_paths_share(self) -> None:
    first_directory = self.root / "first"
    second_directory = self.root / "second"
    first_directory.mkdir()
    second_directory.mkdir()

    first = self.start(cwd=first_directory)
    first.read_until(b"csql-with-history>")
    first.send(b"select directory_one;\r")
    first.read_until(b'EXECUTED=["select directory_one;"]')
    first.read_until(b"csql-with-history>")
    first.send(b"\x04")
    self.assertEqual(0, first.wait())

    isolated = self.start(cwd=second_directory)
    isolated.read_until(b"csql-with-history>")
    isolated.send(b"\x1b[A")
    isolated.read_for(0.05)
    self.assertNotIn("directory_one", self.rendered_screen(isolated))
    isolated.send(b"\x04")
    self.assertEqual(0, isolated.wait())

    shared_from_first = self.start(["--history-file", "../shared.sqlite3"], first_directory)
    shared_from_first.read_until(b"csql-with-history>")
    shared_from_first.send(b"select shared;\r")
    shared_from_first.read_until(b'EXECUTED=["select shared;"]')
    shared_from_first.read_until(b"csql-with-history>")
    shared_from_first.send(b"\x04")
    self.assertEqual(0, shared_from_first.wait())

    shared_from_second = self.start(["--history-file=../shared.sqlite3"], second_directory)
    shared_from_second.read_until(b"csql-with-history>")
    shared_from_second.send(b"\x1b[A")
    shared_from_second.read_for(0.05)
    self.assertIn("select shared;", self.rendered_screen(shared_from_second))

    self.assertEqual(["select directory_one;"], self.stored_commands(first_directory / ".csql_history.sqlite3"))
    self.assertEqual([], self.stored_commands(second_directory / ".csql_history.sqlite3"))
    self.assertEqual(["select shared;"], self.stored_commands(self.root / "shared.sqlite3"))

  def test_live_sessions_refresh_shared_history_on_browse_and_search(self) -> None:
    first_directory = self.root / "live-first"
    second_directory = self.root / "live-second"
    first_directory.mkdir()
    second_directory.mkdir()
    shared_history = self.root / "live-shared.sqlite3"
    history_arguments = ["--history-file", str(shared_history)]

    receiver = self.start(history_arguments, first_directory, "target_one")
    writer = self.start(history_arguments, second_directory, "target_two")
    receiver.read_until(b"csql-with-history>")
    writer.read_until(b"csql-with-history>")

    writer.send(b"select shared_browse;\r")
    writer.read_until(b'EXECUTED=["select shared_browse;"]')
    writer.read_until(b"csql-with-history>")
    receiver.send(b"\x1b[A")
    receiver.read_for(0.05)
    self.assertIn("select shared_browse;", self.rendered_screen(receiver))
    receiver.send(b"\x1b[B")

    writer.send(b"select shared_search;\r")
    writer.read_until(b'EXECUTED=["select shared_search;"]')
    writer.read_until(b"csql-with-history>")
    receiver.send(b"draft\x12shared_search")
    receiver.read_for(0.05)
    self.assertIn("select shared_search;", self.rendered_screen(receiver))
    self.assertEqual(
      ["select shared_browse;", "select shared_search;"],
      self.stored_commands(shared_history),
    )

  def test_shared_history_uses_wal_with_live_reader_writer_sidecars(self) -> None:
    history_file = self.root / "wal-history.sqlite3"
    session = self.start(["--history-file", str(history_file)])
    session.read_until(b"csql-with-history>")

    with closing(sqlite3.connect(history_file)) as connection:
      journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    self.assertEqual("wal", journal_mode)
    self.assertTrue(Path(str(history_file) + "-wal").exists())
    self.assertTrue(Path(str(history_file) + "-shm").exists())

  def test_concurrent_live_writers_insert_and_prune_without_losing_retained_entries(self) -> None:
    history_file = self.root / "concurrent-retention.sqlite3"
    arguments = ["--history-file", str(history_file), "--history-limit", "7"]
    first = self.start(arguments, database="target_one")
    second = self.start(arguments, database="target_two")
    first.read_until(b"csql-with-history>")
    second.read_until(b"csql-with-history>")

    first_commands = ["select first_{};".format(number) for number in range(6)]
    second_commands = ["select second_{};".format(number) for number in range(6)]

    def submit_all(session: TerminalSession, commands: list[str]) -> None:
      for command in commands:
        session.send(command.encode("ascii") + b"\r")
        session.read_until(('EXECUTED=["{}"]'.format(command)).encode("ascii"))
        session.read_until(b"csql-with-history>")

    with ThreadPoolExecutor(max_workers=2) as executor:
      futures = (
        executor.submit(submit_all, first, first_commands),
        executor.submit(submit_all, second, second_commands),
      )
      for future in futures:
        future.result()

    retained = self.stored_commands(history_file)
    self.assertEqual(7, len(retained))
    self.assertEqual(7, len(set(retained)))
    self.assertTrue(set(retained).issubset(set(first_commands + second_commands)))

    reader = self.start(["--history-file", str(history_file), "--no-history"])
    reader.read_until(b"csql-with-history>")
    for command in reversed(retained):
      reader.send(b"\x1b[A")
      reader.read_for(0.03)
      self.assertIn(command, self.rendered_screen(reader))

  def test_conflicting_live_limits_apply_the_limit_of_each_committing_writer(self) -> None:
    history_file = self.root / "conflicting-limits.sqlite3"
    common = ["--history-file", str(history_file)]
    wider = self.start([*common, "--history-limit", "5"], database="wide_target")
    narrower = self.start([*common, "--history-limit", "3"], database="narrow_target")
    wider.read_until(b"csql-with-history>")
    narrower.read_until(b"csql-with-history>")

    for number in range(5):
      command = "select wide_{};".format(number)
      wider.send(command.encode("ascii") + b"\r")
      wider.read_until(('EXECUTED=["{}"]'.format(command)).encode("ascii"))
      wider.read_until(b"csql-with-history>")

    narrower.send(b"select narrow_commit;\r")
    narrower.read_until(b'EXECUTED=["select narrow_commit;"]')
    narrower.read_until(b"csql-with-history>")
    self.assertEqual(
      ["select wide_3;", "select wide_4;", "select narrow_commit;"],
      self.stored_commands(history_file),
    )

    wider.send(b"select wide_after_prune;\r")
    wider.read_until(b'EXECUTED=["select wide_after_prune;"]')
    wider.read_until(b"csql-with-history>")
    self.assertEqual(
      [
        "select wide_3;",
        "select wide_4;",
        "select narrow_commit;",
        "select wide_after_prune;",
      ],
      self.stored_commands(history_file),
    )

  def test_short_writer_contention_waits_then_commits_before_csql_submission(self) -> None:
    history_file = self.root / "brief-contention.sqlite3"
    session = self.start(["--history-file", str(history_file)])
    session.read_until(b"csql-with-history>")
    lock_acquired = threading.Event()

    def hold_writer_lock() -> None:
      with closing(sqlite3.connect(history_file)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        lock_acquired.set()
        time.sleep(0.1)
        connection.rollback()

    holder = threading.Thread(target=hold_writer_lock)
    holder.start()
    self.assertTrue(lock_acquired.wait(1))
    started = time.monotonic()
    session.send(b"select after_brief_lock;\r")
    session.read_until(b'EXECUTED=["select after_brief_lock;"]')
    elapsed = time.monotonic() - started
    holder.join(1)

    self.assertFalse(holder.is_alive())
    self.assertGreaterEqual(elapsed, 0.05)
    self.assertLess(elapsed, 1.0)
    self.assertEqual(["select after_brief_lock;"], self.stored_commands(history_file))

  def test_expired_writer_contention_switches_to_memory_only_and_executes_submission(self) -> None:
    history_file = self.root / "expired-contention.sqlite3"
    session = self.start(["--history-file", str(history_file)])
    session.read_until(b"csql-with-history>")
    session.send(b"select persisted_before_lock;\r")
    session.read_until(b'EXECUTED=["select persisted_before_lock;"]')
    session.read_until(b"csql-with-history>")

    with closing(sqlite3.connect(history_file)) as blocker:
      blocker.execute("BEGIN IMMEDIATE")
      started = time.monotonic()
      session.send(b"select blocked_history;\r")
      session.read_until(b"newly retained entries will disappear on exit", timeout=2)
      session.read_until(b'EXECUTED=["select blocked_history;"]')
      elapsed = time.monotonic() - started
      session.read_until(b"csql-with-history>")

    self.assertGreaterEqual(elapsed, 0.2)
    self.assertLess(elapsed, 1.5)
    session.send(b"SELECT volatile\x0aFROM memory;\r")
    session.read_until(b'EXECUTED=["SELECT volatile", "FROM memory;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"SELECT volatile\x0aFROM memory;\r")
    session.read_until(b'EXECUTED=["SELECT volatile", "FROM memory;"]')
    session.read_until(b"csql-with-history>")
    session.send(b" select private_after_failure;\r")
    session.read_until(b'EXECUTED=[" select private_after_failure;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"select after_storage_restored;\r")
    session.read_until(b'EXECUTED=["select after_storage_restored;"]')
    session.read_until(b"csql-with-history>")

    screen = self.rendered_screen(session)
    self.assertEqual(1, screen.count("MEMORY-ONLY"), screen)
    self.assertIn("entries disappear on exit", screen)
    session.send(b"\x1b[A")
    session.read_for(0.05)
    self.assertIn("select after_storage_restored;", self.rendered_screen(session))
    session.send(b"\x03draft\x12volatile memory")
    session.read_for(0.05)
    search_screen = self.rendered_screen(session)
    overlay = search_screen.split("History search:", 1)[1].split("MEMORY-ONLY", 1)[0]
    self.assertEqual(1, overlay.count("SELECT volatile"), search_screen)
    self.assertIn("FROM memory;", overlay)
    session.send(b"\r")
    session.read_for(0.05)
    recalled = self.rendered_screen(session)
    self.assertIn("SELECT volatile", recalled)
    self.assertIn("FROM memory;", recalled)
    session.send(b"\x03\x12private_after_failure")
    session.read_for(0.05)
    self.assertIn("(no matches)", self.rendered_screen(session))
    session.send(b"\x1b")
    session.read_for(0.1)
    session.send(b"\x04")
    self.assertEqual(0, session.wait())

    self.assertEqual(["select persisted_before_lock;"], self.stored_commands(history_file))

    restarted = self.start(["--history-file", str(history_file)])
    restarted.read_until(b"csql-with-history>")
    restarted.send(b"\x1b[A")
    restarted.read_for(0.05)
    restart_screen = self.rendered_screen(restarted)
    self.assertIn("select persisted_before_lock;", restart_screen)
    self.assertNotIn("blocked_history", restart_screen)
    self.assertNotIn("after_storage_restored", restart_screen)
    restarted.send(b"\x03\x12volatile memory")
    restarted.read_for(0.05)
    self.assertIn("(no matches)", self.rendered_screen(restarted))

  def test_unavailable_history_destination_keeps_enhanced_memory_only_session_usable(self) -> None:
    history_file = self.root / "missing" / "unavailable.sqlite3"
    session = self.start(["--history-file", str(history_file)])

    warning = session.read_until(b"newly retained entries will disappear on exit")
    self.assertIn(b"persistent history unavailable", warning)
    session.read_until(b"csql-with-history>")
    self.assertIn("MEMORY-ONLY", self.rendered_screen(session))

    session.send(b"select memory_only;\r")
    session.read_until(b'EXECUTED=["select memory_only;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x1b[A")
    session.read_for(0.05)
    self.assertIn("select memory_only;", self.rendered_screen(session))
    self.assertFalse(history_file.exists())

  def test_unavailable_no_history_store_keeps_saving_disabled(self) -> None:
    history_file = self.root / "unreadable-history.sqlite3"
    history_file.mkdir()
    session = self.start(["--history-file", str(history_file), "--no-history"])

    warning = session.read_until(b"history saving remains disabled")
    self.assertIn(b"persistent history unavailable", warning)
    session.read_until(b"csql-with-history>")
    session.send(b"select private_no_history;\r")
    session.read_until(b'EXECUTED=["select private_no_history;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x12private_no_history")
    session.read_for(0.05)
    self.assertIn("(no matches)", self.rendered_screen(session))
    self.assertNotIn("MEMORY-ONLY", self.rendered_screen(session))

  def test_ctrl_j_builds_one_multiline_submission_and_returns_to_styled_prompt(self) -> None:
    session = self.start()

    initial = session.read_until(b"csql-with-history>")
    initial += session.read_for(0.05)
    self.assertIn(b"\x1b[1;38;2;203;166;247m", initial)
    self.assertIn(b"\x1b[38;2;205;214;244;48;2;24;24;37m", initial)
    self.assertIn(b"\x1b[1;38;2;137;180;250;48;2;24;24;37m", initial)
    self.assertIn(b"?", initial)
    self.assertIn(b"shortcuts", initial)
    session.send(b"select\x0a42;\r")

    result = session.read_until(b'EXECUTED=["select", "42;"]')
    self.assertIn(b"select", result)
    session.read_until(b"csql-with-history>")

  def test_prompt_looking_output_and_silence_do_not_end_running_work(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")

    session.send(b"promptlike;\r")
    session.read_until(b"promptlike;\r")
    before_completion = session.read_for(0.2)
    self.assertNotIn(b"csql-with-history>", before_completion)
    self.assertNotIn(b"PROMPT-LIKE WORK FINISHED", before_completion)
    self.assertIn(b"__CSQL_WITH_HISTORY_", before_completion)
    completed = session.read_until(b"PROMPT-LIKE WORK FINISHED")
    self.assertNotIn(b"csql-with-history>", completed)
    session.read_until(b"csql-with-history>")

    session.send(b"quiet;\r")
    session.read_until(b"quiet;\r")
    silent_interval = session.read_for(0.2)
    self.assertNotIn(b"csql-with-history>", silent_interval)
    session.read_until(b"QUIET WORK FINISHED")
    session.read_until(b"csql-with-history>")

  def test_running_ctrl_c_matches_direct_csql_and_both_sessions_remain_usable(self) -> None:
    direct = TerminalSession([str(self.csql), "synthetic_db"], self.root, self.environment)
    self.addCleanup(direct.close)
    wrapped = self.start()

    for label, session, prompt in (
      ("direct", direct, b"csql> "),
      ("wrapped", wrapped, b"csql-with-history>"),
    ):
      with self.subTest(label=label):
        session.read_until(prompt)
        session.read_for(0.1)
        session.send(b"slow;\r")
        session.read_until(b"slow;\r\n")
        interrupted_at = time.monotonic()
        session.send(b"\x03")
        session.read_until(b"ERROR: synthetic interrupted", timeout=2.0)
        self.assertLess(time.monotonic() - interrupted_at, 1.0)
        session.read_until(prompt)
        session.read_for(0.1)
        session.send(b"select after_interrupt;\r")
        session.read_until(b'EXECUTED=["select after_interrupt;"]')
        session.read_until(prompt)
        session.read_for(0.1)
        session.send(b";exit\r")
        self.assertEqual(0, session.wait())

  def test_shell_receives_terminal_input_and_returns_to_enhanced_history(self) -> None:
    self.environment["CUBRID_CSQL_SHELL"] = "PS1='SYNTHETIC-SHELL> ' /bin/sh -i"
    session = self.start()
    session.read_until(b"csql-with-history>")

    session.send(b";shell\r")
    session.read_until(b"SYNTHETIC-SHELL> ")
    session.send(b"sleep 10\n")
    session.read_for(0.1)
    session.send(b"\x03")
    session.read_until(b"SYNTHETIC-SHELL> ")
    session.send(b"printf 'SHELL-INPUT-RECEIVED\\n'\nexit 7\n")
    session.read_until(b"SHELL-INPUT-RECEIVED")
    session.read_until(b"SHELL-STATUS=1792")
    session.read_until(b"csql-with-history>")

    session.send(b"select after_shell;\r")
    session.read_until(b'EXECUTED=["select after_shell;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x1b[A")
    session.read_for(0.05)
    self.assertIn("select after_shell;", self.rendered_screen(session))
    self.assertEqual([";shell", "select after_shell;"], self.stored_commands())

  def test_password_is_masked_and_excluded_from_history_and_search(self) -> None:
    password = "synthetic-password-input-ticket07"
    self.environment["SYNTHETIC_PASSWORD"] = password
    session = self.start()

    session.read_until(b"Password: ")
    session.send(password.encode("ascii") + b"\n")
    session.read_until(b"AUTHENTICATED")
    session.read_until(b"csql-with-history>")
    self.assertNotIn(password.encode("ascii"), bytes(session.output))

    session.send(b"select after_password;\r")
    session.read_until(b'EXECUTED=["select after_password;"]')
    session.read_until(b"csql-with-history>")
    session.send(b"\x12password-input-ticket07")
    session.read_for(0.05)
    self.assertIn("(no matches)", self.rendered_screen(session))
    self.assertEqual(["select after_password;"], self.stored_commands())

  def test_raw_terminal_program_prompt_output_does_not_reclaim_input_early(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")

    session.send(b";rawhandoff\r")
    session.read_until(b";rawhandoff\r\n")
    output_before_completion = session.read_for(0.2)
    self.assertNotIn(b"csql-with-history>", output_before_completion)
    self.assertNotIn(b"RAW-HANDOFF-FINISHED", output_before_completion)
    session.read_until(b"RAW-HANDOFF-FINISHED")
    session.read_until(b"csql-with-history>")

    session.send(b"select after_raw_handoff;\r")
    session.read_until(b'EXECUTED=["select after_raw_handoff;"]')

  def test_resize_reaches_a_terminal_handoff_and_returns_at_the_current_size(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    session.send(b";rawhandoff\r")
    session.read_until(b"__CSQL_WITH_HISTORY_")
    session.set_size(13, 47)
    session.read_until(b"RAW-HANDOFF-SIZE=13x47")
    session.read_until(b"RAW-HANDOFF-FINISHED")
    session.read_until(b"csql-with-history>")

    handoff_returned = len(session.output)
    session.send(b"select output_after_resized_handoff;\r")
    session.read_until(b'EXECUTED=["select output_after_resized_handoff;"]')
    session.read_until(b"csql-with-history>")
    session.read_for(0.1)
    screen = AnsiScreen(rows=13, columns=47)
    screen.feed(bytes(session.output[handoff_returned:]))
    lines = screen.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in lines), lines)
    self.assertEqual(1, sum("Input mode" in line for line in lines), lines)
    self.assertIn("output_after_resized_handoff", "".join(lines))

  def test_separate_submissions_accumulate_for_xrun_and_errors_do_not_end_session(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")

    session.send(b";singleline off\r")
    session.read_until(b"SINGLELINE IS OFF")
    session.read_until(b"csql-with-history>")
    for submission in (b"select\r", b"42;\r"):
      session.send(submission)
      session.read_until(submission)
      session.read_until(b"csql-with-history>")
    self.assertNotIn(b"EXECUTED", bytes(session.output))
    session.send(b";xrun\r")
    session.read_until(b'EXECUTED=["select", "42;"]')
    session.read_until(b"csql-with-history>")

    session.send(b";singleline on\r")
    session.read_until(b"SINGLELINE IS ON")
    session.read_until(b"csql-with-history>")
    session.send(b"bad;\r")
    session.read_until(b"ERROR: synthetic failure")
    session.read_until(b"csql-with-history>")
    session.send(b"select 99;\r")
    session.read_until(b'EXECUTED=["select 99;"]')
    session.read_until(b"csql-with-history>")

  def test_alt_enter_cursor_editing_and_idle_ctrl_c_preserve_exact_drafts(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")

    session.send(b"selct\x1b[D\x1b[De\x1b[F 7;\r")
    session.read_until(b'EXECUTED=["select 7;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"select\x1b\r84;\r")
    session.read_until(b'EXECUTED=["select", "84;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"\tselect 21;\r")
    session.read_until(b'EXECUTED=["\\tselect 21;"]')
    session.read_until(b"csql-with-history>")

    session.send(b"discard this draft\x03select 100;\r")
    result = session.read_until(b'EXECUTED=["select 100;"]')
    self.assertNotIn(b"discard this draft\r\n", result)
    session.read_until(b"csql-with-history>")

  def test_repeated_submissions_leave_one_rendered_prompt_and_status(self) -> None:
    session = self.start()
    session.set_size(10, 60)
    session.read_until(b"csql-with-history>")
    for number in range(15):
      session.send("select {};\r".format(number).encode("ascii"))
      session.read_until('EXECUTED=["select {};"]'.format(number).encode("ascii"))
      session.read_until(b"csql-with-history>")
    session.read_for(0.05)

    screen = AnsiScreen(rows=10, columns=60)
    screen.feed(bytes(session.output))
    lines = screen.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in lines), lines)
    self.assertEqual(1, sum("Input mode" in line for line in lines), lines)
    self.assertTrue(any('EXECUTED=["select 14;"]' in line for line in lines), lines)

  def test_soft_wrapped_draft_has_one_rendered_prompt_and_status(self) -> None:
    session = self.start()
    session.set_size(10, 20)
    session.read_until(b"csql-with-history>")
    session.send(b"x" * 45)
    session.read_for(0.1)

    screen = AnsiScreen(rows=10, columns=20)
    screen.feed(bytes(session.output))
    lines = screen.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in lines), lines)
    self.assertEqual(1, sum("Input mode" in line for line in lines), lines)

    session.send(b"\x03select 20;\r")
    session.read_until(b'EXECUTED=["select 20;"]')

  def test_resize_redraws_a_long_multibyte_draft_without_waiting_for_input(self) -> None:
    session = self.start()
    session.read_until(b"csql-with-history>")
    draft = "select '" + "한글" * 30 + "';"
    session.send(draft.encode("utf-8"))
    session.read_for(0.1)
    screen = AnsiScreen(rows=24, columns=100)
    screen.feed(bytes(session.output))

    session.set_size(9, 24)
    resized = session.read_for(0.2)
    screen.resize(9, 24)
    screen.feed(resized)
    self.assertIn(b"csql-with-history>", resized)
    self.assertIn("한글".encode("utf-8"), resized)
    self.assertIn(b"Input mode", resized)
    lines = screen.display()
    self.assertEqual(1, sum("csql-with-history>" in line for line in lines), lines)
    self.assertEqual(1, sum("Input mode" in line for line in lines), lines)

    session.send(b"\x03select after_resize;\r")
    session.read_until(b'EXECUTED=["select after_resize;"]')

  def test_exit_and_empty_draft_eof_restore_the_outer_terminal(self) -> None:
    for ending in (b";exit\r", b"\x04"):
      with self.subTest(ending=ending):
        session = self.start()
        session.read_until(b"csql-with-history>")
        session.send(ending)
        self.assertEqual(0, session.wait())
        restored = session.terminal_attributes()
        self.assertEqual(session.initial_attributes, restored)

  def test_csql_error_exit_preserves_status_and_restores_the_outer_terminal(self) -> None:
    self.environment["SYNTHETIC_STARTUP_STATUS"] = "23"
    session = self.start()
    self.assertEqual(23, session.wait())
    self.assertEqual(session.initial_attributes, session.terminal_attributes())

  def test_termination_signals_restore_the_terminal_and_reap_csql(self) -> None:
    pid_file = self.root / "synthetic-csql.pid"
    self.environment["SYNTHETIC_PID_FILE"] = str(pid_file)
    for termination_signal in (signal.SIGHUP, signal.SIGTERM):
      with self.subTest(signal=termination_signal):
        pid_file.unlink(missing_ok=True)
        session = self.start()
        session.read_until(b"csql-with-history>")
        csql_process_id = int(pid_file.read_text(encoding="ascii"))

        os.kill(session.process_id, termination_signal)
        self.assertEqual(128 + termination_signal, session.wait())
        self.assertEqual(session.initial_attributes, session.terminal_attributes())

        self.assertTrue(wait_for_process_exit(csql_process_id))

  def test_termination_immediately_after_csql_spawn_still_reaps_the_child(self) -> None:
    pid_file = self.root / "immediate-synthetic-csql.pid"
    self.environment["SYNTHETIC_PID_FILE"] = str(pid_file)
    session = self.start()
    deadline = time.monotonic() + 2.0
    while not pid_file.exists() and time.monotonic() < deadline:
      time.sleep(0.001)
    self.assertTrue(pid_file.exists())
    csql_process_id = int(pid_file.read_text(encoding="ascii"))

    os.kill(session.process_id, signal.SIGTERM)
    self.assertEqual(128 + signal.SIGTERM, session.wait())
    self.assertEqual(session.initial_attributes, session.terminal_attributes())
    self.assertTrue(wait_for_process_exit(csql_process_id))


if __name__ == "__main__":
  unittest.main()

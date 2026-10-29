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
"""External-process tests for the csql-future bypass."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

try:
  import tomllib
except ModuleNotFoundError:
  import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = Path(os.environ.get("CSQL_FUTURE_TEST_COMMAND", str(PROJECT_ROOT / ".venv/bin/csql-future")))


class LaunchAndBypassTest(unittest.TestCase):

  def setUp(self) -> None:
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary_directory.cleanup)
    self.root = Path(self.temporary_directory.name)
    self.bin_directory = self.root / "bin"
    self.bin_directory.mkdir()
    self.csql = self.bin_directory / "csql"
    self.csql.write_text(
      textwrap.dedent("""\
                #!/usr/bin/env python3
                import json
                import sys

                payload = sys.stdin.buffer.read()
                print(json.dumps(sys.argv[1:], ensure_ascii=False))
                sys.stdout.buffer.write(payload)
                print("synthetic csql stderr", file=sys.stderr)
                if "--synthetic-failure" in sys.argv:
                    sys.exit(23)
                if "--definitely-invalid" in sys.argv:
                    sys.exit(2)
                """),
      encoding="utf-8",
    )
    self.csql.chmod(0o755)
    self.environment = os.environ.copy()
    self.environment["XDG_CONFIG_HOME"] = str(self.root / "config")
    self.environment["PATH"] = os.pathsep.join((str(self.bin_directory), self.environment.get("PATH", "")))

  def run_process(self, command: list[str], input_bytes: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
      command,
      input=input_bytes,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      cwd=self.root,
      env=self.environment,
      check=False,
    )

  def test_print_keymap_works_without_csql_and_round_trips(self) -> None:
    self.environment["PATH"] = str(self.root / "missing-bin")
    result = self.run_process([str(WRAPPER), "--print-keymap"], b"")
    self.assertEqual(0, result.returncode)
    self.assertEqual(b"", result.stderr)
    bindings = tomllib.loads(result.stdout.decode("utf-8"))
    self.assertEqual(["Ctrl+R"], bindings["search"])
    self.assertEqual(["Ctrl+X Ctrl+E"], bindings["external_editor"])
    from csql_future.keymap import Keymap
    Keymap(bindings)

  def test_batch_bypass_ignores_invalid_keymaps(self) -> None:
    default = Path(self.environment["XDG_CONFIG_HOME"]) / "csql-future/keymap.toml"
    default.parent.mkdir(parents=True)
    default.write_text("invalid TOML", encoding="utf-8")
    arguments = ["-c", "select 7", "synthetic_db"]
    direct = self.run_process([str(self.csql), *arguments], b"input")
    wrapped = self.run_process([str(WRAPPER), "--keymap", "missing.toml", *arguments], b"input")
    self.assertEqual(direct.returncode, wrapped.returncode)
    self.assertEqual(direct.stdout, wrapped.stdout)
    self.assertEqual(direct.stderr, wrapped.stderr)

  def test_keymap_requires_a_nonempty_path(self) -> None:
    for arguments in (["--keymap"], ["--keymap=", "synthetic_db"]):
      with self.subTest(arguments=arguments):
        result = self.run_process([str(WRAPPER), *arguments], b"")
        self.assertEqual(2, result.returncode)
        self.assertEqual(b"", result.stdout)
        self.assertIn(b"--keymap requires", result.stderr)

  def test_pipe_bypass_preserves_process_behavior_without_touching_history(self) -> None:
    input_bytes = b"select 424242;\n"
    csql_arguments = ["-S", "-u", "dba", "synthetic_db"]
    selected_history = self.root / "selected.sqlite3"

    direct = self.run_process([str(self.csql), *csql_arguments], input_bytes)
    wrapped = self.run_process(
      [
        str(WRAPPER),
        "--history-file",
        str(selected_history),
        "--history-limit",
        "7",
        "--no-history",
        *csql_arguments,
      ],
      input_bytes,
    )

    self.assertEqual(direct.returncode, wrapped.returncode)
    self.assertEqual(direct.stdout, wrapped.stdout)
    self.assertEqual(direct.stderr, wrapped.stderr)
    self.assertFalse(selected_history.exists())
    self.assertFalse((self.root / ".csql_history.sqlite3").exists())

  def test_wrapper_looking_csql_values_are_forwarded_unchanged(self) -> None:
    cases = (
      ["-p", "--no-history", "synthetic_db"],
      ["--password", "--history-limit", "synthetic_db"],
      ["--password", "--keymap", "synthetic_db"],
      ["--pass", "--keymap=secret", "synthetic_db"],
      ["--", "--keymap", "keys.toml"],
      ["--pass", "--history-file", "synthetic_db"],
      ["-c", "--history-file", "synthetic_db"],
      ["--command=--no-history", "synthetic_db"],
      ["-Sc", "--history-limit", "synthetic_db"],
      ["--", "--no-history"],
    )

    for csql_arguments in cases:
      with self.subTest(csql_arguments=csql_arguments):
        direct = self.run_process([str(self.csql), *csql_arguments], b"")
        wrapped = self.run_process([str(WRAPPER), "--history-limit", "3", *csql_arguments], b"")
        self.assertEqual(direct.returncode, wrapped.returncode)
        self.assertEqual(direct.stdout, wrapped.stdout)
        self.assertEqual(direct.stderr, wrapped.stderr)

  def test_success_failure_and_invalid_option_statuses_are_preserved(self) -> None:
    cases = (
      ["-c", "select 1", "synthetic_db"],
      ["--synthetic-failure", "synthetic_db"],
      ["--definitely-invalid", "synthetic_db"],
    )

    for csql_arguments in cases:
      with self.subTest(csql_arguments=csql_arguments):
        direct = self.run_process([str(self.csql), *csql_arguments], b"")
        wrapped = self.run_process([str(WRAPPER), "--no-history", *csql_arguments], b"")
        self.assertEqual(direct.returncode, wrapped.returncode)
        self.assertEqual(direct.stdout, wrapped.stdout)
        self.assertEqual(direct.stderr, wrapped.stderr)

  def test_redirected_stdout_and_stderr_match_direct_csql(self) -> None:
    input_bytes = b"select 7;\n"
    csql_arguments = ["-i", "synthetic.sql", "synthetic_db"]
    direct_stdout = self.root / "direct.stdout"
    direct_stderr = self.root / "direct.stderr"
    wrapped_stdout = self.root / "wrapped.stdout"
    wrapped_stderr = self.root / "wrapped.stderr"

    with direct_stdout.open("wb") as stdout, direct_stderr.open("wb") as stderr:
      direct = subprocess.run(
        [str(self.csql), *csql_arguments],
        input=input_bytes,
        stdout=stdout,
        stderr=stderr,
        cwd=self.root,
        env=self.environment,
        check=False,
      )
    with wrapped_stdout.open("wb") as stdout, wrapped_stderr.open("wb") as stderr:
      wrapped = subprocess.run(
        [str(WRAPPER), "--history-file=unused.sqlite3", *csql_arguments],
        input=input_bytes,
        stdout=stdout,
        stderr=stderr,
        cwd=self.root,
        env=self.environment,
        check=False,
      )

    self.assertEqual(direct.returncode, wrapped.returncode)
    self.assertEqual(direct_stdout.read_bytes(), wrapped_stdout.read_bytes())
    self.assertEqual(direct_stderr.read_bytes(), wrapped_stderr.read_bytes())
    self.assertFalse((self.root / "unused.sqlite3").exists())

  def test_existing_selected_history_is_unchanged(self) -> None:
    history = self.root / "existing.sqlite3"
    sentinel = b"existing history must remain byte-for-byte unchanged\n"
    history.write_bytes(sentinel)

    wrapped = self.run_process(
      [
        str(WRAPPER),
        "-c",
        "select 8",
        "--history-file",
        str(history),
        "synthetic_db",
      ],
      b"",
    )

    self.assertEqual(0, wrapped.returncode)
    self.assertEqual(sentinel, history.read_bytes())

  def test_non_numeric_history_limit_stops_before_csql(self) -> None:
    result = self.run_process([str(WRAPPER), "--history-limit", "not-a-number", "synthetic_db"], b"")

    self.assertEqual(2, result.returncode)
    self.assertEqual(b"", result.stdout)
    self.assertIn(b"--history-limit must be an integer", result.stderr)

  def test_help_and_version_work_without_csql_on_path(self) -> None:
    environment = dict(self.environment, PATH=str(self.root / "missing"))
    for option, expected in (("--help", b"--history-file"), ("--version", b"csql-future 0.1.0")):
      with self.subTest(option=option):
        result = subprocess.run(
          [str(WRAPPER), option], cwd=self.root, env=environment, capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(expected, result.stdout)
        self.assertFalse((self.root / ".csql_history.sqlite3").exists())

  def test_missing_csql_has_a_clear_exit_status(self) -> None:
    environment = dict(self.environment, PATH=str(self.root / "missing"))
    result = subprocess.run(
      [str(WRAPPER), "synthetic_db"], cwd=self.root, env=environment, capture_output=True, check=False,
    )
    self.assertEqual(127, result.returncode)
    self.assertIn(b"csql executable not found", result.stderr)

  def test_active_path_client_wins_over_a_launcher_sibling(self) -> None:
    launchers = self.root / "launchers"
    launchers.mkdir()
    launcher = launchers / "csql-future"
    launcher.write_bytes(WRAPPER.read_bytes())
    launcher.chmod(0o755)
    sibling = launchers / "csql"
    sibling.write_text("#!/bin/sh\necho WRONG-CLIENT\nexit 99\n")
    sibling.chmod(0o755)
    arguments = ["-c", "select 1", "synthetic_db"]
    direct = self.run_process([str(self.csql), *arguments], b"")
    wrapped = self.run_process([str(launcher), *arguments], b"")
    self.assertEqual((direct.returncode, direct.stdout, direct.stderr),
                     (wrapped.returncode, wrapped.stdout, wrapped.stderr))

if __name__ == "__main__":
  unittest.main()

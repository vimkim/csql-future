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
"""Compare direct and wrapped noninteractive calls against real csql."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = Path(os.environ.get("CSQL_WITH_HISTORY_TEST_COMMAND", str(PROJECT_ROOT / ".venv/bin/csql-with-history")))
ELAPSED_TIME = re.compile(rb"\([0-9]+(?:\.[0-9]+)? sec\)")


@dataclass(frozen=True)
class Invocation:
  returncode: int
  stdout: bytes
  stderr: bytes


def normalized(output: bytes) -> bytes:
  return ELAPSED_TIME.sub(b"(TIME)", output)


def run(
  command: Sequence[str],
  environment: dict[str, str],
  working_directory: Path,
  input_bytes: Optional[bytes] = None,
) -> Invocation:
  result = subprocess.run(
    command,
    input=input_bytes,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=working_directory,
    env=environment,
    check=False,
  )
  return Invocation(result.returncode, result.stdout, result.stderr)


def run_with_file_stdin(
  command: Sequence[str],
  environment: dict[str, str],
  working_directory: Path,
  input_path: Path,
) -> Invocation:
  with input_path.open("rb") as input_file:
    result = subprocess.run(
      command,
      stdin=input_file,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      cwd=working_directory,
      env=environment,
      check=False,
    )
  return Invocation(result.returncode, result.stdout, result.stderr)


def assert_same(label: str, direct: Invocation, wrapped: Invocation) -> None:
  differences: List[str] = []
  if direct.returncode != wrapped.returncode:
    differences.append("exit status: direct={} wrapped={}".format(direct.returncode, wrapped.returncode))
  if normalized(direct.stdout) != normalized(wrapped.stdout):
    differences.append("stdout:\n--- direct ---\n{}\n--- wrapped ---\n{}".format(
      direct.stdout.decode(errors="replace"), wrapped.stdout.decode(errors="replace")))
  if normalized(direct.stderr) != normalized(wrapped.stderr):
    differences.append("stderr:\n--- direct ---\n{}\n--- wrapped ---\n{}".format(
      direct.stderr.decode(errors="replace"), wrapped.stderr.decode(errors="replace")))
  if differences:
    raise AssertionError("{} differs:\n{}".format(label, "\n".join(differences)))
  print("PASS {} (exit {})".format(label, direct.returncode))


def require_program(name: str) -> str:
  program = shutil.which(name)
  if program is None:
    raise RuntimeError("{} is not available on PATH".format(name))
  return program


def isolate_runtime(root: Path, environment: dict[str, str]) -> None:
  installed_root_value = environment.get("CUBRID")
  if not installed_root_value:
    raise RuntimeError("CUBRID is not set; initialize the CUBRID runtime environment")
  installed_root = Path(installed_root_value).resolve()
  if not installed_root.is_dir():
    raise RuntimeError("CUBRID does not name an installed runtime directory")

  isolated_root = root / "runtime"
  isolated_root.mkdir()
  mutable_directories = {"databases", "log", "tmp", "var"}
  for installed_entry in installed_root.iterdir():
    isolated_entry = isolated_root / installed_entry.name
    if installed_entry.name in mutable_directories:
      isolated_entry.mkdir()
    else:
      isolated_entry.symlink_to(installed_entry, target_is_directory=installed_entry.is_dir())

  for directory in mutable_directories:
    (isolated_root / directory).mkdir(exist_ok=True)
  environment["CUBRID"] = str(isolated_root)
  environment["PATH"] = os.pathsep.join((str(isolated_root / "bin"), environment.get("PATH", "")))


def main() -> int:
  require_program("python3")
  require_program("csql")
  cubrid = require_program("cubrid")

  with tempfile.TemporaryDirectory(prefix="csql-with-history-bypass-") as temporary:
    root = Path(temporary)
    registry = root / "registry"
    database_directory = root / "database"
    run_directory = root / "run"
    registry.mkdir()
    database_directory.mkdir()
    (database_directory / "lob").mkdir()
    run_directory.mkdir()
    database_name = "cwhb{:08x}".format(os.getpid() & 0xFFFFFFFF)

    environment = os.environ.copy()
    isolate_runtime(root, environment)
    environment["CUBRID_DATABASES"] = str(registry)
    createdb = subprocess.run(
      [
        cubrid,
        "createdb",
        "--db-volume-size=32M",
        "--log-volume-size=32M",
        "-F",
        str(database_directory),
        database_name,
        "en_US.utf8",
      ],
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      cwd=run_directory,
      env=environment,
      check=False,
    )
    if createdb.returncode != 0:
      sys.stderr.buffer.write(createdb.stdout)
      sys.stderr.buffer.write(createdb.stderr)
      raise RuntimeError("could not create isolated standalone database")

    sql_file = root / "input.sql"
    sql_file.write_text("select 424244;\n", encoding="utf-8")
    new_history = run_directory / "new-history.sqlite3"
    wrapper_prefix = [
      str(WRAPPER),
      "--history-file",
      str(new_history),
      "--history-limit",
      "17",
      "--no-history",
    ]

    cases = (
      ("pipe SQL", ["-S", "-u", "dba", database_name], b"select 424242;\n"),
      (
        "command SQL",
        ["-S", "-u", "dba", "-c", "select 424243;", database_name],
        None,
      ),
      ("file SQL", ["-S", "-u", "dba", "-i", str(sql_file), database_name], None),
      (
        "failing SQL",
        ["-S", "-u", "dba", "-c", "select * from missing_cwh_table;", database_name],
        None,
      ),
      ("invalid csql option", ["--definitely-invalid", database_name], None),
      (
        "SQL value resembling wrapper option",
        ["-S", "-u", "dba", "-c", "--history-file", database_name],
        None,
      ),
      (
        "password value resembling wrapper option",
        ["-S", "-u", "dba", "-p", "--no-history", "-c", "select 1;", database_name],
        None,
      ),
    )

    for label, arguments, input_bytes in cases:
      direct = run(["csql", *arguments], environment, run_directory, input_bytes)
      wrapped = run([*wrapper_prefix, *arguments], environment, run_directory, input_bytes)
      assert_same(label, direct, wrapped)
      if new_history.exists():
        raise AssertionError("{} created history during bypass".format(label))

    redirected_input = root / "redirected-input.sql"
    redirected_input.write_text("select 424248;\n", encoding="utf-8")
    redirected_input_arguments = ["-S", "-u", "dba", database_name]
    direct = run_with_file_stdin(["csql", *redirected_input_arguments], environment, run_directory, redirected_input)
    wrapped = run_with_file_stdin(
      [*wrapper_prefix, *redirected_input_arguments],
      environment,
      run_directory,
      redirected_input,
    )
    assert_same("regular-file stdin redirection", direct, wrapped)

    existing_history = run_directory / "existing-history.sqlite3"
    sentinel = b"pre-existing history sentinel\n"
    existing_history.write_bytes(sentinel)
    existing_arguments = ["-S", "-u", "dba", "-c", "select 424245;", database_name]
    direct = run(["csql", *existing_arguments], environment, run_directory)
    wrapped = run(
      [str(WRAPPER), "--history-file", str(existing_history), *existing_arguments],
      environment,
      run_directory,
    )
    assert_same("existing history remains unchanged", direct, wrapped)
    if existing_history.read_bytes() != sentinel:
      raise AssertionError("noninteractive invocation changed existing history")

    direct_stdout = root / "direct.stdout"
    direct_stderr = root / "direct.stderr"
    wrapped_stdout = root / "wrapped.stdout"
    wrapped_stderr = root / "wrapped.stderr"
    redirection_arguments = ["-S", "-u", "dba", "-c", "select 424246;", database_name]
    direct_status = run_redirected(
      ["csql", *redirection_arguments],
      environment,
      run_directory,
      direct_stdout,
      direct_stderr,
    )
    wrapped_status = run_redirected(
      [*wrapper_prefix, *redirection_arguments],
      environment,
      run_directory,
      wrapped_stdout,
      wrapped_stderr,
    )
    assert_same(
      "redirected stdout and stderr",
      Invocation(direct_status, direct_stdout.read_bytes(), direct_stderr.read_bytes()),
      Invocation(wrapped_status, wrapped_stdout.read_bytes(), wrapped_stderr.read_bytes()),
    )

    direct_output_file = root / "direct-csql-output.txt"
    wrapped_output_file = root / "wrapped-csql-output.txt"
    output_arguments = ["-S", "-u", "dba", "-c", "select 424247;"]
    direct = run(
      ["csql", *output_arguments, "-o", str(direct_output_file), database_name],
      environment,
      run_directory,
    )
    wrapped = run(
      [
        *wrapper_prefix,
        *output_arguments,
        "-o",
        str(wrapped_output_file),
        database_name,
      ],
      environment,
      run_directory,
    )
    assert_same("csql output-file routing", direct, wrapped)
    if normalized(direct_output_file.read_bytes()) != normalized(wrapped_output_file.read_bytes()):
      raise AssertionError("csql output files differ")
    print("PASS csql output files match")

    if (run_directory / ".csql_history.sqlite3").exists():
      raise AssertionError("noninteractive invocation created the default history file")
    print("PASS bypass did not create new or default history and did not change existing history")
  return 0


def run_redirected(
  command: Sequence[str],
  environment: dict[str, str],
  working_directory: Path,
  stdout_path: Path,
  stderr_path: Path,
) -> int:
  with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
    result = subprocess.run(
      command,
      stdout=stdout,
      stderr=stderr,
      cwd=working_directory,
      env=environment,
      check=False,
    )
  return result.returncode


if __name__ == "__main__":
  try:
    sys.exit(main())
  except (AssertionError, RuntimeError) as error:
    print("FAIL {}".format(error), file=sys.stderr)
    sys.exit(1)

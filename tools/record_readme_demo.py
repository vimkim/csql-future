#!/usr/bin/env python3
"""Record the real demodb standalone editor session as an asciicast and GIF.

Requires a loaded CUBRID environment with a stopped, populated demodb,
csql-future on PATH, and agg for GIF rendering. No database setup is performed.
"""

from __future__ import annotations

import argparse
import codecs
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from pty_test_support import TerminalSession


class Recording(TerminalSession):

  def __init__(self, cwd: Path, environment: dict[str, str]):
    self.events = []
    self.started = time.monotonic()
    self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    super().__init__([shutil.which("bash"), "--noprofile", "--norc", "-i"], cwd, environment)
    self.set_size(24, 88)

  def _read(self) -> None:
    start = len(self.output)
    super()._read()
    content = self.decoder.decode(bytes(self.output[start:]))
    if content:
      self.events.append([round(time.monotonic() - self.started, 4), "o", content])

  def expect(self, text: str) -> None:
    self.read_until(text.encode(), timeout=20)

  def type(self, text: str) -> None:
    start = len(self.output)
    for character in text:
      self.send(character.encode())
      self.read_for(0.07)
    self.read_position = start

  def hold(self, seconds: float = 1.5) -> None:
    self.read_for(seconds)

  def key(self, data: bytes, expected: str = "", hold: float = 0.5) -> None:
    self.send(data)
    if expected:
      self.expect(expected)
    self.hold(hold)


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output-dir", type=Path, default=ROOT / "assets/readme")
  args = parser.parse_args()
  for command in ("bash", "csql", "csql-future", "agg"):
    if shutil.which(command) is None:
      parser.error(f"{command} must be on PATH")

  output = args.output_dir.resolve()
  output.mkdir(parents=True, exist_ok=True)
  environment = os.environ.copy()
  environment.update({
    "TERM": "xterm-256color",
    "PS1": "$ ",
    "PS2": "> ",
    "PROMPT_COMMAND": "",
    "HISTFILE": "/dev/null",
    "PYTHONPATH": str(ROOT / "src"),
  })
  environment.pop("BASH_ENV", None)
  # Temporary cwd gives this recording a fresh history without reading or
  # changing the user's saved queries. The source checkout supplies the editor.
  with tempfile.TemporaryDirectory(prefix="csql-readme-demo-") as temporary:
    session = Recording(Path(temporary), environment)
    try:
      session.expect("$ ")
      session.hold(0.7)
      session.type("csql-future -S -u dba --no-pager demodb")
      session.key(b"\r", "csql-future>", hold=1.5)

      # Complete a keyword, then open the unfiltered hint menu and narrow it.
      session.type("s")
      session.key(b"\t", "> SELECT  keyword", hold=1.6)
      session.key(b"\r")
      session.type(" /*+")
      session.key(b"\t", "query hint", hold=1.8)
      session.type(" PARA")
      session.expect("> PARALLEL  query hint")
      session.hold(1.4)
      session.key(b"\r")

      # Leave the SELECT list empty, pick a real table, then move back to it.
      session.type("(2) */  from ")
      session.key(b"\t", "> athlete  table", hold=2.0)
      session.type("ath")
      session.key(b"\r")
      session.key(b"\x01" + b"\x06" * len("SELECT /*+ PARALLEL(2) */ "))
      session.key(b"\t", "> code  column athlete", hold=2.0)
      session.type("na")
      session.expect("> name  column athlete")
      session.hold(1.2)
      session.key(b"\r")
      session.type(", ")
      session.key(b"\t", "code  column athlete", hold=1.0)
      session.type("co")
      session.key(b"\r")
      session.key(b"\x05", hold=0.2)
      session.type(" limit 3;")
      session.hold(1.0)
      session.key(b"\r", "3 rows selected", hold=0)
      session.expect("csql-future>")
      session.hold(2.8)

      # Show native session-command and argument completion, then quit CSQL.
      session.type(";")
      session.key(b"\t", ";autocommit", hold=1.8)
      session.type("pl")
      session.expect("> ;plan  query plan")
      session.hold(1.2)
      session.key(b"\r")
      session.type(" ")
      session.key(b"\t", "> detail  keyword", hold=1.6)
      session.key(b"\r")
      session.key(b"\r", "csql-future>", hold=1.8)
      session.type(";ex")
      session.key(b"\t", "> ;exit  exit CSQL", hold=1.0)
      session.key(b"\r")
      session.key(b"\r", "$ ", hold=1.0)

      captured = bytes(session.output)
      if b"ERROR:" in captured or b"(no completions)" in captured:
        raise RuntimeError("recording contains a SQL error or empty completion menu")
      # End on the same clean shell prompt as the beginning for a calm loop.
      session.key(b"\x0c", "$ ", hold=0.5)
      loop_end = len(session.events)
      session.send(b"exit\r")
      if session.wait(10) != 0:
        raise RuntimeError("recording shell did not exit successfully")
    finally:
      session.close()

  # Omit the shell's final exit echo while preserving the clean last prompt.
  events = session.events[:loop_end]
  header = {"version": 2, "width": 88, "height": 24,
            "title": "csql-future: real demodb standalone session",
            "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}
  cast = output / "demodb-demo.cast"
  cast.write_text("\n".join(json.dumps(item) for item in [header, *events]) + "\n")
  subprocess.run([
    "agg", "--theme", "1e1e2e,cdd6f4,45475a,f38ba8,a6e3a1,f9e2af,89b4fa,cba6f7,94e2d5,bac2de,585b70,f38ba8,a6e3a1,f9e2af,89b4fa,cba6f7,94e2d5,a6adc8",
    "--font-family", "DejaVu Sans Mono", "--font-size", "18",
    "--line-height", "1.3", "--fps-cap", "15",
    "--last-frame-duration", "1", str(cast), str(output / "demodb-demo.gif"),
  ], check=True)
  print(f"Recorded {events[-1][0]:.1f}s of real terminal output to {cast}")


if __name__ == "__main__":
  main()

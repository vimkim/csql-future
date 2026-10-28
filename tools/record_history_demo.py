#!/usr/bin/env python3
"""Record a separate real demodb Ctrl+R history demo as an asciicast and GIF.

Requires the same loaded CUBRID environment, populated demodb, and recording
tools as record_readme_demo.py. The completion recording is left untouched.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from record_readme_demo import ROOT, Recording
from pty_test_support import AnsiScreen


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
  queries = ("select name from athlete limit 3;", "select code from athlete limit 3;")

  # Build this history through real submissions in a fresh launch directory.
  with tempfile.TemporaryDirectory(prefix="csql-history-demo-") as temporary:
    session = Recording(Path(temporary), environment)
    try:
      session.expect("$ ")
      session.hold(0.7)
      session.type("csql-future -S -u dba --no-pager demodb")
      session.key(b"\r", "csql-future>", hold=1.0)

      for query in queries:
        session.type(query)
        session.hold(0.6)
        session.key(b"\r", "3 rows selected", hold=0)
        session.expect("csql-future>")
        session.hold(1.8)

      # Browse both submissions, then visibly filter two matches down to one.
      history_start = len(session.output)
      session.key(b"\x12", "History search mode", hold=2.0)
      for query in queries:
        if query.encode() not in session.output[history_start:]:
          raise RuntimeError("a submitted query is missing from history search")
      session.key(b"\x1b[B", "> " + queries[0], hold=1.6)
      session.type("name")
      session.hold(2.4)
      filtered = AnsiScreen(rows=24, columns=88)
      filtered.feed(bytes(session.output[history_start:]))
      visible = "\n".join(filtered.display())
      if "> " + queries[0] not in visible or queries[1] in visible:
        raise RuntimeError("name search did not visibly narrow history to one query")

      # Enter recalls into the editor; a separate Enter executes the query.
      recall_start = len(session.output)
      session.key(b"\r", queries[0], hold=2.2)
      if b"3 rows selected" in session.output[recall_start:]:
        raise RuntimeError("history recall unexpectedly executed the query")
      session.key(b"\r", "3 rows selected", hold=0)
      session.expect("csql-future>")
      session.hold(2.0)
      session.type(";exit")
      session.key(b"\r", "$ ", hold=1.0)

      captured = bytes(session.output)
      if b"ERROR:" in captured or captured.count(b"3 rows selected") != 3:
        raise RuntimeError("recording did not execute exactly three successful queries")
      session.key(b"\x0c", "$ ", hold=0.5)
      loop_end = len(session.events)
      session.send(b"exit\r")
      if session.wait(10) != 0:
        raise RuntimeError("recording shell did not exit successfully")
    finally:
      session.close()

  events = session.events[:loop_end]
  header = {"version": 2, "width": 88, "height": 24,
            "title": "csql-future: search and recall real demodb query history",
            "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}
  cast = output / "history-demo.cast"
  cast.write_text("\n".join(json.dumps(item) for item in [header, *events]) + "\n")
  subprocess.run([
    "agg", "--quiet", "--theme",
    "1e1e2e,cdd6f4,45475a,f38ba8,a6e3a1,f9e2af,89b4fa,cba6f7,94e2d5,bac2de,585b70,f38ba8,a6e3a1,f9e2af,89b4fa,cba6f7,94e2d5,a6adc8",
    "--font-family", "DejaVu Sans Mono", "--font-size", "18",
    "--line-height", "1.3", "--fps-cap", "15",
    "--last-frame-duration", "1", str(cast), str(output / "history-demo.gif"),
  ], check=True)
  print(f"Recorded {events[-1][0]:.1f}s of real terminal output to {cast}")


if __name__ == "__main__":
  main()

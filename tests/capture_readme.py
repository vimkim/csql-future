"""Capture the actual editor with demo data for static README illustrations."""

from html import escape
from pathlib import Path
import time
from unittest.mock import patch

from csql_future.cli import SubmissionHistory
from pty_test_support import AnsiScreen
from test_editable_session import EditableSessionTest


ASSETS = Path(__file__).resolve().parents[1] / 'assets/readme'


def write_capture(name: str, title: str, description: str, session) -> None:
  session.read_for(0.1)
  screen = AnsiScreen(rows=18, columns=64)
  screen.feed(bytes(session.output))
  lines = screen.display()
  first = next(index for index, line in enumerate(lines) if 'csql-future>' in line)
  lines = lines[first:]
  while lines and not lines[-1].strip():
    lines.pop()
  height = 120 + len(lines) * 42
  svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title desc">',
    f'  <title id="title">{escape(title)}</title>',
    f'  <desc id="desc">{escape(description)}</desc>',
    f'  <rect width="1200" height="{height}" rx="20" fill="#1e1e2e"/>',
    '  <g font-family="DejaVu Sans Mono, ui-monospace, monospace" font-size="28" xml:space="preserve" style="white-space:pre">',
  ]
  for index, line in enumerate(lines):
    color = '#cba6f7' if 'csql-future>' in line else '#cdd6f4'
    if line.lstrip().startswith('>'):
      color = '#89b4fa'
    if 'mode' in line:
      color = '#a6adc8'
    svg.append(f'    <text x="48" y="{72 + index * 42}" fill="{color}">{escape(line)}</text>')
  svg.extend(['  </g>', '</svg>', ''])
  (ASSETS / f'{name}.svg').write_text('\n'.join(svg))


def capture_history() -> None:
  fixture = EditableSessionTest()
  fixture.setUp()
  try:
    history = SubmissionHistory(fixture.root / '.csql_history.sqlite3', 10000, False)
    try:
      for index, query in enumerate((
        'select id, name from employees;',
        'select department from employees;',
        'select name from employees where id = 42;',
      )):
        with patch('csql_future.cli.time.time', return_value=time.time() - (3 - index) * 180):
          history.save(query)
    finally:
      history.close()
    session = fixture.start()
    session.set_size(18, 64)
    session.read_until(b'csql-future>')
    session.send(b'\x12employees')
    session.read_until(b'History search mode')
    write_capture('history', 'Search your saved SQL',
                  'Actual editor output: Ctrl+R searches illustrative saved employee queries.', session)
    session.send(b'\x11')
    if session.wait() != 0:
      raise RuntimeError('history capture did not exit cleanly')
  finally:
    fixture.doCleanups()


def capture_completion() -> None:
  fixture = EditableSessionTest()
  fixture.setUp()
  try:
    fixture.environment['SYNTHETIC_CATALOG'] = '\n'.join((
      'kind\tlogin_name\towner_name\tclass_name\titem_name\titem_type',
      'relation\tDBA\tDBA\temployees\temployees\tCLASS',
      *[f'column\tDBA\tDBA\temployees\t{name}\tINSTANCE' for name in ('id', 'name', 'department')],
    ))
    session = fixture.start(['-C', '-u', 'dba'])
    session.set_size(18, 64)
    session.read_until(b'csql-future>')
    session.send(b'select e. from employees e;')
    session.send(b'\x1b[D' * len(' from employees e;') + b'\t')
    session.read_until(b'> department  column e')
    write_capture('completion', 'Complete names from your schema',
                  'Actual editor output: e. offers department, id, and name from an illustrative employees catalog.', session)
    session.send(b'\x1b')
    session.read_for(0.05)
    session.send(b'\x11')
    if session.wait() != 0:
      raise RuntimeError('completion capture did not exit cleanly')
  finally:
    fixture.doCleanups()


if __name__ == '__main__':
  capture_history()
  capture_completion()
  print('Captured history.svg and completion.svg from the editor with demo fixtures.')

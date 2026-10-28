"""Verify schema completion using isolated real CUBRID databases."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from verify_editable_csql import Session, checked_run
from verify_real_csql import isolate_runtime, require_program
from csql_future.metadata import CATALOG_QUERY, parse_catalog


def check_completion(mode: str, database: str, environment: dict[str, str], root: Path) -> None:
  history = root / ('history-' + mode + '.sqlite3')
  session = Session(['--history-file', str(history), mode, '-u', 'dba', '--no-pager', database], environment, root)
  try:
    session.expect('csql-future>')
    session.send(b'select * from co\t')
    session.expect('> code  table DBA')
    session.expect('coding  table DBA')
    session.send(b'\x0e\r')
    session.read_for(0.1)
    with closing(sqlite3.connect(history)) as connection:
      assert connection.execute('SELECT count(*) FROM submissions').fetchone()[0] == 0
    session.send(b';\r')
    session.expect('1 row selected')
    session.expect('csql-future>')
    session.send(b'select * from code c where c.na\t')
    session.expect('name  column c')
    session.send(b"\r='code-row';\r")
    session.expect('1 row selected')
    session.expect('csql-future>')
    assert session.finish() == 0
    with closing(sqlite3.connect(history)) as connection:
      commands = [row[0] for row in connection.execute('SELECT command FROM submissions ORDER BY id')]
    assert commands == ['select * from coding;', "select * from code c where c.name='code-row';", ';exit'], commands
    print('PASS real {} table/column completion and history boundaries'.format(mode), flush=True)
  finally:
    session.close()


def check_show_completion(mode: str, database: str, environment: dict[str, str], root: Path) -> None:
  history = root / ('show-history-' + mode + '.sqlite3')
  session = Session(['--history-file', str(history), mode, '-u', 'dba', '--no-pager', database], environment, root)
  cases = (
    (b'show ta;\x02\t', '> TABLES  keyword', 'show TABLES;'),
    (b'show full ta;\x02\t', '> TABLES  keyword', 'show full TABLES;'),
    (b'show columns from co;\x02\t', '> code  table DBA', 'show columns from code;'),
    (b'show full columns in dba.[co];\x02\t', '> [code]  table DBA', 'show full columns in dba.[code];'),
  )
  commands = []
  try:
    session.expect('csql-future>')
    for keys, menu, command in cases:
      session.send(keys)
      session.expect(menu)
      session.send(b'\r')
      session.read_for(0.1)
      with closing(sqlite3.connect(history)) as connection:
        assert connection.execute('SELECT count(*) FROM submissions').fetchone()[0] == len(commands)
      session.send(b'\r')
      session.expect('2 rows selected')
      session.expect('csql-future>')
      commands.append(command)
    assert session.finish() == 0
    with closing(sqlite3.connect(history)) as connection:
      actual = [row[0] for row in connection.execute('SELECT command FROM submissions ORDER BY id')]
    assert actual == commands + [';exit'], actual
    print('PASS real {} SHOW completion, quoted targets, semicolons and history boundaries'.format(mode), flush=True)
  finally:
    session.close()


def main() -> None:
  cubrid = require_program('cubrid')
  csql = require_program('csql')
  with tempfile.TemporaryDirectory(prefix='csql-completion-') as temporary:
    root = Path(temporary)
    registry = root / 'registry'
    volumes = root / 'volumes'
    run = root / 'run'
    for directory in (registry, volumes, run, volumes / 'lob'):
      directory.mkdir()
    environment = os.environ.copy()
    isolate_runtime(root, environment)
    environment['CUBRID_DATABASES'] = str(registry)
    environment['TERM'] = 'xterm-256color'
    database = 'cwhc{:08x}'.format(os.getpid())
    checked_run([cubrid, 'createdb', '--db-volume-size=32M', '--log-volume-size=32M',
                 '-F', str(volumes), database, 'en_US.utf8'], environment, run)
    checked_run([csql, '-S', '-u', 'dba', '-c', """
      CREATE TABLE code (id INTEGER, name VARCHAR(40));
      CREATE TABLE coding (id INTEGER, language_name VARCHAR(40));
      INSERT INTO code VALUES (1, 'code-row');
      INSERT INTO coding VALUES (2, 'coding-row');
      CREATE USER cwh_reader PASSWORD 'test-only-password';
      GRANT SELECT ON code TO cwh_reader;
    """, database], environment, run)
    result = subprocess.run([csql, '-S', '-u', 'dba', '-r', '-t', '-c', CATALOG_QUERY, database],
                            env=environment, cwd=run, capture_output=True, timeout=10, check=True)
    schema = parse_catalog(result.stdout)
    assert {'code', 'coding'} <= {r.name for r in schema.relations}, result.stdout
    check_completion('-S', database, environment, run)
    check_show_completion('-S', database, environment, run)
    restricted = subprocess.run([csql, '-S', '-u', 'cwh_reader', '-p', 'test-only-password',
                                 '-r', '-t', '-c', CATALOG_QUERY, database],
                                env=environment, cwd=run, capture_output=True, timeout=10, check=True)
    restricted_schema = parse_catalog(restricted.stdout)
    assert {r.name for r in restricted_schema.relations} == {'code'}, restricted.stdout
    print('PASS real catalog respects user permissions', flush=True)
    server_command(cubrid, 'start', database, environment, run)
    try:
      check_completion('-C', database, environment, run)
      check_show_completion('-C', database, environment, run)
      check_refresh(database, environment, run)
    finally:
      server_command(cubrid, 'stop', database, environment, run)


def server_command(cubrid: str, action: str, database: str, environment: dict[str, str], root: Path) -> None:
  with (root / ('server-' + action + '.stdout')).open('wb') as stdout, (root / ('server-' + action + '.stderr')).open('wb') as stderr:
    subprocess.run([cubrid, 'server', action, database], env=environment, cwd=root,
                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                   start_new_session=True, timeout=30, check=True)


def check_refresh(database: str, environment: dict[str, str], root: Path) -> None:
  session = Session(['-C', '-u', 'dba', '--no-pager', database], environment, root)
  try:
    session.expect('csql-future>')
    session.send(b'select * from co\t')
    session.expect('> code  table DBA')
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'\x03')
    session.submit('create table coder (id integer);', 'Execute OK.')
    session.send(b'select * from coder\t')
    session.expect('(no completions)')
    session.send(b'\x1b')
    session.read_for(0.1)
    session.send(b'\x03;refresh-completions\r')
    session.read_for(0.2)
    session.send(b'select * from coder\t')
    session.expect('> coder  table DBA')
    session.send(b'\r;\r')
    session.expect('0 row selected')
    session.expect('csql-future>')
    assert session.finish() == 0
    print('PASS real client/server refresh discovers committed DDL', flush=True)
  finally:
    session.close()


if __name__ == '__main__':
  main()

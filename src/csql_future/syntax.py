"""Completion grammar for CUBRID 11.4 inspection and management commands.

This recognizes unfinished input for suggestions. CSQL remains the SQL parser.
"""

from dataclasses import dataclass
from itertools import product

from .completion_data import SHOW_FIELDS


SESSION_COMMANDS = {
  'read': 'read a file into the query buffer',
  'write': 'write the query buffer to a file',
  'append': 'append the query buffer to a file',
  'print': 'print the query buffer',
  'shell': 'open the configured shell',
  'cd': 'change the client working directory',
  'exit': 'exit CSQL',
  'clear': 'clear the query buffer',
  'edit': 'edit the query buffer',
  'list': 'display the query buffer',
  'run': 'execute the query buffer',
  'xrun': 'execute and clear the query buffer',
  'commit': 'commit the transaction',
  'rollback': 'roll back the transaction',
  'autocommit': 'set automatic commit: on/off',
  'restart': 'reconnect to the database',
  'checkpoint': 'issue a checkpoint (DBA, --sysadm)',
  'killtran': 'list or terminate transactions (DBA, --sysadm)',
  'shell_cmd': 'configure the shell',
  'editor_cmd': 'configure the editor',
  'print_cmd': 'configure the print command',
  'pager_cmd': 'configure the pager',
  'formatter_cmd': 'configure the formatter',
  'date': 'display the date and time',
  'database': 'display the database and host',
  'schema': 'display a table schema',
  'trigger': 'display trigger definitions',
  'get': 'read a system parameter',
  'set': 'change a dynamic system parameter',
  'string-width': 'set string output width',
  'column-width': 'set column output width',
  'plan': 'query plan: simple/detail/off',
  'info': 'display internal information',
  'time': 'display query execution time: on/off',
  'server-output': 'display DBMS_OUTPUT messages: on/off',
  'line-output': 'display values on separate lines: on/off',
  'historylist': 'display native CSQL history',
  'historyread': 'read a native history entry',
  'trace': 'SQL trace: on/off text/json (client/server)',
  'singleline': 'single-line execution: on/off',
  'connect': 'connect as another user',
  '.hist': 'collect execution statistics: on/off (DBA)',
  '.clear_hist': 'clear execution statistics',
  '.dump_hist': 'display execution statistics',
  '.x_hist': 'display and clear execution statistics',
  'help': 'display native CSQL help',
  'refresh-completions': 'refresh wrapper metadata (client/server)',
}


@dataclass(frozen=True)
class Context:
  words: tuple[str, ...] = ()
  target: str = ''
  qualifier: tuple[str, ...] = ()
  fields: tuple[str, ...] = ()
  detail: str = 'keyword'


@dataclass(frozen=True)
class Rule:
  pattern: tuple[str, ...]
  fields: tuple[str, ...] = ()
  detail: str = 'keyword'


RULES: list[Rule] = []


def add(pattern: str, family: str = '', filters: tuple[str, ...] = (), diagnostic: bool = False) -> None:
  fields = SHOW_FIELDS.get(family, ())
  detail = 'keyword (DBA)' if diagnostic else 'keyword'
  for path in product(*(part.split('|') for part in pattern.split())):
    RULES.append(Rule(path, (), detail))
    for tail in filters:
      RULES.append(Rule((*path, tail, '<filter>' if tail == 'WHERE' else '<value>'), fields, detail))


for full in ('', 'FULL '):
  for name, target in (('TABLES', ''), ('COLUMNS', ' FROM|IN <relation>'), ('TIMEZONES', '')):
    family = 'SHOW ' + full + name
    add(family + target, family, ('LIKE', 'WHERE') if name != 'TIMEZONES' else ('LIKE',))
add('SHOW INDEX|INDEXES|KEYS FROM|IN <relation>')
add('SHOW COLLATION', 'SHOW COLLATION', ('LIKE',))
add('SHOW GRANTS FOR <user>')
add('SHOW CREATE TABLE <table>')
add('SHOW CREATE VIEW <view>')
add('SHOW ACCESS STATUS', 'SHOW ACCESS STATUS', ('LIKE', 'WHERE'), diagnostic=True)
add('SHOW EXEC STATISTICS')
add('SHOW EXEC STATISTICS ALL')
add('SHOW TRACE')
for command in ('DESC', 'DESCRIBE', 'EXPLAIN'):
  add(command + ' <relation>')
add('SHOW VOLUME HEADER OF <number>', diagnostic=True)
add('SHOW LOG HEADER', diagnostic=True)
add('SHOW LOG HEADER OF <value>', diagnostic=True)
add('SHOW ARCHIVE LOG HEADER OF <value>', diagnostic=True)
for kind in ('HEADER', 'CAPACITY'):
  for all_objects in ('', 'ALL '):
    add('SHOW ' + all_objects + 'HEAP ' + kind + ' OF <table>', diagnostic=True)
  add('SHOW INDEX ' + kind + ' OF <index>', diagnostic=True)
  add('SHOW ALL INDEXES ' + kind + ' OF <table>', diagnostic=True)
for kind in ('HEADER', 'SLOTS'):
  add('SHOW SLOTTED PAGE ' + kind + ' OF|WHERE VOLUME = <number> AND PAGE = <number>', diagnostic=True)
add('SHOW CRITICAL SECTIONS', diagnostic=True)
add('SHOW TRAN|TRANSACTION TABLES', 'SHOW TRANSACTION TABLES', ('WHERE',), diagnostic=True)
add('SHOW THREADS', 'SHOW THREADS', ('WHERE',), diagnostic=True)
add('SHOW JOB QUEUES', diagnostic=True)
add('SHOW PAGE BUFFER STATUS', diagnostic=True)
for target in ('<tables>', 'ALL CLASSES', 'CATALOG CLASSES'):
  add('UPDATE STATISTICS ON ' + target)
  add('UPDATE STATISTICS ON ' + target + ' WITH FULLSCAN')
add('SET TRACE ON|OFF')
add('SET TRACE ON|OFF OUTPUT TEXT|JSON')
add('SET OPTIMIZATION LEVEL <number>')
add('GET OPTIMIZATION LEVEL')
add('GET OPTIMIZATION LEVEL TO|INTO <value>')
add('GET TRANSACTION ISOLATION LEVEL')
for isolation in ('READ COMMITTED', 'REPEATABLE READ', 'SERIALIZABLE'):
  add('SET TRANSACTION ISOLATION LEVEL ' + isolation)
add('SET SYSTEM PARAMETERS <value>')
for command in ('autocommit', 'time', 'server-output', 'line-output', 'singleline', '.hist'):
  add(';' + command + ' on|off')
add(';plan simple|detail|off')
add(';trace on|off')
add(';trace on|off text|json')
add(';edit format|fmt')
add(';schema <relation>')
add(';connect <user>')
add(';info schema|stats <relation>')
add(';info lock|workspace|plan|trigger|deferred')


def match(rule: Rule, tokens: list) -> Context | None:
  """Return the next terminal or object, preserving unfinished qualification."""
  index = 0
  for atom in rule.pattern:
    if atom == '<filter>':
      return Context(fields=rule.fields, detail=rule.detail)
    if index == len(tokens):
      return Context(target=atom[1:-1], detail=rule.detail) if atom.startswith('<') else Context((atom,), detail=rule.detail)
    token = tokens[index]
    if not atom.startswith('<'):
      if token.text.upper() != atom.upper() or token.kind == 'identifier':
        return None
      index += 1
    elif atom in ('<value>', '<number>'):
      if atom == '<number>' and not token.text.isdigit():
        return None
      index += 1
    else:
      names = []
      while index < len(tokens):
        token = tokens[index]
        if token.kind not in ('word', 'identifier') or token.keyword in ('ALL', 'CATALOG'):
          return None
        names.append(token.name)
        index += 1
        if index < len(tokens) and tokens[index].text == '.':
          index += 1
          if index == len(tokens):
            return Context(target=atom[1:-1], qualifier=tuple(names), detail=rule.detail)
          continue
        if atom == '<tables>' and index < len(tokens) and tokens[index].text == ',':
          index += 1
          names = []
          if index == len(tokens):
            return Context(target='table', detail=rule.detail)
          continue
        break
  return Context() if index == len(tokens) else None


def contexts(tokens: list) -> list[Context] | None:
  if not tokens:
    return None
  first = tokens[0].keyword
  if first == 'UPDATE' and (len(tokens) == 1 or tokens[1].keyword != 'STATISTICS'):
    return None
  if first not in ('SHOW', 'DESC', 'DESCRIBE', 'EXPLAIN', 'SET', 'GET', 'UPDATE') and not tokens[0].text.startswith(';'):
    return None
  return [context for rule in RULES if (context := match(rule, tokens)) is not None]

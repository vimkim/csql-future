"""Inspection, session and catalog completion behavior at unfinished cursors."""

import unittest

from csql_future.completion import CompletionMenu, Relation, Schema, suggest


SCHEMA = Schema('DBA', (
  Relation('DBA', 'athlete', 'CLASS', ('code', 'name'), indexes=('idx_name', 'idx_code')),
  Relation('OTHER', 'athlete', 'CLASS', ('other_id',), indexes=('idx_other',)),
  Relation('DBA', 'athlete_view', 'VCLASS', ('name',)),
  Relation('DBA', 'db_class', 'VCLASS', ('class_name', 'owner_name'), True),
  Relation('DBA', 'db_index', 'VCLASS', ('index_name',), True),
  Relation('DBA', 'db_index_key', 'VCLASS', ('key_attr_name',), True),
  Relation('DBA', '_db_class', 'CLASS', ('class_name',), True),
), ('DBA', 'PUBLIC', 'reader'), 'demo')


class CommandCompletionTest(unittest.TestCase):

  def names(self, marked, schema=SCHEMA):
    cursor = marked.index('|') if '|' in marked else len(marked)
    return [c.text for c in suggest(marked.replace('|', ''), cursor, schema).candidates]

  def accept(self, marked, candidate):
    text, cursor = marked.replace('|', ''), marked.index('|')
    menu = CompletionMenu()
    menu.open(text, cursor, suggest(text, cursor, SCHEMA))
    menu.selected = next(i for i, c in enumerate(menu.suggestions.candidates) if c.text == candidate)
    return menu.accept()[0]

  def test_inspection_grammar_and_modifiers_without_a_database(self):
    cases = {
      'SHOW CREATE ': ['TABLE', 'VIEW'],
      'SHOW INDEX ': ['CAPACITY', 'FROM', 'HEADER', 'IN'],
      'SHOW INDEXES ': ['FROM', 'IN'],
      'SHOW KEYS ': ['FROM', 'IN'],
      'SHOW COLLATION ': ['LIKE'],
      'SHOW TIMEZONES ': ['LIKE'],
      'SHOW FULL TIMEZONES ': ['LIKE'],
      'SHOW GRANTS ': ['FOR'],
      'SHOW ACCESS ': ['STATUS'],
      'SHOW ACCESS STATUS ': ['LIKE', 'WHERE'],
      'SHOW EXEC STATISTICS ': ['ALL'],
      'SHOW ARCHIVE LOG HEADER ': ['OF'],
      'SHOW LOG HEADER ': ['OF'],
      'SHOW VOLUME HEADER ': ['OF'],
      'SHOW HEAP HEADER ': ['OF'],
      'SHOW HEAP CAPACITY ': ['OF'],
      'SHOW ALL ': ['HEAP', 'INDEXES'],
      'SHOW ALL HEAP ': ['CAPACITY', 'HEADER'],
      'SHOW ALL INDEXES ': ['CAPACITY', 'HEADER'],
      'SHOW INDEX HEADER ': ['OF'],
      'SHOW INDEX CAPACITY ': ['OF'],
      'SHOW SLOTTED PAGE ': ['HEADER', 'SLOTS'],
      'SHOW SLOTTED PAGE HEADER ': ['OF', 'WHERE'],
      'SHOW SLOTTED PAGE SLOTS OF ': ['VOLUME'],
      'SHOW SLOTTED PAGE SLOTS OF VOLUME ': ['='],
      'SHOW SLOTTED PAGE SLOTS OF VOLUME = 0 ': ['AND'],
      'SHOW SLOTTED PAGE SLOTS OF VOLUME = 0 AND ': ['PAGE'],
      'SHOW SLOTTED PAGE SLOTS OF VOLUME = 0 AND PAGE ': ['='],
      'SHOW CRITICAL ': ['SECTIONS'],
      'SHOW TRANSACTION ': ['TABLES'],
      'SHOW TRAN TABLES ': ['WHERE'],
      'SHOW THREADS ': ['WHERE'],
      'SHOW JOB ': ['QUEUES'],
      'SHOW PAGE BUFFER ': ['STATUS'],
    }
    for draft, expected in cases.items():
      with self.subTest(draft=draft):
        self.assertEqual(expected, self.names(draft, Schema()))

  def test_objects_are_filtered_by_command_kind(self):
    for command in ('DESC ', 'DESCRIBE ', 'EXPLAIN ', 'SHOW COLUMNS FROM ', 'SHOW INDEX FROM '):
      self.assertEqual(['athlete', 'athlete_view', 'OTHER.athlete'], self.names(command + 'at'))
    for command in ('SHOW CREATE TABLE ', 'SHOW HEAP HEADER OF ', 'SHOW ALL HEAP CAPACITY OF ',
                    'SHOW ALL INDEXES HEADER OF ', 'SHOW ALL INDEXES CAPACITY OF '):
      self.assertEqual(['athlete', 'OTHER.athlete'], self.names(command + 'at'))
    self.assertEqual(['athlete_view'], self.names('SHOW CREATE VIEW at'))
    self.assertEqual(['reader'], self.names('SHOW GRANTS FOR re'))
    self.assertEqual(['athlete'], self.names('SHOW CREATE TABLE [OTHER].at'))

  def test_index_names_follow_the_target_table_and_owner(self):
    self.assertEqual(['athlete.', 'OTHER.athlete.'], self.names('SHOW INDEX HEADER OF at'))
    self.assertEqual(['idx_code', 'idx_name'], self.names('SHOW INDEX HEADER OF athlete.idx'))
    self.assertEqual(['idx_other'], self.names('SHOW INDEX CAPACITY OF other.athlete.idx'))
    self.assertEqual(['idx_other'], self.names('SHOW INDEX CAPACITY OF [OTHER].[athlete].idx'))
    self.assertEqual([], self.names('SHOW INDEX HEADER OF missing.idx'))
    self.assertEqual('SHOW INDEX HEADER OF other.athlete.idx_other;',
                     self.accept('SHOW INDEX HEADER OF other.athlete.idx|wrong;', 'idx_other'))

  def test_filter_fields_belong_to_show_results(self):
    cases = {
      'SHOW COLUMNS FROM athlete WHERE fi': ['Field'],
      'SHOW FULL COLUMNS FROM athlete WHERE co': ['[Collation]', 'Comment'],
      'SHOW COLUMNS FROM athlete WHERE na': [],
      'SHOW FULL TABLES WHERE tab': ['Table_type', 'tables_in_demo'],
      'SHOW TABLES WHERE tab': ['tables_in_demo'],
      'SHOW THREADS WHERE st': ['Status'],
      'SHOW TRANSACTION TABLES WHERE client_t': ['Client_type'],
      'SHOW ACCESS STATUS WHERE last_a': ['last_access_host', 'last_access_time'],
      'SHOW THREADS WHERE Status = \'FREE\' AND tran_i': ['Tran_index'],
    }
    for draft, expected in cases.items():
      with self.subTest(draft=draft):
        self.assertEqual(expected, self.names(draft))
    self.assertEqual('SHOW COLUMNS FROM athlete WHERE Field;',
                     self.accept('SHOW COLUMNS FROM athlete WHERE fi|wrong;', 'Field'))

  def test_all_session_names_and_argument_completion(self):
    self.assertEqual([';schema'], self.names(';sc'))
    self.assertEqual([';plan'], self.names('  ;PL'))
    self.assertEqual([';.hist'], self.names(';.h'))
    self.assertIn(';refresh-completions', self.names(';'))
    for command in ('autocommit', 'time', 'line-output', 'server-output', 'singleline', '.hist'):
      self.assertEqual(['off', 'on'], self.names(';' + command + ' '))
    self.assertEqual(['detail', 'off', 'simple'], self.names(';plan '))
    self.assertEqual(['json', 'text'], self.names(';trace on '))
    self.assertEqual(['detail'], self.names(';pl de'))
    self.assertEqual(['athlete', 'athlete_view', 'OTHER.athlete'], self.names(';schema at'))
    self.assertEqual(['athlete', 'athlete_view', 'OTHER.athlete'], self.names(';info stats at'))
    self.assertEqual(['reader'], self.names(';connect re'))
    self.assertEqual('  ;schema athlete;', self.accept('  ;sc|wrong athlete;', ';schema'))
    self.assertEqual(';schema other.athlete', self.accept(';schema other.at|wrong', 'athlete'))
    self.assertEqual([], self.names(';unknown at'))

  def test_parameters_are_dynamic_only_when_setting(self):
    self.assertEqual(['lock_escalation', 'lock_timeout'], self.names(';get lock_'))
    self.assertEqual(['lock_timeout='], self.names(';set lock_'))
    self.assertEqual(['no', 'yes'], sorted(self.names(';set block_ddl_statement=')))
    self.assertEqual(['no'], self.names(';set block_ddl_statement=n'))
    self.assertEqual([], self.names(';set max_clients'))
    self.assertEqual([], self.names(';get block_ddl_statement=y'))
    self.assertEqual(';set lock_timeout=12', self.accept(';set lock_t|wrong=12', 'lock_timeout'))
    self.assertEqual(';get lock_timeout', self.accept(';get lock_t|wrong', 'lock_timeout'))
    self.assertEqual("SET SYSTEM PARAMETERS 'lock_timeout=';",
                     self.accept("SET SYSTEM PARAMETERS 'lock_t|wrong';", 'lock_timeout='))
    self.assertEqual(['DEFAULT'], self.names("SET SYSTEM PARAMETERS 'lock_timeout=D"))
    self.assertEqual(['block_ddl_statement='], self.names("SET SYSTEM PARAMETERS 'lock_timeout=1;block_dd"))
    self.assertEqual("SET SYSTEM PARAMETERS 'block_ddl_statement=no';",
                     self.accept("SET SYSTEM PARAMETERS 'block_ddl_statement=n|wrong';", 'no'))

  def test_catalogs_use_literal_prefixes_and_keep_user_tables_prominent(self):
    self.assertEqual(['db_index', 'db_index_key'], self.names('select * from db_in'))
    self.assertEqual(['_db_class'], self.names('select * from _db'))
    self.assertEqual(['db_class'], self.names('select * from dba.db_cl'))
    self.assertEqual(['db_class'], self.names('db_cl'))
    self.assertNotIn('db_class', self.names('select * from '))
    self.assertEqual(['class_name'], self.names('select d.cl| from db_class d'))
    reader = Schema('reader', SCHEMA.relations)
    self.assertEqual(['db_class'], self.names('select * from db_cl', reader))
    self.assertEqual(['owner_name'], self.names('select d.ow| from db_class d', reader))
    extra = Schema('reader', (*SCHEMA.relations, Relation('INFORMATION_SCHEMA', 'views', 'VCLASS', ('table_name',), True)))
    self.assertEqual(['views'], self.names('select * from information_schema.vi', extra))
    self.assertEqual([], self.names('select v.tab| from views v', extra))
    self.assertEqual(['table_name'], self.names('select v.tab| from information_schema.views v', extra))

  def test_management_sequences_and_repeated_statistics_targets(self):
    cases = {
      'UPDATE sta': ['STATISTICS'],
      'UPDATE STATISTICS ': ['ON'],
      'UPDATE STATISTICS ON athlete, at': ['athlete', 'OTHER.athlete'],
      'UPDATE STATISTICS ON athlete WITH ': ['FULLSCAN'],
      'UPDATE STATISTICS ON CATALOG ': ['CLASSES'],
      'SET TRACE ': ['OFF', 'ON'],
      'SET TRACE ON ': ['OUTPUT'],
      'SET TRACE ON OUTPUT ': ['JSON', 'TEXT'],
      'SHOW tr': ['TRACE', 'TRAN', 'TRANSACTION'],
      'SET OPTIMIZATION ': ['LEVEL'],
      'GET TRANSACTION ISOLATION ': ['LEVEL'],
    }
    for draft, expected in cases.items():
      with self.subTest(draft=draft):
        self.assertEqual(expected, self.names(draft))

  def test_comments_strings_quotes_and_other_statements_do_not_leak(self):
    self.assertEqual(['HEADER'], self.names('/* lead */ SHOW INDEX /* gap */ he'))
    self.assertEqual(['TABLE'], self.names('select 1; SHOW CREATE t'))
    self.assertEqual(['name'], self.names('SHOW TABLES; select a.na| from athlete a'))
    self.assertEqual([], self.names('SHOW "he'))
    self.assertEqual([], self.names('SHOW broken FROM at'))
    for marked in ('SHOW THREADS WHERE Status=\'fr', ';schema \'at', 'SHOW /* he'):
      self.assertFalse(suggest(marked, len(marked), SCHEMA).allowed)


if __name__ == '__main__':
  unittest.main()

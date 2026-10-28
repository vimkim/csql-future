"""CUBRID hint comments complete names without changing the surrounding SQL."""

import unittest

from csql_future.completion import CompletionMenu, Relation, Schema, suggest


class HintCompletionTest(unittest.TestCase):

  def suggestions(self, marked, schema=Schema()):
    cursor = marked.index('|') if '|' in marked else len(marked)
    return suggest(marked.replace('|', ''), cursor, schema)

  def names(self, marked, schema=Schema()):
    return [c.text for c in self.suggestions(marked, schema).candidates]

  def test_hint_names_work_without_metadata_in_all_comment_styles(self):
    for opener in ('/*+', '--+', '//+'):
      for prefix in ('re', 'Re', 'RE'):
        with self.subTest(opener=opener, prefix=prefix):
          self.assertEqual(['RECOMPILE', 'REEXECUTE'], self.names('select ' + opener + ' ' + prefix))
      self.assertEqual(['RECOMPILE', 'REEXECUTE'], self.names('select ' + opener + 're'))
      result = self.suggestions('select ' + opener + ' ')
      self.assertTrue(result.allowed)
      names = [c.text for c in result.candidates]
      for name in ('ORDERED', 'USE_NL', 'USE_HASH', 'NO_MERGE', 'INDEX_SS',
                   'USE_INSERT_IDX', 'USE_UPDATE_IDX', 'NO_UNNEST', 'PARALLEL',
                   'LOCK_TIMEOUT', 'SQL_NO_CACHE', 'MATERIALIZE'):
        self.assertIn(name, names)
      self.assertNotIn('SELECT', names)
      self.assertTrue(all(c.detail == 'query hint' for c in result.candidates))
    self.assertEqual(self.names('select /*+ '), self.names('select /*+|*/ 1;'))
    self.assertEqual(self.names('select /*+ '), self.names('select /*+ | */ 1;'))

  def test_multiple_hints_and_multiline_block_comments(self):
    for marked in ('select /*+ ordered re',
                   'select /*+ ordered\n  re| */ 1;',
                   'select /*+ USE_NL(t) re| */ * from t',
                   'select /*+ LEADING(t, u) ORDERED re',
                   'update /*+ ordered re',
                   'delete /*+ re',
                   'merge /*+ re',
                   'select --+ ordered re',
                   'select //+ ordered re'):
      with self.subTest(draft=marked):
        self.assertEqual(['RECOMPILE', 'REEXECUTE'], self.names(marked))
    self.assertEqual(['USE_DESC_IDX', 'USE_HASH', 'USE_IDX', 'USE_INSERT_IDX', 'USE_MERGE', 'USE_NL',
                      'USE_SBR', 'USE_UPDATE_IDX'], self.names('select /*+ ordered use_| */ 1;'))

  def test_acceptance_replaces_only_the_hint_name_and_keeps_delimiters_and_arguments(self):
    cases = (
      ('select /*+ re|wrong ORDERED */ 1;', 'RECOMPILE',
       'select /*+ RECOMPILE ORDERED */ 1;'),
      ('select /*+re|wrong*/ 1;', 'RECOMPILE', 'select /*+RECOMPILE*/ 1;'),
      ('select /*+ ordered us|wrong(t, u) */ * from t, u;', 'USE_NL',
       'select /*+ ordered USE_NL(t, u) */ * from t, u;'),
      ('select /*+ |rewrong */ 1;', 'RECOMPILE', 'select /*+ RECOMPILE */ 1;'),
      ('select /*+ ordered re|', 'RECOMPILE', 'select /*+ ordered RECOMPILE'),
      ('select --+ ordered re|wrong\n1;', 'RECOMPILE', 'select --+ ordered RECOMPILE\n1;'),
      ('select //+ re|wrong\n1;', 'RECOMPILE', 'select //+ RECOMPILE\n1;'),
    )
    for marked, candidate, expected in cases:
      with self.subTest(draft=marked):
        text, cursor = marked.replace('|', ''), marked.index('|')
        menu = CompletionMenu()
        menu.open(text, cursor, suggest(text, cursor))
        menu.selected = next(i for i, c in enumerate(menu.suggestions.candidates) if c.text == candidate)
        accepted, position = menu.accept()
        self.assertEqual(expected, accepted)
        self.assertEqual(menu.suggestions.start + len(candidate), position)
        self.assertFalse(menu.active)

  def test_ordinary_comments_strings_and_hint_arguments_stay_quiet(self):
    for marked in ('select /* re', 'select -- re', 'select // re',
                   'select /* + re', 'select -- + re', 'select // + re',
                   "select '/*+ re|';",
                   'select /*|+ re */', 'select /*+ re *|/',
                   'select /*+ USE_NL(re', 'select /*+ USE_NL(t, re|) */ 1;',
                   'select /*+ LEADING(t, |u) */ 1;',
                   'select /*+ USE_NL("re|wrong") */ 1;',
                   'select /*+ USE_NL([re|wrong]) */ 1;',
                   "select /*+ 're|wrong' */ 1;",
                   ';schema /*+ re'):
      with self.subTest(draft=marked):
        result = self.suggestions(marked)
        self.assertFalse(result.allowed)
        self.assertEqual((), result.candidates)
    self.assertEqual([], self.names('select /*+ unknown_hint'))
    self.assertEqual([], self.names('select "/*+ re|"'))

  def test_sql_completion_resumes_after_the_hint_comment(self):
    schema = Schema('DBA', (Relation('DBA', 'code', 'CLASS', ('id', 'name')),))
    for marked in ('select /*+ RECOMPILE */ na| from code',
                   'select --+ RECOMPILE\nna| from code',
                   'select //+ RECOMPILE\nna| from code',
                   'select /*+ USE_NL(code) */ c.na| from code c'):
      with self.subTest(draft=marked):
        self.assertEqual(['name'], self.names(marked, schema))
    self.assertEqual(['code'], self.names('select /*+ ORDERED */ * from co', schema))
    self.assertEqual(['SELECT', 'SET', 'SHOW', 'STATISTICS'], self.names('select /*+ RECOMPILE */s'))
    self.assertEqual(['RECOMPILE', 'REEXECUTE'], self.names('select 1; select /*+ re| */ 1;'))
    self.assertEqual(['RECOMPILE', 'REEXECUTE'], self.names('select (select /*+ re| */ 1) from code'))


if __name__ == '__main__':
  unittest.main()

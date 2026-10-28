"""SQL context and replacement contracts independent of terminal rendering."""

import unittest

from csql_with_history.completion import CompletionMenu, Relation, Schema, suggest


SCHEMA = Schema('DBA', (
  Relation('DBA', 'code', 'CLASS', ('id', 'name')),
  Relation('DBA', 'coding', 'VCLASS', ('id', 'language')),
  Relation('DBA', 'coding odd', 'CLASS', ('odd name',)),
  Relation('OTHER', 'code', 'CLASS', ('other_id',)),
))


class CompletionTest(unittest.TestCase):

  def candidates(self, draft: str) -> list[str]:
    cursor = draft.index('|') if '|' in draft else len(draft)
    return [c.text for c in suggest(draft.replace('|', ''), cursor, SCHEMA).candidates]

  def test_relations_follow_sql_table_positions(self) -> None:
    for draft in ('select * from co', 'select * from code join co', 'update co',
                  'insert into co', 'select * from code, co', 'select *\nfrom co'):
      with self.subTest(draft=draft):
        self.assertEqual(['[coding odd]', 'code', 'coding', 'OTHER.code'], self.candidates(draft))

  def test_quoted_and_owner_qualified_names(self) -> None:
    self.assertEqual(['code'], self.candidates('select * from other.co'))
    self.assertCountEqual(['[code]', '[coding]', '[coding odd]', 'OTHER.[code]'], self.candidates('select * from [co'))
    self.assertCountEqual(['"code"', '"coding"', '"coding odd"', 'OTHER."code"'], self.candidates('select * from "co'))

  def test_reserved_identifiers_and_shadowed_public_names_are_qualified_safely(self) -> None:
    schema = Schema('DBA', (*SCHEMA.relations,
                           Relation('DBA', 'int', 'CLASS'),
                           Relation('PUBLIC', 'code', 'CLASS')))
    result = suggest('select * from in', len('select * from in'), schema)
    self.assertEqual(['[int]'], [c.text for c in result.candidates])
    result = suggest('select * from co', len('select * from co'), schema)
    self.assertIn('PUBLIC.code', [c.text for c in result.candidates])

  def test_replacement_removes_the_entire_identifier_and_preserves_suffix(self) -> None:
    draft = 'select * from cowrong where id=1;'
    cursor = draft.index('wrong')
    suggestions = suggest(draft, cursor, SCHEMA)
    menu = CompletionMenu()
    menu.open(draft, cursor, suggestions)
    menu.selected = next(i for i, c in enumerate(suggestions.candidates) if c.text == 'code')
    text, position = menu.accept()
    self.assertEqual('select * from code where id=1;', text)
    self.assertEqual(len('select * from code'), position)

  def test_columns_resolve_aliases_and_tables_after_the_cursor(self) -> None:
    self.assertEqual(['name'], self.candidates('select c.na| from code as c'))
    self.assertEqual(['name'], self.candidates('select na| from code'))
    self.assertEqual(['[language]'], self.candidates('select * from coding c where c.la'))
    self.assertEqual(['c.id', 'd.id'], self.candidates('select id| from code c join coding d on c.id=d.id'))
    self.assertEqual(['other_id'], self.candidates('select x.ot| from other.code x'))
    self.assertEqual(['name'], self.candidates('select lower(c.na|) from code c'))
    self.assertEqual(['name'], self.candidates('select * from code c where (c.na|)'))
    self.assertEqual(['name'], self.candidates('insert into code (na'))

  def test_comments_strings_and_session_commands_suppress_completion(self) -> None:
    for draft in ("select 'co", "select 'co|ding' from code", '-- co',
                  'select /* co', 'select -- co\n|', ';schema co'):
      with self.subTest(draft=draft):
        text = draft.replace('|', '')
        cursor = draft.index('|') if '|' in draft else len(text)
        result = suggest(text, cursor, SCHEMA)
        if draft == 'select -- co\n|':
          self.assertTrue(result.allowed)
        else:
          self.assertFalse(result.allowed)

  def test_nested_scopes_and_statements_do_not_leak_aliases(self) -> None:
    self.assertEqual(['[language]'], self.candidates('select (select c.la| from coding c) from code c'))
    self.assertEqual(['[language]'], self.candidates('select * from code c; select c.la| from coding c'))
    self.assertEqual(['code'], self.candidates('select * from /* ignored */ other.co'))


if __name__ == '__main__':
  unittest.main()

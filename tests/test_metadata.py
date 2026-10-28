"""Catalog format and connection routing contracts."""

import unittest

from csql_with_history.cli import completion_connection
from csql_with_history.metadata import HEADER, parse_catalog


class MetadataTest(unittest.TestCase):

  def test_parser_decodes_plain_output_and_keeps_owner_identity(self) -> None:
    lines = [
      '\t'.join(HEADER),
      'relation\tDBA\tDBA\tcode\tcode\tCLASS',
      'relation\tDBA\tOTHER\tcode\tcode\tVCLASS',
      'column\tDBA\tOTHER\tcode\tother_id\tINSTANCE',
      'column\tDBA\tDBA\tcode\tname\\twith\\nline\\\\slash\tINSTANCE',
    ]
    schema = parse_catalog(('\n'.join(lines) + '\n').encode())
    self.assertEqual('DBA', schema.user)
    self.assertEqual(('name\twith\nline\\slash',), schema.relations[0].columns)
    self.assertEqual(('other_id',), schema.relations[1].columns)

  def test_invalid_output_is_rejected_instead_of_becoming_candidates(self) -> None:
    for output in (b'ERROR: failure', b'', '\t'.join(HEADER).encode() + b'\nshort\trow',
                   '\t'.join(HEADER).encode() + b'\nrelation\tDBA\tDBA\tbad\\x\tx\tCLASS'):
      with self.subTest(output=output), self.assertRaises(ValueError):
        parse_catalog(output)
    self.assertEqual((), parse_catalog(('\t'.join(HEADER) + '\n').encode()).relations)

  def test_connection_copy_preserves_mode_user_password_and_remote_target(self) -> None:
    cases = (
      (['-S', '-udba', '-p', 'test-only-password', 'db@host'], True),
      (['--SA-mode', '--us=dba', '--pass=test-only-password', 'db@host'], True),
      (['-Su', 'dba', '-C', '--password=test-only-password', '--no-pager', 'db@host'], False),
    )
    for arguments, standalone in cases:
      with self.subTest(arguments=arguments):
        connection = completion_connection(arguments)
        self.assertIsNotNone(connection)
        self.assertEqual(standalone, connection.standalone)
        self.assertEqual(('-S' if standalone else '-C', '--user=dba', '--password=test-only-password', 'db@host'), connection.arguments)

  def test_utility_actions_and_uncertain_targets_disable_metadata(self) -> None:
    for arguments in (['--sysadm-rebuild-catalog', 'db'], ['--sysadm', 'db'],
                      ['--unknown', 'db'], ['db1', 'db2'], ['--', '-database'], ['-u']):
      with self.subTest(arguments=arguments):
        self.assertIsNone(completion_connection(arguments))


if __name__ == '__main__':
  unittest.main()

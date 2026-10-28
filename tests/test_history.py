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
"""History timestamp compatibility and relative-age checks."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from csql_with_history.cli import SubmissionHistory, format_history_age


class HistoryTimestampTest(unittest.TestCase):

  def setUp(self) -> None:
    temporary = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.path = Path(temporary.name) / "history.sqlite3"

  def open_history(self, save_disabled: bool = False) -> SubmissionHistory:
    history = SubmissionHistory(self.path, 100, save_disabled)
    self.addCleanup(history.close)
    return history

  def make_legacy_history(self) -> None:
    with closing(sqlite3.connect(self.path)) as connection:
      connection.execute("CREATE TABLE submissions (id INTEGER PRIMARY KEY, command TEXT NOT NULL)")
      connection.execute("INSERT INTO submissions(command) VALUES ('select legacy;')")
      connection.commit()

  def test_legacy_rows_keep_unknown_times_and_new_submissions_get_timestamps(self) -> None:
    self.make_legacy_history()
    history = self.open_history()
    self.assertIsNone(history.records()[0].submitted_at)
    with patch("csql_with_history.cli.time.time", return_value=1234567890):
      history.save("select new;")
    self.assertEqual(["select new;", "select legacy;"], history.entries())
    history.close()
    restarted = self.open_history()
    self.assertEqual([1234567890, None], [entry.submitted_at for entry in restarted.records()])

  def test_read_only_legacy_history_is_not_migrated(self) -> None:
    self.make_legacy_history()
    original = self.path.read_bytes()
    history = self.open_history(save_disabled=True)
    self.assertEqual(["select legacy;"], history.entries())
    self.assertIsNone(history.records()[0].submitted_at)
    history.save("select excluded;")
    history.close()
    self.assertEqual(original, self.path.read_bytes())

  def test_concurrent_legacy_openers_both_migrate_and_read_the_store(self) -> None:
    self.make_legacy_history()

    def read_history(_: int) -> list[str]:
      history = SubmissionHistory(self.path, 100, False)
      try:
        self.assertIsNotNone(history.connection)
        return history.entries()
      finally:
        history.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
      self.assertEqual([["select legacy;"]] * 2, list(executor.map(read_history, range(2))))

  def test_shared_history_deduplicates_using_the_latest_submission_time(self) -> None:
    first = self.open_history()
    second = self.open_history()
    with patch("csql_with_history.cli.time.time", return_value=1000):
      first.save("select\n'one';")
    with patch("csql_with_history.cli.time.time", return_value=2000):
      second.save("select two;")
      second.save("select\n'one';")
    entries = first.records()
    self.assertEqual(["select\n'one';", "select two;"], [entry.command for entry in entries])
    self.assertEqual([2000, 2000], [entry.submitted_at for entry in entries])

  def test_unavailable_store_keeps_memory_only_submission_times(self) -> None:
    self.path.mkdir()
    history = self.open_history()
    with patch("csql_with_history.cli.time.time", return_value=1000):
      history.save("select volatile;")
    self.assertEqual(1000, history.records()[0].submitted_at)

  def test_relative_ages_handle_boundaries_unknown_times_and_clock_skew(self) -> None:
    for elapsed, expected in (
      (0, "just now"), (3, "just now"), (5, "5 sec ago"),
      (59, "59 sec ago"), (60, "1 min ago"), (180, "3 min ago"),
      (3600, "1 hr ago"), (86400, "1 day ago"),
      (172800, "2 days ago"), (31536000, "1 year ago"), (-100, "just now"),
    ):
      with self.subTest(elapsed=elapsed):
        self.assertEqual(expected, format_history_age(1000000000 - elapsed, now=1000000000))
    self.assertEqual("time unknown", format_history_age(None, now=1000000000))

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
"""History deduplication, retention, timestamp compatibility, and relative ages."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from csql_future.cli import HistoryMode, SubmissionHistory, format_history_age


class SubmissionHistoryTest(unittest.TestCase):

  def setUp(self) -> None:
    temporary = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.path = Path(temporary.name) / "history.sqlite3"

  def open_history(self, save_disabled: bool = False, limit: int = 100) -> SubmissionHistory:
    history = SubmissionHistory(self.path, limit, save_disabled)
    self.addCleanup(history.close)
    return history

  def stored_entries(self) -> list[tuple[str, float | None]]:
    with closing(sqlite3.connect(self.path)) as connection:
      return connection.execute(
        "SELECT command, submitted_at FROM submissions ORDER BY id"
      ).fetchall()

  def make_legacy_history(self) -> None:
    with closing(sqlite3.connect(self.path)) as connection:
      connection.execute("CREATE TABLE submissions (id INTEGER PRIMARY KEY, command TEXT NOT NULL)")
      connection.execute("INSERT INTO submissions(command) VALUES ('select legacy;')")
      connection.commit()

  def test_legacy_rows_keep_unknown_times_and_new_submissions_get_timestamps(self) -> None:
    self.make_legacy_history()
    history = self.open_history()
    self.assertIsNone(history.records()[0].submitted_at)
    with patch("csql_future.cli.time.time", return_value=1234567890):
      history.save("select new;")
    self.assertEqual(["select new;", "select legacy;"], history.entries())
    history.close()
    restarted = self.open_history()
    self.assertEqual([1234567890, None], [entry.submitted_at for entry in restarted.records()])

  def test_read_only_legacy_history_is_not_migrated(self) -> None:
    self.make_legacy_history()
    with closing(sqlite3.connect(self.path)) as connection:
      connection.execute("INSERT INTO submissions(command) VALUES ('select legacy;')")
      connection.commit()
    original = self.path.read_bytes()
    history = self.open_history(save_disabled=True)
    self.assertEqual(["select legacy;"], history.entries())
    self.assertIsNone(history.records()[0].submitted_at)
    history.save("select excluded;")
    history.close()
    self.assertEqual(original, self.path.read_bytes())

  def test_writable_open_keeps_the_latest_duplicate_row_and_timestamp(self) -> None:
    with closing(sqlite3.connect(self.path)) as connection:
      connection.execute(
        "CREATE TABLE submissions (id INTEGER PRIMARY KEY, command TEXT NOT NULL, submitted_at REAL)"
      )
      connection.executemany(
        "INSERT INTO submissions(command, submitted_at) VALUES (?, ?)",
        [("select repeat;", 3000), ("select distinct;", 2000), ("select repeat;", 1000)],
      )
      connection.commit()
    history = self.open_history()
    self.assertEqual(["select repeat;", "select distinct;"], history.entries())
    expected = [("select distinct;", 2000), ("select repeat;", 1000)]
    self.assertEqual(expected, self.stored_entries())
    history.close()
    restarted = self.open_history()
    self.assertEqual(["select repeat;", "select distinct;"], restarted.entries())
    self.assertEqual(expected, self.stored_entries())

  def test_legacy_duplicates_are_cleaned_during_timestamp_migration(self) -> None:
    self.make_legacy_history()
    with closing(sqlite3.connect(self.path)) as connection:
      connection.executemany(
        "INSERT INTO submissions(command) VALUES (?)",
        [("select distinct;",), ("select legacy;",)],
      )
      connection.commit()
    history = self.open_history()
    self.assertEqual(["select legacy;", "select distinct;"], history.entries())
    self.assertEqual([("select distinct;", None), ("select legacy;", None)], self.stored_entries())

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
    with patch("csql_future.cli.time.time", return_value=1000):
      first.save("select\n'one';")
    with patch("csql_future.cli.time.time", return_value=2000):
      second.save("select two;")
      second.save("select\n'one';")
    entries = first.records()
    self.assertEqual(["select\n'one';", "select two;"], [entry.command for entry in entries])
    self.assertEqual([2000, 2000], [entry.submitted_at for entry in entries])
    self.assertEqual([("select two;", 2000), ("select\n'one';", 2000)], self.stored_entries())

  def test_repeated_saves_update_latest_use_without_evicting_distinct_commands(self) -> None:
    history = self.open_history(limit=3)
    for submitted_at, command in enumerate(("first", "repeat", "middle", "repeat")):
      with patch("csql_future.cli.time.time", return_value=submitted_at):
        history.save(command)
    self.assertEqual([("first", 0), ("middle", 2), ("repeat", 3)], self.stored_entries())
    self.assertEqual(["repeat", "middle", "first"], history.entries())
    history.save("newest")
    self.assertEqual(["newest", "repeat", "middle"], history.entries())
    self.assertEqual(["middle", "repeat", "newest"], [row[0] for row in self.stored_entries()])

  def test_deduplication_preserves_case_whitespace_and_multiline_differences(self) -> None:
    history = self.open_history()
    commands = ["select 'A  B';", "SELECT 'A  B';", "select 'A B';", "select\n'A  B';", "select 'A  B'; "]
    for command in commands + [commands[0]]:
      history.save(command)
    self.assertEqual(commands[1:] + commands[:1], [row[0] for row in self.stored_entries()])

  def test_concurrent_writers_keep_one_row_for_each_exact_command(self) -> None:
    initializer = self.open_history()
    initializer.close()

    def save_repeatedly(_: int) -> None:
      history = SubmissionHistory(self.path, 3, False)
      try:
        for _ in range(10):
          history.save("repeat")
        self.assertIs(history.mode, HistoryMode.PERSISTENT)
      finally:
        history.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
      list(executor.map(save_repeatedly, range(2)))
    self.assertEqual(["repeat"], [row[0] for row in self.stored_entries()])

  def test_failed_insert_rolls_back_duplicate_removal(self) -> None:
    history = self.open_history()
    with patch("csql_future.cli.time.time", return_value=1000):
      history.save("repeat")
    with closing(sqlite3.connect(self.path)) as connection:
      connection.execute(
        "CREATE TRIGGER reject_insert BEFORE INSERT ON submissions "
        "BEGIN SELECT RAISE(ABORT, 'insert failed'); END"
      )
      connection.commit()
    with patch("csql_future.cli.time.time", return_value=2000):
      history.save("repeat")
    self.assertIs(history.mode, HistoryMode.MEMORY_ONLY)
    self.assertEqual([("repeat", 1000)], self.stored_entries())
    self.assertEqual(2000, history.records()[0].submitted_at)

  def test_memory_only_retention_counts_unique_commands(self) -> None:
    self.path.mkdir()
    history = self.open_history(limit=3)
    for command in ("first", "repeat", "middle", "repeat"):
      history.save(command)
    self.assertEqual(["repeat", "middle", "first"], history.entries())
    history.save("newest")
    self.assertEqual(["newest", "repeat", "middle"], history.entries())

  def test_zero_and_negative_limits_keep_their_existing_meaning(self) -> None:
    for limit in (0, -1):
      with self.subTest(limit=limit):
        history = self.open_history(limit=limit)
        for command in ("first", "repeat", "repeat"):
          history.save(command)
        expected = [] if limit == 0 else ["repeat", "first"]
        self.assertEqual(expected, history.entries())
        self.assertEqual(list(reversed(expected)), [row[0] for row in self.stored_entries()])
        history.close()

  def test_unavailable_store_keeps_memory_only_submission_times(self) -> None:
    self.path.mkdir()
    history = self.open_history()
    with patch("csql_future.cli.time.time", return_value=1000):
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

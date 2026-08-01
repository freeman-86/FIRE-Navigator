import tempfile
import unittest
from pathlib import Path

from adapters.local.history_repository import MAX_HISTORY_ENTRIES, append_history_entry, load_history


class HistoryRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp_dir.name) / "history.json"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_load_history_returns_empty_list_when_file_does_not_exist(self) -> None:
        self.assertEqual(load_history(self.path), [])

    def test_append_then_load_round_trips(self) -> None:
        append_history_entry({"timestamp": "2026-01-01T00:00:00", "current_networth": 1_000_000}, self.path)

        entries = load_history(self.path)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["current_networth"], 1_000_000)

    def test_append_adds_to_end_without_removing_earlier_entries(self) -> None:
        append_history_entry({"timestamp": "1"}, self.path)
        append_history_entry({"timestamp": "2"}, self.path)
        append_history_entry({"timestamp": "3"}, self.path)

        entries = load_history(self.path)

        self.assertEqual([e["timestamp"] for e in entries], ["1", "2", "3"])

    def test_old_entries_are_trimmed_beyond_max_history_entries(self) -> None:
        for i in range(MAX_HISTORY_ENTRIES + 5):
            append_history_entry({"timestamp": str(i)}, self.path)

        entries = load_history(self.path)

        self.assertEqual(len(entries), MAX_HISTORY_ENTRIES)
        # 古い方(0〜4)が削除され、末尾側が残る
        self.assertEqual(entries[0]["timestamp"], "5")
        self.assertEqual(entries[-1]["timestamp"], str(MAX_HISTORY_ENTRIES + 4))


if __name__ == "__main__":
    unittest.main()

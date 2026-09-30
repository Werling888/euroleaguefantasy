"""Official free trades map onto the Best team Changes radio."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.official import change_radio_options, suggested_changes_label


class SuggestedChangesTest(unittest.TestCase):
    def test_clamps_to_four(self) -> None:
        self.assertEqual(suggested_changes_label(2), "2")
        self.assertEqual(suggested_changes_label(4), "4")
        self.assertEqual(suggested_changes_label(6), "4")

    def test_zero_or_missing_means_no_suggestion(self) -> None:
        self.assertIsNone(suggested_changes_label(0))
        self.assertIsNone(suggested_changes_label(-1))
        self.assertIsNone(suggested_changes_label(None))
        self.assertIsNone(suggested_changes_label(""))

    def test_radio_hides_counts_above_free_trades(self) -> None:
        self.assertEqual(change_radio_options(2), ["1", "2", "All"])
        self.assertEqual(change_radio_options(1), ["1", "All"])
        self.assertEqual(change_radio_options(4), ["1", "2", "3", "4", "All"])
        self.assertEqual(change_radio_options(0), ["All"])
        self.assertEqual(change_radio_options(None), ["1", "2", "3", "4", "All"])


if __name__ == "__main__":
    unittest.main()

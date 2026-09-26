"""Fantasy Challenge G/F/C come from the price list, not EuroLeague Center/Forward."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prices import apply_fantasy_positions, apply_fantasy_positions_to_logs


class FantasyPositionTest(unittest.TestCase):
    def test_list_forward_overrides_euroleague_center(self) -> None:
        players = pd.DataFrame(
            [
                {
                    "person_id": "001",
                    "person_name": "Conor Morgan",
                    "team_name": "Besiktas",
                    "position_group": "C",
                }
            ]
        )
        prices = pd.DataFrame(
            [
                {
                    "source_name": "Conor Morgan",
                    "source_team": "Besiktas Istanbul",
                    "position_group": "F",
                    "price": 8.6,
                }
            ]
        )
        result = apply_fantasy_positions(players, prices)
        self.assertEqual(result.iloc[0]["position_group"], "F")

    def test_box_scores_use_the_same_slot(self) -> None:
        players = pd.DataFrame(
            [{"person_id": "001", "person_name": "Conor Morgan", "team_name": "Besiktas", "position_group": "F"}]
        )
        logs = pd.DataFrame(
            [{"player_id": "001", "position_group": "C", "fantasy": 10.0}]
        )
        tagged = apply_fantasy_positions_to_logs(logs, players)
        self.assertEqual(tagged.iloc[0]["position_group"], "F")


if __name__ == "__main__":
    unittest.main()

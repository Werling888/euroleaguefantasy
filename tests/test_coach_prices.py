"""Official coach quotations map onto local coaches; player rows stay G/F/C only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.prices import assign_prices, map_coach_prices, player_price_rows


class CoachPriceMapTest(unittest.TestCase):
    def test_maps_head_coach_quotation(self) -> None:
        coaches = pd.DataFrame(
            [
                {"coach_id": "KOW", "coach_name": "Xavi Pascual", "team_name": "Dubai"},
                {"coach_id": "ATT", "coach_name": "Georgios Bartzokas", "team_name": "Olympiacos"},
            ]
        )
        prices = pd.DataFrame(
            [
                {
                    "source_name": "Carlik Jones",
                    "source_team": "Partizan",
                    "position_group": "G",
                    "price": 14.5,
                },
                {
                    "source_name": "Xavi Pascual",
                    "source_team": "Dubai Basketball",
                    "position_group": "Coach",
                    "price": 8.1,
                },
                {
                    "source_name": "Georgios Bartzokas",
                    "source_team": "Olympiacos Piraeus",
                    "position_group": "Coach",
                    "price": 10.3,
                },
            ]
        )
        mapped = map_coach_prices(coaches, prices)
        self.assertEqual(mapped["KOW"], 8.1)
        self.assertEqual(mapped["ATT"], 10.3)

    def test_player_price_assign_ignores_coach_rows(self) -> None:
        players = pd.DataFrame(
            [{"player_id": "1", "player_name": "Carlik Jones", "team_name": "Partizan"}]
        )
        prices = pd.DataFrame(
            [
                {
                    "source_name": "Carlik Jones",
                    "source_team": "Partizan Belgrade",
                    "position_group": "G",
                    "price": 14.5,
                },
                {
                    "source_name": "Xavi Pascual",
                    "source_team": "Dubai",
                    "position_group": "Coach",
                    "price": 8.1,
                },
            ]
        )
        market = player_price_rows(prices)
        self.assertEqual(len(market), 1)
        self.assertEqual(market.iloc[0]["position_group"], "G")
        priced = assign_prices(players, prices)
        self.assertEqual(float(priced.iloc[0]["price"]), 14.5)


if __name__ == "__main__":
    unittest.main()

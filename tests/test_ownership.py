"""Ownership share from the official list maps onto projections and differentials."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ownership import differentials
from src.prices import assign_coach_ownership, assign_prices


class OwnershipMapTest(unittest.TestCase):
    def test_assign_prices_copies_popularity(self) -> None:
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
                    "popularity": 0.333,
                },
                {
                    "source_name": "Xavi Pascual",
                    "source_team": "Dubai",
                    "position_group": "Coach",
                    "price": 8.1,
                    "popularity": 0.05,
                },
            ]
        )
        priced = assign_prices(players, prices)
        self.assertEqual(float(priced.iloc[0]["price"]), 14.5)
        self.assertAlmostEqual(float(priced.iloc[0]["ownership"]), 0.333)

    def test_assign_prices_without_popularity_column(self) -> None:
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
                }
            ]
        )
        priced = assign_prices(players, prices)
        self.assertTrue(pd.isna(priced.iloc[0]["ownership"]))

    def test_assign_coach_ownership(self) -> None:
        coaches = pd.DataFrame(
            [{"coach_id": "KOW", "coach_name": "Xavi Pascual", "team_name": "Dubai"}]
        )
        prices = pd.DataFrame(
            [
                {
                    "source_name": "Xavi Pascual",
                    "source_team": "Dubai Basketball",
                    "position_group": "Coach",
                    "price": 8.1,
                    "popularity": 0.081,
                }
            ]
        )
        mapped = assign_coach_ownership(coaches, prices)
        self.assertAlmostEqual(float(mapped.iloc[0]["ownership"]), 0.081)

    def test_differentials_and_template_risk(self) -> None:
        board = pd.DataFrame(
            [
                {
                    "player_id": "a",
                    "player_name": "Star",
                    "projected": 30.0,
                    "ownership": 0.40,
                    "availability": "available",
                },
                {
                    "player_id": "b",
                    "player_name": "Diff",
                    "projected": 22.0,
                    "ownership": 0.05,
                    "availability": "available",
                },
                {
                    "player_id": "c",
                    "player_name": "Mine",
                    "projected": 18.0,
                    "ownership": 0.03,
                    "availability": "available",
                },
                {
                    "player_id": "d",
                    "player_name": "OutStar",
                    "projected": 28.0,
                    "ownership": 0.35,
                    "availability": "out",
                },
            ]
        )
        diffs, risk = differentials(board, held_ids=["c"])
        self.assertEqual(list(diffs["player_id"]), ["b"])
        self.assertEqual(list(risk["player_id"]), ["a"])


if __name__ == "__main__":
    unittest.main()

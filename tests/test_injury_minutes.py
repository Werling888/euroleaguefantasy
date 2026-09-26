"""Vacated minutes go to remaining Available teammates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.injuries import MINUTE_CAP, apply_injury_minutes


def _club() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_name": "Out guard",
                "team_code": "ABC",
                "position_group": "G",
                "availability": "out",
                "expected_minutes": 28.0,
                "projected": 20.0,
                "floor": 10.0,
                "ceiling": 30.0,
            },
            {
                "player_name": "Best guard",
                "team_code": "ABC",
                "position_group": "G",
                "availability": "available",
                "expected_minutes": 24.0,
                "projected": 18.0,
                "floor": 9.0,
                "ceiling": 27.0,
            },
            {
                "player_name": "Second guard",
                "team_code": "ABC",
                "position_group": "G",
                "availability": "available",
                "expected_minutes": 18.0,
                "projected": 12.0,
                "floor": 6.0,
                "ceiling": 18.0,
            },
            {
                "player_name": "Third guard",
                "team_code": "ABC",
                "position_group": "G",
                "availability": "available",
                "expected_minutes": 8.0,
                "projected": 5.0,
                "floor": 2.0,
                "ceiling": 8.0,
            },
            {
                "player_name": "Forward",
                "team_code": "ABC",
                "position_group": "F",
                "availability": "available",
                "expected_minutes": 20.0,
                "projected": 14.0,
                "floor": 7.0,
                "ceiling": 21.0,
            },
        ]
    )


class InjuryMinutesTest(unittest.TestCase):
    def test_same_position_gets_most_and_projected_scales(self) -> None:
        result = apply_injury_minutes(_club()).set_index("player_name")
        best = result.loc["Best guard"]
        second = result.loc["Second guard"]
        third = result.loc["Third guard"]
        forward = result.loc["Forward"]
        out = result.loc["Out guard"]

        self.assertGreater(best.injury_boost_min, second.injury_boost_min)
        self.assertGreater(second.injury_boost_min, third.injury_boost_min)
        self.assertGreater(forward.injury_boost_min, 0.0)
        self.assertEqual(out.injury_boost_min, 0.0)
        self.assertLessEqual(result["expected_minutes"].max(), MINUTE_CAP)

        same_boost = (
            best.injury_boost_min + second.injury_boost_min + third.injury_boost_min
        )
        self.assertAlmostEqual(same_boost, 28.0 * 0.60, places=6)
        self.assertAlmostEqual(forward.injury_boost_min, 28.0 * 0.40, places=6)

        self.assertAlmostEqual(
            best.projected, 18.0 * (best.expected_minutes / 24.0), places=6
        )
        self.assertAlmostEqual(best.expected_minutes, 24.0 + best.injury_boost_min)

    def test_skips_when_he_already_missed_games(self) -> None:
        club = _club()
        club["gp_current"] = [1, 2, 2, 2, 2]
        result = apply_injury_minutes(club).set_index("player_name")
        self.assertEqual(result["injury_boost_min"].sum(), 0.0)
    def test_reverts_when_he_returns(self) -> None:
        club = _club()
        club.loc[club["player_name"] == "Out guard", "availability"] = "available"
        club["gp_current"] = [1, 2, 2, 2, 2]
        result = apply_injury_minutes(club).set_index("player_name")
        returned = result.loc["Out guard"]
        best = result.loc["Best guard"]
        forward = result.loc["Forward"]
        self.assertEqual(returned.injury_boost_min, 0.0)
        self.assertEqual(returned.expected_minutes, 28.0)
        self.assertLess(best.injury_boost_min, 0.0)
        self.assertLess(forward.injury_boost_min, 0.0)
        self.assertLess(best.injury_boost_min, result.loc["Second guard"].injury_boost_min)
        self.assertAlmostEqual(
            best.injury_boost_min
            + result.loc["Second guard"].injury_boost_min
            + result.loc["Third guard"].injury_boost_min,
            -14.0 * 0.60,
            places=6,
        )
        self.assertAlmostEqual(forward.injury_boost_min, -14.0 * 0.40, places=6)
        self.assertAlmostEqual(best.expected_minutes, 24.0 + best.injury_boost_min)
        self.assertGreater(best.expected_minutes, 0.0)


if __name__ == "__main__":
    unittest.main()

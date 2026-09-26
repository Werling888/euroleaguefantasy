"""Opponent factor uses the G/F/C game pie, not one starter cloned onto everyone."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.project import CURRENT_SEASON, PRIOR_SEASON, _defense_profiles, _opponent_factor, _shrink_factor


def _row(season, opponent, game, position, fantasy, minutes, day, team="AAA"):
    return {
        "season_code": season,
        "opponent_code": opponent,
        "game_code": game,
        "position_group": position,
        "fantasy": fantasy,
        "minutes": minutes,
        "date": pd.Timestamp(day, tz="UTC"),
        "team_code": team,
        "played": True,
        "phase": "RS",
    }


class GamePieTest(unittest.TestCase):
    def test_two_centers_in_one_game_are_one_pie(self) -> None:
        logs = pd.DataFrame(
            [
                _row(CURRENT_SEASON, "PRS", 1, "C", 30.8, 22.0, "2026-09-25", "PAN"),
                _row(CURRENT_SEASON, "PRS", 1, "C", 5.0, 8.0, "2026-09-25", "PAN"),
                _row(CURRENT_SEASON, "MIL", 2, "C", 20.0, 20.0, "2026-09-25", "PAR"),
            ]
        )
        profiles, league, games, _prior_league, _prior_allowed = _defense_profiles(logs)
        paris = profiles[(profiles.opponent_code == "PRS") & (profiles.position_group == "C")].iloc[0]
        self.assertAlmostEqual(paris.allowed_all, 35.8, places=5)
        self.assertEqual(int(paris.games), 1)
        self.assertEqual(games["PRS"], 1)
        self.assertAlmostEqual(league["C"], (35.8 + 20.0) / 2.0, places=5)

    def test_does_not_give_every_center_the_star_line(self) -> None:
        rows = [_row(CURRENT_SEASON, "PRS", 1, "C", 30.8, 22.0, "2026-09-25")]
        for index in range(8):
            rows.append(_row(CURRENT_SEASON, f"T{index}", 10 + index, "C", 20.0, 20.0, "2026-09-26"))
        rows.append(_row(PRIOR_SEASON, "PRS", 99, "C", 22.0, 20.0, "2026-01-01"))
        for index in range(8):
            rows.append(_row(PRIOR_SEASON, f"P{index}", 80 + index, "C", 21.0, 20.0, "2026-01-02"))
        profiles, league, _games, prior_league, prior_allowed = _defense_profiles(pd.DataFrame(rows))
        factor = _opponent_factor("PRS", "C", league, profiles, prior_league, prior_allowed)
        self.assertLess(factor, 1.40)
        projected = 13.2 * factor * (1.0 + 0.10 * 0.71)
        self.assertLess(projected, 22.0)
        self.assertGreater(projected, 10.0)

    def test_all_grows_with_each_game(self) -> None:
        logs = pd.DataFrame(
            [
                _row(CURRENT_SEASON, "PRS", 1, "C", 20.0, 20.0, "2026-09-25"),
                _row(CURRENT_SEASON, "PRS", 2, "C", 10.0, 20.0, "2026-10-02"),
                _row(CURRENT_SEASON, "PRS", 3, "C", 12.0, 20.0, "2026-10-09"),
                _row(CURRENT_SEASON, "MIL", 9, "C", 12.0, 20.0, "2026-09-25"),
            ]
        )
        profiles, league, _games, _pl, _pa = _defense_profiles(logs)
        paris = profiles[(profiles.opponent_code == "PRS") & (profiles.position_group == "C")].iloc[0]
        self.assertEqual(int(paris.games), 3)
        self.assertAlmostEqual(paris.allowed_all, 14.0, places=5)
        self.assertAlmostEqual(paris.l3, 14.0, places=5)

    def test_last_three_ignore_older_games(self) -> None:
        rows = [
            _row(CURRENT_SEASON, "PRS", n, "C", 10.0 if n >= 3 else 25.0, 20.0, f"2026-10-{n:02d}")
            for n in range(1, 6)
        ]
        rows.append(_row(CURRENT_SEASON, "MIL", 99, "C", 12.0, 20.0, "2026-09-25"))
        profiles, _league, _games, _pl, _pa = _defense_profiles(pd.DataFrame(rows))
        paris = profiles[(profiles.opponent_code == "PRS") & (profiles.position_group == "C")].iloc[0]
        self.assertEqual(int(paris.games), 5)
        self.assertAlmostEqual(paris.l3, 10.0, places=5)
        self.assertAlmostEqual(paris.allowed_all, (25.0 + 25.0 + 10.0 + 10.0 + 10.0) / 5.0, places=5)

    def test_forwards_stay_out_of_the_center_pie(self) -> None:
        logs = pd.DataFrame(
            [
                _row(CURRENT_SEASON, "PRS", 1, "C", 30.8, 22.0, "2026-09-25"),
                _row(CURRENT_SEASON, "PRS", 1, "F", 15.4, 18.0, "2026-09-25"),
                _row(CURRENT_SEASON, "MIL", 2, "C", 20.0, 20.0, "2026-09-25"),
                _row(CURRENT_SEASON, "MIL", 2, "F", 12.0, 20.0, "2026-09-25"),
            ]
        )
        profiles, _league, _g, _pl, _pa = _defense_profiles(logs)
        c_pie = profiles[(profiles.opponent_code == "PRS") & (profiles.position_group == "C")].iloc[0]
        f_pie = profiles[(profiles.opponent_code == "PRS") & (profiles.position_group == "F")].iloc[0]
        self.assertAlmostEqual(c_pie.allowed_all, 30.8, places=5)
        self.assertAlmostEqual(f_pie.allowed_all, 15.4, places=5)

    def test_shrink_blends_toward_prior(self) -> None:
        mixed = _shrink_factor(1.80, 1.0, 1)
        self.assertLess(mixed, 1.80)
        self.assertGreater(mixed, 1.0)
        many = _shrink_factor(1.80, 1.0, 20)
        self.assertGreater(many, mixed)

    def test_healthy_frontcourt_does_not_add_center_minutes(self) -> None:
        from src.injuries import apply_injury_minutes

        club = pd.DataFrame(
            [
                {"player_name": "Hayes", "team_code": "PAR", "position_group": "C", "availability": "available", "expected_minutes": 16.6, "projected": 13.2, "gp_current": 1},
                {"player_name": "Jekiri", "team_code": "PAR", "position_group": "C", "availability": "available", "expected_minutes": 20.3, "projected": 15.4, "gp_current": 1},
                {"player_name": "Tanaskovic", "team_code": "PAR", "position_group": "C", "availability": "available", "expected_minutes": 23.0, "projected": 9.9, "gp_current": 1},
            ]
        )
        result = apply_injury_minutes(club).set_index("player_name")
        self.assertEqual(result["injury_boost_min"].sum(), 0.0)
        self.assertAlmostEqual(result.loc["Hayes", "projected"], 13.2, places=5)


if __name__ == "__main__":
    unittest.main()

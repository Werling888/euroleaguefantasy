"""Past matches lists opponent scorers, newest games first."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.past_matches import fpts_cost_band, opponent_high_scores, position_averages, position_highs, select_venue, window_limit
from src.project import _season_factor


def _line(**overrides) -> dict:
    row = {
        "season_code": "E2026",
        "phase": "RS",
        "played": True,
        "minutes": 20.0,
        "is_home": True,
        "team_score": 80,
        "opp_score": 70,
        "position_group": "G",
        "player_id": "1",
        "player_name": "Home Guard",
        "team_code": "OLY",
        "team_name": "Olympiacos",
        "opponent_code": "PRS",
        "opponent_name": "Paris",
        "game_code": 1,
        "round": 1,
        "date": "2026-10-01T18:00:00Z",
        "fantasy": 10.0,
    }
    row.update(overrides)
    return row


def _game(code: int, day: str, opponent: str, opp_name: str, **overrides) -> list[dict]:
    """Both sides of one game. Olympiacos is home. Opponent fantasy is the high line."""
    home = _line(
        game_code=code,
        round=code,
        date=f"{day}T18:00:00Z",
        opponent_code=opponent,
        opponent_name=opp_name,
        player_name="Olympiacos Guard",
        fantasy=4.0,
    )
    away_guard = _line(
        game_code=code,
        round=code,
        date=f"{day}T18:00:00Z",
        team_code=opponent,
        team_name=opp_name,
        opponent_code="OLY",
        opponent_name="Olympiacos",
        is_home=False,
        team_score=70,
        opp_score=80,
        player_id=f"{code}-g",
        player_name=f"{opp_name} Guard",
        position_group="G",
        fantasy=12.0 + code,
        minutes=28.0,
    )
    away_forward = _line(
        game_code=code,
        round=code,
        date=f"{day}T18:00:00Z",
        team_code=opponent,
        team_name=opp_name,
        opponent_code="OLY",
        opponent_name="Olympiacos",
        is_home=False,
        team_score=70,
        opp_score=80,
        player_id=f"{code}-f",
        player_name=f"{opp_name} Forward",
        position_group="F",
        fantasy=8.0,
        minutes=22.0,
    )
    rows = [home, away_guard, away_forward]
    for row in rows:
        row.update(overrides)
    return rows


class PastMatchesTest(unittest.TestCase):
    def setUp(self) -> None:
        rows = []
        rows.extend(_game(1, "2026-10-01", "PRS", "Paris"))
        rows.extend(_game(2, "2026-10-08", "PAN", "Panathinaikos"))
        rows.extend(_game(3, "2026-10-15", "MAD", "Real Madrid"))
        rows.extend(_game(4, "2026-10-22", "BAR", "Barcelona"))
        self.logs = pd.DataFrame(rows)

    def test_window_labels(self) -> None:
        self.assertIsNone(window_limit("All"))
        self.assertEqual(window_limit("5"), 5)
        self.assertEqual(window_limit("1"), 1)

    def test_last_one_is_the_newest_game_only(self) -> None:
        games, lines = opponent_high_scores(self.logs, "OLY", "E2026", 1)
        self.assertEqual(list(games["game_code"]), [4])
        self.assertEqual(set(lines["team_name"]), {"Barcelona"})
        self.assertNotIn("Olympiacos Guard", set(lines["player_name"]))

    def test_last_three_drops_the_oldest(self) -> None:
        games, lines = opponent_high_scores(self.logs, "OLY", "E2026", 3)
        self.assertEqual(list(games["game_code"]), [4, 3, 2])
        self.assertNotIn(1, set(lines["game_code"]))

    def test_all_keeps_every_game_and_ranks_fantasy(self) -> None:
        games, lines = opponent_high_scores(self.logs, "OLY", "E2026", None)
        self.assertEqual(list(games["game_code"]), [4, 3, 2, 1])
        guards = lines[lines["position_group"] == "G"]
        self.assertEqual(list(guards["fantasy"]), sorted(guards["fantasy"], reverse=True))
        self.assertGreater(float(guards.iloc[0]["fantasy"]), float(guards.iloc[-1]["fantasy"]))

    def test_did_not_play_prior_season_and_playoffs_are_left_out(self) -> None:
        extra = pd.DataFrame(
            [
                _line(
                    game_code=4,
                    round=4,
                    date="2026-10-22T18:00:00Z",
                    team_code="BAR",
                    team_name="Barcelona",
                    opponent_code="OLY",
                    opponent_name="Olympiacos",
                    player_id="bench",
                    player_name="Did Not Play",
                    played=False,
                    minutes=0,
                    fantasy=0,
                ),
                _line(
                    season_code="E2025",
                    game_code=90,
                    date="2025-10-22T18:00:00Z",
                    team_code="BAR",
                    team_name="Barcelona",
                    opponent_code="OLY",
                    opponent_name="Olympiacos",
                    player_name="Last Year",
                    fantasy=40,
                ),
                _line(
                    phase="PO",
                    game_code=91,
                    date="2026-05-01T18:00:00Z",
                    team_code="BAR",
                    team_name="Barcelona",
                    opponent_code="OLY",
                    opponent_name="Olympiacos",
                    player_name="Playoff",
                    fantasy=40,
                ),
            ]
        )
        logs = pd.concat([self.logs, extra], ignore_index=True)
        games, lines = opponent_high_scores(logs, "OLY", "E2026", None)
        names = set(lines["player_name"])
        self.assertNotIn("Did Not Play", names)
        self.assertNotIn("Last Year", names)
        self.assertNotIn("Playoff", names)
        self.assertNotIn(90, set(games["game_code"]))

    def test_high_line_wins_a_tie_on_minutes(self) -> None:
        rows = _game(1, "2026-10-01", "PRS", "Paris")
        rows.append(
            _line(
                game_code=1,
                round=1,
                date="2026-10-01T18:00:00Z",
                team_code="PRS",
                team_name="Paris",
                opponent_code="OLY",
                opponent_name="Olympiacos",
                is_home=False,
                player_id="g2",
                player_name="Short Guard",
                position_group="G",
                fantasy=13.0,
                minutes=10.0,
            )
        )
        # _game's away guard is also 13.0 (12+1) at 28 minutes.
        _games, lines = opponent_high_scores(pd.DataFrame(rows), "OLY", "E2026", 1)
        highs = position_highs(lines)
        guard = highs[highs["position_group"] == "G"].iloc[0]
        self.assertEqual(guard["player_name"], "Paris Guard")

    def test_fewer_games_than_the_window_returns_all(self) -> None:
        games, _lines = opponent_high_scores(self.logs, "OLY", "E2026", 5)
        self.assertEqual(len(games), 4)

    def test_average_divides_the_position_pie_by_games_shown(self) -> None:
        games, lines = opponent_high_scores(self.logs, "OLY", "E2026", 2)
        averages = position_averages(lines, games)
        # Newest two games: guards score 16 and 15, forwards 8 and 8. No centers.
        self.assertEqual(len(games), 2)
        self.assertAlmostEqual(averages["G"], (16.0 + 15.0) / 2.0)
        self.assertAlmostEqual(averages["F"], (8.0 + 8.0) / 2.0)
        self.assertAlmostEqual(averages["C"], 0.0)

    def test_venue_limit_keeps_the_newest_games_at_that_venue(self) -> None:
        games = pd.DataFrame(
            [
                {"game_code": 4, "is_home": False},
                {"game_code": 3, "is_home": True},
                {"game_code": 2, "is_home": True},
                {"game_code": 1, "is_home": False},
            ]
        )
        lines = pd.DataFrame(
            [
                {"game_code": 4, "fantasy": 10.0},
                {"game_code": 3, "fantasy": 20.0},
                {"game_code": 2, "fantasy": 30.0},
                {"game_code": 1, "fantasy": 40.0},
            ]
        )
        home, home_lines = select_venue(games, lines, "Home", 1)
        self.assertEqual(list(home["game_code"]), [3])
        self.assertEqual(list(home_lines["game_code"]), [3])
        away, away_lines = select_venue(games, lines, "Away", None)
        self.assertEqual(list(away["game_code"]), [4, 1])
        self.assertEqual(list(away_lines["fantasy"]), [10.0, 40.0])
        both, _both_lines = select_venue(games, lines, "Both", 2)
        self.assertEqual(list(both["game_code"]), [4, 3])

    def test_factor_is_the_pie_over_the_league(self) -> None:
        self.assertAlmostEqual(_season_factor(40.0, 20.0), 2.0)
        self.assertIsNone(_season_factor(40.0, None))

    def test_fpts_color_follows_price(self) -> None:
        self.assertEqual(fpts_cost_band(9.9, 10), "red")
        self.assertEqual(fpts_cost_band(10, 10), "yellow")
        self.assertEqual(fpts_cost_band(11, 10), "yellow")
        self.assertEqual(fpts_cost_band(11.1, 10), "green")
        self.assertEqual(fpts_cost_band(11, 11.9), "yellow")
        self.assertEqual(fpts_cost_band(10.9, 11.9), "red")
        self.assertEqual(fpts_cost_band(8, 8.4), "yellow")
        self.assertIsNone(fpts_cost_band(12, None))

    def test_unknown_club_is_empty(self) -> None:
        games, lines = opponent_high_scores(self.logs, "ZZZ", "E2026", None)
        self.assertTrue(games.empty)
        self.assertTrue(lines.empty)


if __name__ == "__main__":
    unittest.main()

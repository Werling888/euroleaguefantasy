"""Single-player trade-up suggestions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.optimize import _pid
from src.trades import MIN_COUNTED_GAIN, MIN_PROJECTED_GAIN, suggest_trade_upgrades


def _player(
    player_id: str,
    position: str,
    price: float,
    projected: float,
    team_code: str = "AAA",
    name: str | None = None,
    game_day=None,
) -> dict:
    return {
        "player_id": _pid(player_id),
        "player_name": name or player_id,
        "team_code": team_code,
        "team_name": team_code,
        "position_group": position,
        "opponent_name": "OPP",
        "home_away": "Home",
        "price": float(price),
        "projected": float(projected),
        "expected_minutes": 20.0,
        "game_day": game_day,
        "points_per_credit": projected / price if price else None,
        "ownership": None,
        "availability": "available",
        "status_label": "Available",
        "injury_note": "",
        "form_source": "",
    }


class TradeSuggestionsTest(unittest.TestCase):
    def test_finds_cheaper_higher_projection_same_position(self) -> None:
        outgoing = _player("1", "G", 10.0, 15.0, team_code="T1", name="Out")
        upgrade = _player("2", "G", 9.0, 18.0, team_code="T2", name="In")
        cheap = _player("3", "G", 8.0, 12.0, team_code="T3", name="Worse")
        records = [outgoing, upgrade, cheap]
        result = suggest_trade_upgrades("1", ["1"], records)
        self.assertIsNone(result["message"] or None)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["player_id"], upgrade["player_id"])

    def test_rejects_higher_price(self) -> None:
        outgoing = _player("1", "G", 10.0, 15.0)
        pricey = _player("2", "G", 11.0, 20.0)
        result = suggest_trade_upgrades("1", ["1"], [outgoing, pricey])
        self.assertEqual(result["candidates"], [])

    def test_rejects_seventh_player_from_same_club(self) -> None:
        outgoing = _player("1", "G", 10.0, 15.0, team_code="Y", name="Out")
        others = [_player(str(n), "G", 8.0, 10.0, team_code="X") for n in range(2, 8)]
        others.extend(_player(str(n), "F", 8.0, 10.0, team_code="Z") for n in range(8, 11))
        saved = [outgoing] + others
        saved_ids = [p["player_id"] for p in saved]
        seventh = _player("99", "G", 9.0, 18.0, team_code="X", name="In")
        records = saved + [seventh]
        result = suggest_trade_upgrades("1", saved_ids, records)
        self.assertEqual(result["candidates"], [])

    def test_outgoing_must_be_on_saved_team(self) -> None:
        outgoing = _player("1", "G", 10.0, 15.0)
        upgrade = _player("2", "G", 9.0, 18.0)
        result = suggest_trade_upgrades("1", ["2"], [outgoing, upgrade])
        self.assertIn("saved team", result["message"].lower())

    def test_filters_small_projected_gain(self) -> None:
        outgoing = _player("1", "G", 10.0, 15.0)
        tiny = _player("2", "G", 10.0, 15.5)
        result = suggest_trade_upgrades("1", ["1"], [outgoing, tiny])
        self.assertEqual(result["candidates"], [])
        self.assertIn(str(MIN_PROJECTED_GAIN), result["message"])

    def test_sorts_by_counted_gain_for_captain(self) -> None:
        outgoing = _player("1", "G", 10.0, 10.0, name="Cap")
        medium = _player("2", "G", 10.0, 11.0, name="Med")
        big = _player("3", "G", 10.0, 12.0, name="Big")
        saved_players = [{"player_id": "1", "slot": "starter", "captain": True}]
        result = suggest_trade_upgrades(
            "1",
            ["1"],
            [outgoing, medium, big],
            saved_players=saved_players,
        )
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["candidates"][0]["player_id"], big["player_id"])
        self.assertAlmostEqual(result["candidates"][0]["delta_counted"], 4.0)
        self.assertAlmostEqual(result["candidates"][1]["delta_counted"], 2.0)


if __name__ == "__main__":
    unittest.main()

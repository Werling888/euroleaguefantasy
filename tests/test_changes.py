"""3 changes means keep 7 from the saved squad."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.optimize import MAX_TURN1, _pid, _search_changes, _turns_ok


def _player(ident: str, pos: str, projected: float, price: float, team: str = "AAA") -> dict:
    return {
        "player_id": _pid(ident),
        "player_name": ident,
        "team_code": team,
        "team_name": team,
        "position_group": pos,
        "opponent_name": "Opp",
        "home_away": "Home",
        "price": price,
        "projected": projected,
        "expected_minutes": 24.0,
        "game_day": None,
        "points_per_credit": projected / price,
        "availability": "available",
        "status_label": "Available",
        "injury_note": "",
        "form_source": "E2026",
        "turn": "T1",
    }


class ChangeLimitTest(unittest.TestCase):
    def test_three_changes_keeps_seven(self) -> None:
        held = []
        pool = []
        ident = 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                held.append(_player(f"{ident:06d}", pos, 20.0 + ident, 8.0, team=f"T{ident}"))
                ident += 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                pool.append(_player(f"{ident:06d}", pos, 30.0 + ident, 8.0, team="BBB"))
                ident += 1
        records = held + pool
        outcome = _search_changes(records, [p["player_id"] for p in held], 3, 100.0, 0.0)
        self.assertEqual(outcome[0], "squad")
        starters, sixth, bench = outcome[2], outcome[3], outcome[4]
        chosen = starters + [sixth] + bench
        held_ids = {p["player_id"] for p in held}
        kept = sum(1 for player in chosen if player["player_id"] in held_ids)
        self.assertEqual(kept, 7)
        self.assertEqual(len(chosen), 10)

    def test_one_change_keeps_nine(self) -> None:
        held = []
        pool = []
        ident = 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                held.append(_player(f"{ident:06d}", pos, 20.0 + ident, 8.0, team=f"T{ident}"))
                ident += 1
        for pos, count in (("G", 2), ("F", 2), ("C", 1)):
            for _ in range(count):
                pool.append(_player(f"{ident:06d}", pos, 40.0 + ident, 8.0, team="BBB"))
                ident += 1
        records = held + pool
        outcome = _search_changes(records, [p["player_id"] for p in held], 1, 100.0, 0.0)
        self.assertEqual(outcome[0], "squad")
        chosen = outcome[2] + [outcome[3]] + outcome[4]
        held_ids = {p["player_id"] for p in held}
        self.assertEqual(sum(1 for player in chosen if player["player_id"] in held_ids), 9)

    def test_one_change_when_one_saved_player_is_out(self) -> None:
        held = []
        ident = 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                held.append(_player(f"{ident:06d}", pos, 20.0 + ident, 8.0, team=f"T{ident}"))
                ident += 1
        out = held[0]
        replacement = _player("000099", out["position_group"], 50.0, 8.0, team="BBB")
        records = held[1:] + [replacement]
        outcome = _search_changes(records, [p["player_id"] for p in held], 1, 100.0, 0.0)
        self.assertEqual(outcome[0], "squad")
        chosen = outcome[2] + [outcome[3]] + outcome[4]
        self.assertEqual(sum(1 for player in chosen if player["player_id"] == replacement["player_id"]), 1)
        self.assertEqual(sum(1 for player in chosen if player["player_id"] in {p["player_id"] for p in held}), 9)

    def test_three_changes_not_all_t1(self) -> None:
        import pandas as pd

        t1 = pd.Timestamp("2026-09-30", tz="Europe/Athens").normalize()
        t2 = pd.Timestamp("2026-10-01", tz="Europe/Athens").normalize()
        held = []
        pool = []
        ident = 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                player = _player(f"{ident:06d}", pos, 20.0 + ident, 8.0, team=f"T{ident}")
                player["game_day"] = t1
                player["turn"] = "T1"
                held.append(player)
                ident += 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                player = _player(f"{ident:06d}", pos, 40.0 + ident, 8.0, team="BBB")
                player["game_day"] = t2
                player["turn"] = "T2"
                pool.append(player)
                ident += 1
        records = held + pool
        outcome = _search_changes(records, [p["player_id"] for p in held], 4, 100.0, 0.0)
        self.assertEqual(outcome[0], "squad")
        chosen = outcome[2] + [outcome[3]] + outcome[4]
        self.assertTrue(_turns_ok(chosen, [t1, t2]))
        self.assertLessEqual(sum(1 for player in chosen if player["turn"] == "T1"), MAX_TURN1)

    def test_spend_leftover_upgrades_same_position(self) -> None:
        from src.optimize import _spend_leftover

        players = []
        ident = 1
        for pos, count in (("G", 4), ("F", 4), ("C", 2)):
            for _ in range(count):
                players.append(_player(f"{ident:06d}", pos, 20.0, 8.0, team=f"T{ident}"))
                ident += 1
        expensive = _player("000099", "G", 20.5, 18.0, team="ZZZ")
        starters = [players[0], players[1], players[4], players[5], players[8]]
        sixth = players[2]
        bench = [players[3], players[6], players[7], players[9]]
        before = sum(p["price"] for p in starters + [sixth] + bench)
        self.assertEqual(before, 80.0)
        starters, sixth, bench = _spend_leftover(
            starters, sixth, bench, players + [expensive], 100.0, None
        )
        after = starters + [sixth] + bench
        self.assertIn(expensive["player_id"], {p["player_id"] for p in after})
        self.assertGreater(sum(p["price"] for p in after), before)


if __name__ == "__main__":
    unittest.main()

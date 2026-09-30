"""Map Fantasy Challenge court positions and roster rows into local squad entries."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.import_squad import build_squad_from_roster, court_slot


class CourtSlotTest(unittest.TestCase):
    def test_starters_sixth_bench(self) -> None:
        self.assertEqual(court_slot(1), "starter")
        self.assertEqual(court_slot(5), "starter")
        self.assertEqual(court_slot(6), "sixth")
        self.assertEqual(court_slot(7), "bench")
        self.assertEqual(court_slot(10), "bench")
        self.assertIsNone(court_slot(11))
        self.assertIsNone(court_slot(None))


class BuildSquadFromRosterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.projections = pd.DataFrame(
            [
                {"player_id": "1001", "player_name": "Carlik Jones", "team_name": "Partizan"},
                {"player_id": "1002", "player_name": "Moses Wright", "team_name": "Olimpia Milano"},
                {"player_id": "1003", "player_name": "Timothe Luwawu-Cabarrot", "team_name": "Real Madrid"},
                {"player_id": "1004", "player_name": "Azuolas Tubelis", "team_name": "Zalgiris"},
                {"player_id": "1005", "player_name": "Talen Horton-Tucker", "team_name": "Fenerbahce"},
                {"player_id": "1006", "player_name": "Theo Maledon", "team_name": "Real Madrid"},
                {"player_id": "1007", "player_name": "Eleftherios Mantzoukas", "team_name": "Panathinaikos"},
                {"player_id": "1008", "player_name": "Kostas Papanikolaou", "team_name": "Olympiacos"},
                {"player_id": "1009", "player_name": "Mario Saint-Supery", "team_name": "Baskonia"},
                {"player_id": "1010", "player_name": "Sertac Sanli", "team_name": "Fenerbahce"},
            ]
        )
        self.coaches = pd.DataFrame(
            [{"coach_id": "c1", "coach_name": "Xavi Pascual", "team_name": "Dubai"}]
        )

    def test_maps_slots_captain_and_coach(self) -> None:
        roster = {
            "players": [
                {
                    "id": 3843,
                    "first_name": "Moses",
                    "last_name": "Wright",
                    "court_position": 1,
                    "is_captain": False,
                    "position": {"name": "Center"},
                    "team": {"name": "Armani Olimpia Milan", "abbreviation": "MIL"},
                    "quotation": 13.7,
                },
                {
                    "id": 3864,
                    "first_name": "Timothé",
                    "last_name": "Luwawu-Cabarrot",
                    "court_position": 2,
                    "is_captain": False,
                    "position": {"name": "Forward"},
                    "team": {"name": "Real Madrid", "abbreviation": "RMB"},
                    "quotation": 12.4,
                },
                {
                    "id": 7221,
                    "first_name": "Azuolas",
                    "last_name": "Tubelis",
                    "court_position": 3,
                    "is_captain": False,
                    "position": {"name": "Forward"},
                    "team": {"name": "Zalgiris Kaunas", "abbreviation": "ZAL"},
                    "quotation": 11.6,
                },
                {
                    "id": 3791,
                    "first_name": "Carlik",
                    "last_name": "Jones",
                    "court_position": 4,
                    "is_captain": True,
                    "position": {"name": "Guard"},
                    "team": {"name": "Partizan Belgrade", "abbreviation": "PAR"},
                    "quotation": 14.5,
                },
                {
                    "id": 8567,
                    "first_name": "Talen",
                    "last_name": "Horton-Tucker",
                    "court_position": 5,
                    "is_captain": False,
                    "position": {"name": "Guard"},
                    "team": {"name": "Fenerbahce Beko", "abbreviation": "FBT"},
                    "quotation": 12.8,
                },
                {
                    "id": 3850,
                    "first_name": "Theo",
                    "last_name": "Maledon",
                    "court_position": 6,
                    "is_captain": False,
                    "position": {"name": "Guard"},
                    "team": {"name": "Real Madrid", "abbreviation": "RMB"},
                    "quotation": 10.0,
                },
                {
                    "id": 4061,
                    "first_name": "Eleftherios",
                    "last_name": "Mantzoukas",
                    "court_position": 7,
                    "is_captain": False,
                    "position": {"name": "Forward"},
                    "team": {"name": "Panathinaikos AKTOR", "abbreviation": "PAO"},
                    "quotation": 4.8,
                },
                {
                    "id": 3867,
                    "first_name": "Kostas",
                    "last_name": "Papanikolaou",
                    "court_position": 8,
                    "is_captain": False,
                    "position": {"name": "Forward"},
                    "team": {"name": "Olympiacos Piraeus", "abbreviation": "OLY"},
                    "quotation": 4.3,
                },
                {
                    "id": 11540,
                    "first_name": "Mario",
                    "last_name": "Saint-supery",
                    "court_position": 9,
                    "is_captain": False,
                    "position": {"name": "Guard"},
                    "team": {"name": "Baskonia Vitoria-Gasteiz", "abbreviation": "VBC"},
                    "quotation": 4.9,
                },
                {
                    "id": 3984,
                    "first_name": "Sertac",
                    "last_name": "Sanli",
                    "court_position": 10,
                    "is_captain": False,
                    "position": {"name": "Center"},
                    "team": {"name": "Fenerbahce Beko", "abbreviation": "FBT"},
                    "quotation": 4.5,
                },
                {
                    "id": 7235,
                    "first_name": "Xavi",
                    "last_name": "Pascual",
                    "court_position": 11,
                    "is_captain": False,
                    "position": {"name": "Head Coach"},
                    "team": {"name": "Dubai Basketball", "abbreviation": "DUB"},
                    "quotation": 8.1,
                },
            ]
        }
        result = build_squad_from_roster(roster, self.projections, self.coaches)
        self.assertEqual(result["matched_players"], 10)
        squad = result["squad"]
        self.assertEqual(squad["coach_id"], "c1")
        self.assertEqual(squad["coach_price"], 8.1)
        by_id = {entry["player_id"]: entry for entry in squad["players"]}
        self.assertEqual(by_id["1001"]["slot"], "starter")
        self.assertTrue(by_id["1001"]["captain"])
        self.assertEqual(by_id["1006"]["slot"], "sixth")
        self.assertEqual(by_id["1010"]["slot"], "bench")
        self.assertEqual(sum(1 for entry in squad["players"] if entry["captain"]), 1)

    def test_unmatched_player_is_warned(self) -> None:
        roster = {
            "players": [
                {
                    "id": 1,
                    "first_name": "Nobody",
                    "last_name": "Here",
                    "court_position": 1,
                    "is_captain": True,
                    "position": {"name": "Guard"},
                    "team": {"name": "Nowhere"},
                    "quotation": 5.0,
                }
            ]
        }
        result = build_squad_from_roster(roster, self.projections, self.coaches)
        self.assertEqual(result["matched_players"], 0)
        self.assertTrue(any("Could not match player Nobody Here" in message for message in result["warnings"]))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.roster_overrides import apply_roster_overrides


class RosterOverrideTests(unittest.TestCase):
    def test_skips_override_once_official_roster_has_him(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data" / "roster_overrides.json").write_text(
                json.dumps(
                    [
                        {
                            "person_id": "OV-HUNTER",
                            "person_name": "Shane Hunter",
                            "team_code": "TEL",
                            "team_name": "Maccabi",
                            "position_group": "C",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            players = pd.DataFrame(
                [{"person_id": "015398", "person_name": "Shane Hunter", "team_code": "TEL", "role": "player"}]
            )
            result = apply_roster_overrides(players, "E2026", root)
        self.assertEqual(result["person_id"].tolist(), ["015398"])


if __name__ == "__main__":
    unittest.main()

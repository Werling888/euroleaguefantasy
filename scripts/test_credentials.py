"""Guards for the private credentials file. Run: python scripts/test_credentials.py"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.credentials import fantasy_login, load_credentials
from src.official import GAME_ID, LEAGUE_ID, _jwt_payload, _position_group, _social_payload


def test_load_credentials_skips_comments_and_placeholders():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "data"
        folder.mkdir()
        (folder / "fantasy_credentials.properties").write_text(
            "# comment\nFANTASY_EMAIL=you@example.com\nFANTASY_PASSWORD=your-password\n",
            encoding="utf-8",
        )
        values = load_credentials(root)
        assert values["FANTASY_EMAIL"] == "you@example.com"
        assert fantasy_login(root) is None


def test_load_credentials_returns_real_login():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "data"
        folder.mkdir()
        (folder / "fantasy_credentials.properties").write_text(
            "FANTASY_EMAIL=user@club.com\nFANTASY_PASSWORD=secret-pass\n",
            encoding="utf-8",
        )
        assert fantasy_login(root) == ("user@club.com", "secret-pass")


def test_euroleague_game_ids_and_social_payload():
    assert GAME_ID == 7
    assert LEAGUE_ID == 10
    body = _social_payload("a@b.c", "99", "token", {"first_name": "Ada", "last_name": "Lovelace"})
    assert body["provider_name"] == "euroleague"
    assert body["game_id"] == 7
    assert body["first_name"] == "Ada"


def test_position_and_jwt_helpers():
    assert _position_group("Guard") == "G"
    assert _position_group({"abbreviation": "C"}) == "C"
    assert _position_group({"name": "Forward"}) == "F"
    token = (
        "aaa."
        + __import__("base64").urlsafe_b64encode(b'{"sub":"abc","email":"a@b.c"}').decode().rstrip("=")
        + ".sig"
    )
    assert _jwt_payload(token)["sub"] == "abc"


if __name__ == "__main__":
    test_load_credentials_skips_comments_and_placeholders()
    test_load_credentials_returns_real_login()
    test_euroleague_game_ids_and_social_payload()
    test_position_and_jwt_helpers()
    print("OK credentials and official helpers")

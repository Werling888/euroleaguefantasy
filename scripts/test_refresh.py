"""Offline guards for the refresh_cache optimizations (B1 season-skip, B2 _flush).

No network, no framework — run directly:  python scripts/test_refresh.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.cache as cache_mod
from src.cache import _flush, cache_dir, refresh_cache


def test_flush_returns_combined_without_reread():
    """B2: _flush returns the combined frames it wrote (no disk round-trip)."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        existing = pd.DataFrame(
            [{"season_code": "E2025", "game_code": 1, "player_id": "p1",
              "team_code": "AAA", "date": "2025-01-01", "pir": 5}]
        )
        # production `existing` comes from parquet already as datetime64
        existing["date"] = pd.to_datetime(existing["date"], utc=True)
        new_players = [{"season_code": "E2026", "game_code": 2, "player_id": "p2",
                        "team_code": "BBB", "date": "2026-01-01", "pir": 9}]
        combined_players, combined_coaches = _flush(folder, existing, None, new_players, [])
        assert len(combined_players) == 2, combined_players
        assert set(combined_players["player_id"]) == {"p1", "p2"}
        # what it returned must equal what it wrote to disk
        on_disk = pd.read_parquet(folder / "player_games.parquet")
        assert len(on_disk) == 2
        # empty coach side returns the (None) input unchanged, no file written
        assert combined_coaches is None
        assert not (folder / "coach_games.parquet").exists()
    print("OK B2: _flush returns combined frames, no re-read")


class _FakeClient:
    """Records which seasons get hit; returns nothing (so no parsing needed)."""

    def __init__(self, delay=0.0):
        self.fetched_seasons: set[str] = set()

    def fetch_clubs(self, season):
        self.fetched_seasons.add(season)
        return []

    def fetch_games(self, season):
        self.fetched_seasons.add(season)
        return []

    def fetch_people(self, season, team_code):  # pragma: no cover - no clubs -> not called
        self.fetched_seasons.add(season)
        return []

    def fetch_standings(self, season, played_round):  # pragma: no cover
        self.fetched_seasons.add(season)
        return []

    def fetch_box_score(self, season, game_code):  # pragma: no cover - nothing pending
        self.fetched_seasons.add(season)
        return None


def test_completed_season_is_reused_not_refetched(monkeypatch_targets):
    """B1: a cached completed season is carried forward, never re-downloaded."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = cache_dir(root)
        # Seed a warm cache: E2025 completed (its box scores already cached).
        games = pd.DataFrame(
            [{"season_code": "E2025", "game_code": 10, "status": "result",
              "date": "2025-02-01", "round": 1, "phase": "RS",
              "home_code": "AAA", "away_code": "BBB",
              "home_name": "Aaa", "away_name": "Bbb"}]
        )
        games.to_parquet(folder / "games.parquet", index=False)
        pd.DataFrame([{"season_code": "E2025", "team_code": "AAA", "role": "player",
                       "person_id": "p1", "person_name": "One", "team_name": "Aaa",
                       "position_group": "G"}]).to_parquet(folder / "rosters.parquet", index=False)
        pd.DataFrame([{"season_code": "E2025", "team_code": "AAA", "round": 1,
                       "net_per_game": 1.0, "games_played": 1}]).to_parquet(
            folder / "standings.parquet", index=False)
        # E2025 box score already cached -> nothing pending -> no box-score fetch.
        pd.DataFrame([{"season_code": "E2025", "game_code": 10, "player_id": "p1",
                       "team_code": "AAA", "date": "2025-02-01"}]).to_parquet(
            folder / "player_games.parquet", index=False)
        pd.DataFrame([{"season_code": "E2025", "game_code": 10, "team_code": "AAA",
                       "date": "2025-02-01"}]).to_parquet(
            folder / "coach_games.parquet", index=False)

        fake = _FakeClient()
        monkeypatch_targets(fake)

        refresh_cache(root)

        assert "E2025" not in fake.fetched_seasons, fake.fetched_seasons
        assert "E2026" in fake.fetched_seasons, "current season must still be refetched"
        # E2025 rows survived the rebuild
        out_games = pd.read_parquet(folder / "games.parquet")
        assert (out_games["season_code"] == "E2025").any(), out_games["season_code"].tolist()
        out_rosters = pd.read_parquet(folder / "rosters.parquet")
        assert (out_rosters["season_code"] == "E2025").any()
    print("OK B1: completed season reused, not refetched; rows carried forward")


def main():
    test_flush_returns_combined_without_reread()

    # Patch client + neutralize the end-of-refresh price/injury refresh (network).
    import src.prices as prices_mod
    import src.injuries as injuries_mod
    prices_mod.ensure_prices = lambda root, force=False: pd.DataFrame()
    injuries_mod.ensure_injuries = lambda root, force=False: pd.DataFrame()

    def patch(fake):
        cache_mod.EuroleagueClient = lambda delay=0.0: fake

    test_completed_season_is_reused_not_refetched(patch)
    print("\nAll refresh guards passed.")


if __name__ == "__main__":
    main()

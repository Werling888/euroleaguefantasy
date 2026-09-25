"""Local parquet cache for schedules, rosters, standings, and box scores."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.client import (
    EuroleagueClient,
    parse_box_score,
    parse_game,
    parse_people,
    parse_standings_row,
)

# The newer code is the fantasy season when it has a schedule.
# The older one supplies box scores before that season starts.
SEASONS = ("E2026", "E2025")


def cache_dir(root: Path) -> Path:
    path = root / "data" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(path)


def _write(frame: pd.DataFrame, path: Path) -> None:
    frame.to_parquet(path, index=False)


def _season_rows(frame: pd.DataFrame | None, season: str) -> pd.DataFrame | None:
    """Cached rows for one season, or None when absent."""
    if frame is None or frame.empty or "season_code" not in frame.columns:
        return None
    subset = frame[frame["season_code"] == season]
    return subset if not subset.empty else None


def load_cache(root: Path) -> dict[str, pd.DataFrame] | None:
    """Return cached tables, or None when the box-score cache is missing."""
    folder = cache_dir(root)
    player_games = _read(folder / "player_games.parquet")
    games = _read(folder / "games.parquet")
    if player_games is None or games is None or player_games.empty:
        return None
    return {
        "games": games,
        "player_games": player_games,
        "coach_games": _read(folder / "coach_games.parquet"),
        "rosters": _read(folder / "rosters.parquet"),
        "standings": _read(folder / "standings.parquet"),
    }


def _latest_played_round(games: list[dict], season_code: str) -> int | None:
    played = [
        game["round"]
        for game in games
        if game["season_code"] == season_code
        and game["phase"] == "RS"
        and game["status"] == "result"
        and game["round"]
    ]
    return max(played) if played else None


def refresh_cache(root: Path, progress=None, delay: float = 0.12) -> dict[str, pd.DataFrame]:
    """Download missing games and rebuild the parquet cache.

    Box scores already stored are skipped, so a second refresh only
    picks up new results. `progress(message, fraction)` is optional.
    """

    def report(message: str, fraction: float | None = None) -> None:
        if progress is not None:
            progress(message, fraction)
        else:
            print(message, flush=True)

    folder = cache_dir(root)
    client = EuroleagueClient(delay=delay)
    game_rows: list[dict] = []
    roster_rows: list[dict] = []
    standing_rows: list[dict] = []

    # SEASONS[0] is the live fantasy season and always re-downloaded. Later
    # entries are completed seasons whose schedule, rosters, standings, and box
    # scores never change again, so reuse the cached rows instead of re-fetching.
    current_season = SEASONS[0]
    existing_games = _read(folder / "games.parquet")
    existing_rosters = _read(folder / "rosters.parquet")
    existing_standings = _read(folder / "standings.parquet")

    for season in SEASONS:
        cached_games = _season_rows(existing_games, season)
        if season != current_season and cached_games is not None:
            report(f"Reusing cached {season} (completed season)")
            game_rows.extend(cached_games.to_dict(orient="records"))
            cached_rosters = _season_rows(existing_rosters, season)
            if cached_rosters is not None:
                roster_rows.extend(cached_rosters.to_dict(orient="records"))
            cached_standings = _season_rows(existing_standings, season)
            if cached_standings is not None:
                standing_rows.extend(cached_standings.to_dict(orient="records"))
            continue
        report(f"Fetching {season} clubs, schedule, and rosters")
        clubs = client.fetch_clubs(season)
        names = {
            club.get("code"): (club.get("abbreviatedName") or club.get("name"))
            for club in clubs
        }
        for raw in client.fetch_games(season):
            game_rows.append(parse_game(raw, season))
        for team_code, team_name in names.items():
            if not team_code:
                continue
            people = client.fetch_people(season, team_code)
            roster_rows.extend(parse_people(people, season, team_code, team_name or team_code))
        played_round = _latest_played_round(game_rows, season)
        if played_round:
            try:
                for raw in client.fetch_standings(season, played_round):
                    standing_rows.append(parse_standings_row(raw, season, played_round))
            except Exception as exc:  # noqa: BLE001 - one season must not abort the refresh
                report(f"Standings {season} round {played_round} skipped: {exc}")

    games = pd.DataFrame(game_rows).drop_duplicates(["season_code", "game_code"])
    games["date"] = pd.to_datetime(games["date"], utc=True, errors="coerce")
    _write(games, folder / "games.parquet")

    existing_players = _read(folder / "player_games.parquet")
    existing_coaches = _read(folder / "coach_games.parquet")
    done: set[tuple] = set()
    if existing_players is not None and not existing_players.empty:
        done = set(
            zip(
                existing_players["season_code"].astype(str),
                existing_players["game_code"].astype(int),
            )
        )

    results = games[games["status"] == "result"]
    pending = [
        row
        for row in results.to_dict(orient="records")
        if (str(row["season_code"]), int(row["game_code"])) not in done
    ]
    report(f"{len(pending)} box scores to fetch ({len(done)} already cached)")

    new_players: list[dict] = []
    new_coaches: list[dict] = []
    failures = 0
    for index, game in enumerate(pending, start=1):
        key = f"{game['season_code']} #{game['game_code']}"
        try:
            box = client.fetch_box_score(game["season_code"], int(game["game_code"]))
            if not box:
                failures += 1
                continue
            players, coaches = parse_box_score(box, game)
            new_players.extend(players)
            new_coaches.extend(coaches)
        except Exception as exc:  # noqa: BLE001 - keep going when one game fails
            failures += 1
            report(f"Skipped {key}: {exc}")
        if index % 20 == 0 or index == len(pending):
            report(
                f"Box scores {index}/{len(pending)}",
                index / max(len(pending), 1),
            )
            existing_players, existing_coaches = _flush(
                folder, existing_players, existing_coaches, new_players, new_coaches
            )
            new_players = []
            new_coaches = []

    if failures:
        report(f"{failures} box scores could not be read")

    rosters = pd.DataFrame(roster_rows)
    standings = pd.DataFrame(standing_rows)
    if not rosters.empty:
        _write(rosters, folder / "rosters.parquet")
    if not standings.empty:
        _write(standings, folder / "standings.parquet")

    meta = {
        "seasons": list(SEASONS),
        "games": int(len(games)),
        "results": int((games["status"] == "result").sum()),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    try:
        from src.prices import ensure_prices

        ensure_prices(root, force=True)
        report("Fantasy Challenge prices updated")
    except Exception as exc:  # noqa: BLE001 - stats refresh should survive a price-page outage
        report(f"Fantasy prices were not updated: {exc}")
    try:
        from src.injuries import ensure_injuries

        ensure_injuries(root, force=True)
        report("Injury report updated")
    except Exception as exc:  # noqa: BLE001 - stats refresh should survive an injury-page outage
        report(f"Injury report was not updated: {exc}")
    loaded = load_cache(root)
    if loaded is None:
        raise RuntimeError("Refresh finished without a usable box-score cache")
    return loaded


def _flush(folder, existing_players, existing_coaches, new_players, new_coaches):
    """Merge new rows into the parquet cache and return the combined frames.

    Returns the in-memory combined frames so the caller can keep accumulating
    without re-reading from disk what we just wrote.
    """
    combined_players = existing_players
    combined_coaches = existing_coaches
    if new_players:
        fresh = pd.DataFrame(new_players)
        fresh["date"] = pd.to_datetime(fresh["date"], utc=True, errors="coerce")
        combined_players = (
            fresh
            if existing_players is None
            else pd.concat([existing_players, fresh], ignore_index=True)
        )
        combined_players = combined_players.drop_duplicates(
            ["season_code", "game_code", "player_id", "team_code"]
        )
        _write(combined_players, folder / "player_games.parquet")
    if new_coaches:
        fresh = pd.DataFrame(new_coaches)
        fresh["date"] = pd.to_datetime(fresh["date"], utc=True, errors="coerce")
        combined_coaches = (
            fresh
            if existing_coaches is None
            else pd.concat([existing_coaches, fresh], ignore_index=True)
        )
        combined_coaches = combined_coaches.drop_duplicates(["season_code", "game_code", "team_code"])
        _write(combined_coaches, folder / "coach_games.parquet")
    return combined_players, combined_coaches

"""Polite client for the public Euroleague feeds used by euroleaguer."""

from __future__ import annotations

import time
from typing import Any

import requests

from src.fantasy import coach_points, display_name, is_overtime, player_fantasy, position_group

V2 = "https://feeds.incrowdsports.com/provider/euroleague-feeds/v2"
V3 = "https://feeds.incrowdsports.com/provider/euroleague-feeds/v3"

HEADERS = {
    "User-Agent": "euroleague-fantasy-dashboard/0.1",
    "Accept": "application/json",
}


class EuroleagueClient:
    """GET helper with a short pause between calls."""

    def __init__(self, delay: float = 0.12, timeout: float = 40.0):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_call = 0.0

    def _get(self, url: str, params: dict | None = None) -> Any:
        wait = self.delay - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        response = self.session.get(url, params=params, timeout=self.timeout)
        self._last_call = time.monotonic()
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    def fetch_clubs(self, season_code: str) -> list[dict]:
        payload = self._get(f"{V2}/competitions/E/seasons/{season_code}/clubs")
        return list((payload or {}).get("data") or [])

    def fetch_games(self, season_code: str) -> list[dict]:
        """All games in a season, walking offset pages of 50."""
        rows: list[dict] = []
        offset = 0
        total = None
        while total is None or offset < total:
            payload = self._get(
                f"{V2}/competitions/E/seasons/{season_code}/games",
                params={"offset": offset},
            )
            if not payload:
                break
            batch = payload.get("data") or []
            meta = payload.get("metadata") or {}
            rows.extend(batch)
            page_size = int(meta.get("pageSize") or len(batch) or 50)
            total = int(meta.get("totalItems") or len(rows))
            offset += max(page_size, 1)
            if not batch or offset > 5000:
                break
        return rows

    def fetch_people(self, season_code: str, team_code: str) -> list[dict]:
        payload = self._get(
            f"{V2}/competitions/E/seasons/{season_code}/clubs/{team_code}/people"
        )
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return data
        return []

    def fetch_standings(self, season_code: str, round_number: int) -> list[dict]:
        payload = self._get(
            f"{V3}/competitions/E/seasons/{season_code}/rounds/{round_number}/basicstandings"
        )
        if not isinstance(payload, dict):
            return []
        return list(payload.get("teams") or [])

    def fetch_box_score(self, season_code: str, game_code: int) -> dict | None:
        payload = self._get(
            f"{V3}/competitions/E/seasons/{season_code}/games/{int(game_code)}/stats"
        )
        if isinstance(payload, dict) and "local" in payload and "road" in payload:
            return payload
        return None


def _team_label(team: dict) -> str:
    return team.get("abbreviatedName") or team.get("editorialName") or team.get("name") or ""


def parse_game(raw: dict, season_code: str) -> dict:
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    phase = (raw.get("phaseType") or {}).get("code")
    round_info = raw.get("round") or {}
    return {
        "season_code": season_code,
        "game_code": int(raw["code"]),
        "phase": phase,
        "round": int(round_info.get("round") or 0),
        "date": raw.get("date"),
        "status": raw.get("status"),
        "home_code": home.get("code"),
        "home_name": _team_label(home),
        "home_score": home.get("score"),
        "away_code": away.get("code"),
        "away_name": _team_label(away),
        "away_score": away.get("score"),
        "overtime": is_overtime(home.get("quarters")),
    }


def parse_standings_row(raw: dict, season_code: str, round_number: int) -> dict:
    club = raw.get("club") or {}
    played = int(raw.get("gamesPlayed") or 0)
    points_for = float(raw.get("pointsFor") or 0)
    points_against = float(raw.get("pointsAgainst") or 0)
    net = (points_for - points_against) / played if played else None
    return {
        "season_code": season_code,
        "round": round_number,
        "team_code": club.get("code"),
        "team_name": _team_label(club),
        "games_played": played,
        "points_for": points_for,
        "points_against": points_against,
        "net_per_game": net,
    }


def parse_people(rows: list[dict], season_code: str, team_code: str, team_name: str) -> list[dict]:
    """Active players and the head coach. Later start dates win duplicates."""
    parsed: list[dict] = []
    for row in rows:
        person = row.get("person") or {}
        kind = row.get("type")
        if kind == "J":
            role = "player"
        elif kind == "E":
            role = "coach"
        else:
            continue
        if not row.get("active", True):
            continue
        parsed.append(
            {
                "season_code": season_code,
                "team_code": team_code,
                "team_name": team_name,
                "person_id": str(person.get("code") or "").strip(),
                "person_name": display_name(person.get("name")),
                "raw_name": person.get("name"),
                "role": role,
                "position_name": row.get("positionName"),
                "position_group": position_group(row.get("positionName")),
                "start_date": row.get("startDate") or "",
            }
        )
    parsed.sort(key=lambda item: item["start_date"])
    deduped: dict[tuple, dict] = {}
    for item in parsed:
        if not item["person_id"]:
            continue
        deduped[(item["role"], item["person_id"])] = item
    return list(deduped.values())


def parse_box_score(box: dict, game: dict) -> tuple[list[dict], list[dict]]:
    """Player logs and coach results for one game.

    `local` is the home team on this feed.
    """
    player_rows: list[dict] = []
    coach_rows: list[dict] = []
    sides = (
        ("local", True, "home_code", "home_name", "home_score", "away_code", "away_name", "away_score"),
        ("road", False, "away_code", "away_name", "away_score", "home_code", "home_name", "home_score"),
    )
    for side, is_home, team_key, team_name_key, score_key, opp_key, opp_name_key, opp_score_key in sides:
        block = box.get(side) or {}
        total = block.get("total") or {}
        team_score = game.get(score_key)
        opp_score = game.get(opp_score_key)
        if team_score is None:
            team_score = total.get("points")
        team_score = float(team_score or 0)
        opp_score = float(opp_score or 0)
        won = team_score > opp_score
        margin = team_score - opp_score
        overtime = bool(game.get("overtime"))
        coach = block.get("coach") or {}
        coach_rows.append(
            {
                "season_code": game["season_code"],
                "game_code": int(game["game_code"]),
                "phase": game.get("phase"),
                "round": game.get("round"),
                "date": game.get("date"),
                "team_code": game.get(team_key),
                "team_name": game.get(team_name_key),
                "opponent_code": game.get(opp_key),
                "opponent_name": game.get(opp_name_key),
                "is_home": is_home,
                "team_score": team_score,
                "opp_score": opp_score,
                "margin": margin,
                "overtime": overtime,
                "coach_id": str(coach.get("code") or "").strip(),
                "coach_name": display_name(coach.get("name")),
                "coach_points": coach_points(margin, overtime),
            }
        )
        for entry in block.get("players") or []:
            person = ((entry.get("player") or {}).get("person")) or {}
            stats = entry.get("stats") or {}
            player_meta = entry.get("player") or {}
            player_id = str(person.get("code") or "").strip()
            if not player_id:
                continue
            seconds = float(stats.get("timePlayed") or 0)
            played = seconds > 0
            pir = float(stats.get("valuation") or 0)
            position_name = player_meta.get("positionName")
            player_rows.append(
                {
                    "season_code": game["season_code"],
                    "game_code": int(game["game_code"]),
                    "phase": game.get("phase"),
                    "round": game.get("round"),
                    "date": game.get("date"),
                    "team_code": game.get(team_key),
                    "team_name": game.get(team_name_key),
                    "opponent_code": game.get(opp_key),
                    "opponent_name": game.get(opp_name_key),
                    "is_home": is_home,
                    "team_score": team_score,
                    "opp_score": opp_score,
                    "team_win": won,
                    "player_id": player_id,
                    "player_name": display_name(person.get("name")),
                    "position_name": position_name,
                    "position_group": position_group(position_name),
                    "minutes": seconds / 60.0,
                    "played": played,
                    "pir": pir,
                    "fantasy": player_fantasy(pir, won) if played else 0.0,
                    "starter": bool(stats.get("startFive")),
                }
            )
    return player_rows, coach_rows

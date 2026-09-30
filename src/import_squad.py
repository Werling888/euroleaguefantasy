"""Map an official Fantasy Challenge roster into the local squad.json shape."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.prices import _candidate_indexes, _chosen_list_row

# Fantaking court_position: 1-5 starters, 6 sixth man, 7-10 bench, 11 coach.
STARTER_COURTS = {1, 2, 3, 4, 5}
SIXTH_COURT = 6
BENCH_COURTS = {7, 8, 9, 10}
COACH_COURT = 11


def court_slot(court_position) -> str | None:
    """Map Fantaking court_position to starter / sixth / bench. Coach is not a player slot."""
    try:
        court = int(court_position)
    except (TypeError, ValueError):
        return None
    if court in STARTER_COURTS:
        return "starter"
    if court == SIXTH_COURT:
        return "sixth"
    if court in BENCH_COURTS:
        return "bench"
    return None


def _is_coach(row: dict) -> bool:
    if row.get("court_position") == COACH_COURT or row.get("court_position") == str(COACH_COURT):
        return True
    position = row.get("position")
    if isinstance(position, dict):
        name = str(position.get("name") or "").strip().lower()
        return "coach" in name
    return "coach" in str(position or "").strip().lower()


def _display_name(row: dict) -> str:
    first = str(row.get("first_name") or "").strip()
    last = str(row.get("last_name") or "").strip()
    return " ".join(part for part in (first, last) if part)


def _team_label(row: dict) -> str:
    team = row.get("team")
    if isinstance(team, dict):
        return str(team.get("name") or team.get("abbreviation") or "")
    return str(team or "")


def _lookup_frame(rows: pd.DataFrame, id_col: str, name_col: str, team_col: str) -> pd.DataFrame:
    frame = rows[[id_col, name_col, team_col]].copy()
    frame = frame.rename(columns={id_col: "local_id", name_col: "source_name", team_col: "source_team"})
    frame["price"] = 0.0
    frame["local_id"] = frame["local_id"].astype(str)
    return frame.reset_index(drop=True)


def _match_local_id(name: str, team_name: str, lookup: pd.DataFrame, index: dict[str, list[int]]) -> str | None:
    chosen = _chosen_list_row(name, team_name, lookup, index)
    if chosen is None:
        return None
    return str(chosen["local_id"])


def _quotation(row: dict) -> float | None:
    value = row.get("quotation")
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def build_squad_from_roster(
    roster: dict,
    projections: pd.DataFrame,
    coaches: pd.DataFrame,
) -> dict[str, Any]:
    """Turn roster/preview JSON into {players, coach_id, coach_price} plus match warnings."""
    rows = list(roster.get("players") or [])
    if not rows:
        return {
            "squad": {"players": [], "coach_id": None, "coach_price": None},
            "warnings": ["Fantasy Challenge roster was empty."],
            "matched_players": 0,
            "team_name": None,
        }

    player_lookup = pd.DataFrame()
    player_index: dict[str, list[int]] = {}
    if projections is not None and not projections.empty:
        player_lookup = _lookup_frame(projections, "player_id", "player_name", "team_name")
        player_index = _candidate_indexes(player_lookup)

    coach_lookup = pd.DataFrame()
    coach_index: dict[str, list[int]] = {}
    if coaches is not None and not coaches.empty:
        coach_lookup = _lookup_frame(coaches, "coach_id", "coach_name", "team_name")
        coach_index = _candidate_indexes(coach_lookup)

    players: list[dict] = []
    warnings: list[str] = []
    coach_id = None
    coach_price = None
    seen_ids: set[str] = set()

    ordered = sorted(
        rows,
        key=lambda row: (
            1 if _is_coach(row) else 0,
            int(row["court_position"]) if str(row.get("court_position") or "").isdigit() else 99,
        ),
    )
    for row in ordered:
        name = _display_name(row)
        team_name = _team_label(row)
        if not name:
            warnings.append("Skipped a roster row with no name.")
            continue
        if _is_coach(row):
            if coach_lookup.empty:
                warnings.append(f"Could not map coach {name}: no local coaches loaded.")
                continue
            matched = _match_local_id(name, team_name, coach_lookup, coach_index)
            if matched is None:
                warnings.append(f"Could not match coach {name} ({team_name}).")
                continue
            coach_id = matched
            coach_price = _quotation(row)
            continue

        slot = court_slot(row.get("court_position"))
        if slot is None:
            warnings.append(f"Skipped {name}: unknown court position {row.get('court_position')}.")
            continue
        if player_lookup.empty:
            warnings.append(f"Could not map {name}: player board is empty.")
            continue
        matched = _match_local_id(name, team_name, player_lookup, player_index)
        if matched is None:
            warnings.append(f"Could not match player {name} ({team_name}).")
            continue
        if matched in seen_ids:
            warnings.append(f"Skipped duplicate match for {name}.")
            continue
        seen_ids.add(matched)
        players.append(
            {
                "player_id": matched,
                "slot": slot,
                "captain": bool(row.get("is_captain")) and slot == "starter",
                "price": None,
            }
        )

    captains = sum(1 for entry in players if entry.get("captain"))
    if captains > 1:
        kept = False
        for entry in players:
            if entry.get("captain") and not kept:
                kept = True
                continue
            entry["captain"] = False
        warnings.append("More than one captain came from Fantasy Challenge; kept the first starter.")
    if captains == 0 and players:
        for entry in players:
            if entry["slot"] == "starter":
                entry["captain"] = True
                warnings.append("No captain in the Fantasy lineup; marked the first starter.")
                break

    return {
        "squad": {"players": players, "coach_id": coach_id, "coach_price": coach_price},
        "warnings": warnings,
        "matched_players": len(players),
        "team_name": None,
    }


def import_official_squad(
    root,
    projections: pd.DataFrame,
    coaches: pd.DataFrame,
    team_id: int | None = None,
) -> dict[str, Any]:
    """Fetch one official team and map it into the local squad shape."""
    from src.official import fetch_official_roster, fetch_user_fantasy_teams

    teams = fetch_user_fantasy_teams(root)
    if not teams:
        raise RuntimeError("No Classic Fantasy Challenge teams were found for this Fan ID.")
    chosen = None
    if team_id is not None:
        for team in teams:
            if int(team["id"]) == int(team_id):
                chosen = team
                break
        if chosen is None:
            raise RuntimeError(f"Fantasy team {team_id} was not in this account.")
    elif len(teams) == 1:
        chosen = teams[0]
    else:
        return {
            "teams": teams,
            "squad": None,
            "warnings": ["Pick which Fantasy Challenge team to import."],
            "matched_players": 0,
            "team_name": None,
            "needs_team_choice": True,
        }

    roster = fetch_official_roster(root, int(chosen["id"]), chosen.get("matchday_id"))
    mapped = build_squad_from_roster(roster, projections, coaches)
    mapped["teams"] = teams
    mapped["team_name"] = chosen["name"]
    mapped["team_id"] = int(chosen["id"])
    mapped["matchday_id"] = roster.get("matchday_id")
    mapped["needs_team_choice"] = False
    return mapped

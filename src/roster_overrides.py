"""Players missing from the Euroleague season roster but still on Fantasy Challenge."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REQUIRED = ("person_id", "person_name", "team_code", "team_name", "position_group")


def overrides_path(root: Path) -> Path:
    return root / "data" / "roster_overrides.json"


def load_overrides(root: Path) -> list[dict]:
    path = overrides_path(root)
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("roster_overrides.json must be a list of players")
    return rows


def apply_roster_overrides(
    players: pd.DataFrame, season_code: str, root: Path | None = None
) -> pd.DataFrame:
    """Append override players not already on the current-season board."""
    rows = load_overrides(root or Path(__file__).resolve().parent.parent)
    if not rows:
        return players
    existing = set()
    if not players.empty and "person_id" in players.columns:
        existing = set(players["person_id"].astype(str))
    extras = []
    for row in rows:
        missing = [key for key in REQUIRED if not row.get(key)]
        if missing:
            raise ValueError(f"roster override missing {missing}: {row}")
        person_id = str(row["person_id"])
        if person_id in existing:
            continue
        extras.append(
            {
                "season_code": season_code,
                "team_code": str(row["team_code"]),
                "team_name": str(row["team_name"]),
                "person_id": person_id,
                "person_name": str(row["person_name"]),
                "raw_name": str(row.get("raw_name") or row["person_name"]),
                "role": "player",
                "position_name": str(row.get("position_name") or row["position_group"]),
                "position_group": str(row["position_group"]),
                "start_date": row.get("start_date"),
            }
        )
    if not extras:
        return players
    return pd.concat([players, pd.DataFrame(extras)], ignore_index=True)

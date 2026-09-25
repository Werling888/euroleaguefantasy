"""Local squad file and official lineup multipliers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SLOT_MULTIPLIER = {"starter": 1.0, "sixth": 1.0, "bench": 0.5}
SLOT_ORDER = {"starter": 0, "sixth": 1, "bench": 2}
REQUIRED_POSITIONS = {"G": 4, "F": 4, "C": 2}
BUDGET = 100.0


def squad_path(root: Path) -> Path:
    return root / "data" / "squad.json"


def prices_path(root: Path) -> Path:
    return root / "data" / "prices.json"


def load_prices(root: Path) -> dict[str, float]:
    """Manual credit prices, keyed by player or coach id."""
    path = prices_path(root)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    prices = {}
    for key, value in raw.items():
        number = _number(value)
        if number is not None and number > 0:
            prices[str(key)] = number
    return prices


def save_prices(root: Path, prices: dict) -> None:
    path = prices_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {
        str(key): float(value)
        for key, value in prices.items()
        if _number(value) is not None and float(value) > 0
    }
    path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")


def points_per_credit(projected, price) -> float | None:
    """Projected fantasy points divided by the credit price."""
    number = _number(price)
    score = _number(projected)
    if number is None or number <= 0 or score is None:
        return None
    return score / number


def empty_squad() -> dict:
    return {"players": [], "coach_id": None, "coach_price": None}


def empty_book() -> dict:
    return {"active": "My team", "teams": {"My team": empty_squad()}}


def _squad_only(payload: dict) -> dict:
    return {
        "players": list(payload.get("players") or []),
        "coach_id": payload.get("coach_id"),
        "coach_price": payload.get("coach_price"),
    }


def _as_book(payload: dict) -> dict:
    if isinstance(payload.get("teams"), dict) and payload["teams"]:
        teams = {str(name): _squad_only(squad) for name, squad in payload["teams"].items()}
        active = str(payload.get("active") or next(iter(teams)))
        if active not in teams:
            active = next(iter(teams))
        return {"active": active, "teams": teams}
    return {"active": "My team", "teams": {"My team": _squad_only(payload)}}


def load_book(root: Path) -> dict:
    path = squad_path(root)
    if not path.exists():
        book = empty_book()
        save_book(root, book)
        return book
    payload = json.loads(path.read_text(encoding="utf-8"))
    book = _as_book(payload)
    if "teams" not in payload:
        save_book(root, book)
    return book


def save_book(root: Path, book: dict) -> None:
    path = squad_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_as_book(book), indent=2), encoding="utf-8")


def load_squad(root: Path) -> dict:
    """The squad selected on My team."""
    book = load_book(root)
    return book["teams"][book["active"]]


def save_squad(root: Path, squad: dict) -> None:
    book = load_book(root)
    book["teams"][book["active"]] = _squad_only(squad)
    save_book(root, book)


def set_active_team(root: Path, name: str) -> None:
    book = load_book(root)
    if name not in book["teams"]:
        return
    book["active"] = name
    save_book(root, book)


def create_team(root: Path, name: str) -> str | None:
    cleaned = " ".join(name.split())
    if not cleaned:
        return "Enter a team name."
    book = load_book(root)
    if cleaned in book["teams"]:
        return "A team with that name already exists."
    book["teams"][cleaned] = empty_squad()
    book["active"] = cleaned
    save_book(root, book)
    return None


def delete_team(root: Path, name: str) -> str | None:
    book = load_book(root)
    if name not in book["teams"]:
        return None
    if len(book["teams"]) == 1:
        return "Keep at least one team."
    del book["teams"][name]
    if book["active"] == name:
        book["active"] = next(iter(book["teams"]))
    save_book(root, book)
    return None


def rename_team(root: Path, old: str, new: str) -> str | None:
    cleaned = " ".join(new.split())
    if not cleaned:
        return "Enter a team name."
    book = load_book(root)
    if old not in book["teams"]:
        return None
    if cleaned != old and cleaned in book["teams"]:
        return "A team with that name already exists."
    squad = book["teams"].pop(old)
    book["teams"][cleaned] = squad
    if book["active"] == old:
        book["active"] = cleaned
    save_book(root, book)
    return None


def save_named_squad(root: Path, name: str, squad: dict) -> None:
    book = load_book(root)
    book["teams"][name] = _squad_only(squad)
    book["active"] = name
    save_book(root, book)


def credits_path(root: Path) -> Path:
    return root / "data" / "credit_overrides.json"


def load_credits(root: Path) -> dict:
    """Current credits typed on Best team. Missing players keep the starting price."""
    path = credits_path(root)
    if not path.exists():
        return {"players": {}, "coaches": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "players": {str(key): float(value) for key, value in (payload.get("players") or {}).items()},
        "coaches": {str(key): float(value) for key, value in (payload.get("coaches") or {}).items()},
    }


def save_credits(root: Path, credits: dict) -> None:
    path = credits_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "players": {str(key): float(value) for key, value in (credits.get("players") or {}).items()},
        "coaches": {str(key): float(value) for key, value in (credits.get("coaches") or {}).items()},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def apply_player_credits(projections: pd.DataFrame, credits: dict) -> pd.DataFrame:
    """Use a typed credit when one exists, otherwise the starting price."""
    frame = projections.copy()
    mapping = credits.get("players") or {}
    if mapping and "player_id" in frame.columns and "price" in frame.columns:
        override = frame["player_id"].astype(str).map({str(key): value for key, value in mapping.items()})
        frame["price"] = override.where(override.notna(), frame["price"])
        frame["points_per_credit"] = [
            None
            if price is None or pd.isna(price) or price == 0 or projected is None or pd.isna(projected)
            else float(projected) / float(price)
            for projected, price in zip(frame["projected"], frame["price"])
        ]
    return frame


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def score_squad(squad: dict, projections: pd.DataFrame, coaches: pd.DataFrame) -> dict:
    """Apply starter, sixth-man, bench, and captain multipliers."""
    messages: list[str] = []
    by_player = {}
    if projections is not None and not projections.empty:
        by_player = {row.player_id: row for row in projections.itertuples(index=False)}
    by_coach = {}
    if coaches is not None and not coaches.empty:
        by_coach = {row.coach_id: row for row in coaches.itertuples(index=False)}

    rows = []
    seen = set()
    captain_used = False
    for entry in squad.get("players") or []:
        player_id = str(entry.get("player_id") or "")
        if not player_id or player_id in seen:
            if player_id in seen:
                messages.append(f"{player_id} is listed more than once.")
            continue
        seen.add(player_id)
        slot = entry.get("slot") or "bench"
        if slot not in SLOT_MULTIPLIER:
            slot = "bench"
            messages.append(f"{player_id} has an unknown slot, counted as bench.")
        captain = bool(entry.get("captain")) and slot == "starter" and not captain_used
        if captain:
            captain_used = True
        info = by_player.get(player_id)
        projected = None if info is None or pd.isna(info.projected) else float(info.projected)
        multiplier = 2.0 if captain else SLOT_MULTIPLIER[slot]
        points = None if projected is None else projected * multiplier
        price = None if info is None else _number(getattr(info, "price", None))
        per_credit = points_per_credit(projected, price)
        if info is None:
            messages.append(f"{player_id} is not on the current projection board.")
        elif price is None:
            messages.append(f"No published price for {info.player_name}.")
        rows.append(
            {
                "player_id": player_id,
                "player_name": info.player_name if info is not None else player_id,
                "team_name": info.team_name if info is not None else "",
                "position_group": info.position_group if info is not None else None,
                "opponent_name": info.opponent_name if info is not None else None,
                "home_away": info.home_away if info is not None else None,
                "slot": slot,
                "captain": captain,
                "price": price,
                "per_credit": per_credit,
                "projected": projected,
                "multiplier": multiplier,
                "points": points,
                "availability": getattr(info, "availability", "available") if info is not None else "available",
                "status_label": getattr(info, "status_label", "Available") if info is not None else "",
                "injury_note": getattr(info, "injury_note", "") if info is not None else "",
            }
        )

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["_order"] = frame["slot"].map(SLOT_ORDER)
        frame = frame.sort_values(["_order", "points"], ascending=[True, False]).drop(columns="_order")
        frame = frame.reset_index(drop=True)

    counts = {"G": 0, "F": 0, "C": 0}
    slot_counts = {"starter": 0, "sixth": 0, "bench": 0}
    captains = 0
    if not frame.empty:
        for row in frame.itertuples(index=False):
            if row.position_group in counts:
                counts[row.position_group] += 1
            slot_counts[row.slot] = slot_counts.get(row.slot, 0) + 1
            if row.captain:
                captains += 1

    raw_captains = sum(1 for entry in squad.get("players") or [] if entry.get("captain"))
    if raw_captains > 1:
        messages.append("Only one captain counts, and they must be in the starting five.")
    elif raw_captains == 1 and captains == 0:
        messages.append("The captain has to be one of the five starters.")
    if len(frame) > 10:
        messages.append("A squad is 10 players. Extra names are still listed.")
    if len(frame) == 10:
        for position, needed in REQUIRED_POSITIONS.items():
            if counts[position] != needed:
                messages.append(
                    f"Need {needed} {position}, squad has {counts[position]}."
                )
        if slot_counts.get("starter") != 5 or slot_counts.get("sixth") != 1 or slot_counts.get("bench") != 4:
            messages.append(
                "Set 5 starters, 1 sixth man, and 4 bench players. "
                f"Now {slot_counts.get('starter', 0)}/{slot_counts.get('sixth', 0)}/{slot_counts.get('bench', 0)}."
            )
        if captains != 1:
            messages.append("Pick one starter as captain. That score is doubled.")

    coach_id = squad.get("coach_id")
    coach = by_coach.get(str(coach_id)) if coach_id else None
    coach_price = _number(squad.get("coach_price"))
    coach_points = None
    if coach is not None and not pd.isna(coach.projected):
        coach_points = float(coach.projected)
    elif coach_id:
        messages.append("The selected coach has no projection yet.")

    player_total = 0.0 if frame.empty else float(frame["points"].fillna(0).sum())
    total = player_total + (coach_points or 0.0)
    prices = []
    if not frame.empty:
        prices.extend(price for price in frame["price"] if price is not None)
    if coach_price is not None:
        prices.append(coach_price)
    price_sum = sum(prices) if prices else None
    if price_sum is not None and price_sum > BUDGET:
        messages.append(f"Entered prices sum to {price_sum:.1f}, over the {BUDGET:.0f} credit budget.")

    return {
        "players": frame,
        "counts": counts,
        "slot_counts": slot_counts,
        "captains": captains,
        "coach": coach,
        "coach_points": coach_points,
        "coach_price": coach_price,
        "total": total,
        "price_sum": price_sum,
        "messages": messages,
    }

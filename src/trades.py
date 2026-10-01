"""Single-player trade-up suggestions (same position, price cap, higher projection)."""

from __future__ import annotations

from src.optimize import (
    _cap_ok,
    _pid,
    _records,
    _stamp_turns,
    _team_counts,
    _turn_days,
    _turns_ok,
)
from src.squad import SLOT_MULTIPLIER

MIN_PROJECTED_GAIN = 1.0
MIN_COUNTED_GAIN = 0.5
DISPLAY_LIMIT = 10


def slot_multiplier(entry: dict | None) -> float:
    """Fantasy multiplier for the saved slot (captain 2×, bench 0.5×)."""
    if not entry:
        return 1.0
    slot = entry.get("slot") or "bench"
    if slot not in SLOT_MULTIPLIER:
        slot = "bench"
    captain = bool(entry.get("captain")) and slot == "starter"
    return 2.0 if captain else float(SLOT_MULTIPLIER[slot])


def slot_label(entry: dict | None) -> str:
    if not entry:
        return "Starter"
    slot = entry.get("slot") or "bench"
    if bool(entry.get("captain")) and slot == "starter":
        return "Captain"
    return {"starter": "Starter", "sixth": "Sixth", "bench": "Bench"}.get(slot, slot.title())


def _entry_by_player(saved_players: list[dict] | None) -> dict[str, dict]:
    if not saved_players:
        return {}
    return {_pid(entry.get("player_id")): entry for entry in saved_players if entry.get("player_id")}


def suggest_trade_upgrades(
    outgoing_id: str,
    saved_ids: list[str],
    records: list[dict],
    *,
    saved_players: list[dict] | None = None,
    limit: int = DISPLAY_LIMIT,
    min_projected_gain: float = MIN_PROJECTED_GAIN,
    min_counted_gain: float = MIN_COUNTED_GAIN,
    min_gain: float = 0.05,
) -> dict:
    """Replacements for one saved player: same G/F/C, price <= outgoing, higher projected.

    Ranks by +Counted (same saved slot/captain as the outgoing player), then +Proj.
    Drops small upgrades below `min_projected_gain` and `min_counted_gain`.
    """
    empty = {"outgoing": None, "candidates": [], "message": "", "outgoing_counted": None, "slot_label": ""}
    if not records:
        return {**empty, "message": "No priced Available players on this slate."}
    by_id = {player["player_id"]: player for player in records}
    outgoing_key = _pid(outgoing_id)
    outgoing = by_id.get(outgoing_key)
    if outgoing is None:
        return {
            **empty,
            "message": "That player has no published price and projection on this slate (or is not Available).",
        }
    saved_set = {_pid(player_id) for player_id in saved_ids}
    if outgoing_key not in saved_set:
        return {**empty, "message": "Pick a player who is on the selected saved team."}
    entry = _entry_by_player(saved_players).get(outgoing_key)
    mult = slot_multiplier(entry)
    outgoing_counted = float(outgoing["projected"]) * mult
    others = [key for key in saved_set if key != outgoing_key]
    others_records = [by_id[key] for key in others if key in by_id]
    counts = _team_counts(others_records)
    turn_days = _turn_days(records)
    check_turns = len(others_records) == len(others) and len(others) == 9

    rows = []
    for candidate in records:
        cid = candidate["player_id"]
        if cid == outgoing_key or cid in saved_set:
            continue
        if candidate["position_group"] != outgoing["position_group"]:
            continue
        if float(candidate["price"]) > float(outgoing["price"]) + 1e-6:
            continue
        if float(candidate["projected"]) < float(outgoing["projected"]) + min_gain:
            continue
        trial = dict(counts)
        club = candidate["team_code"]
        trial[club] = trial.get(club, 0) + 1
        if not _cap_ok(trial):
            continue
        if check_turns:
            squad = list(others_records) + [candidate]
            _stamp_turns(squad)
            if not _turns_ok(squad, turn_days):
                continue
        delta_proj = float(candidate["projected"]) - float(outgoing["projected"])
        incoming_counted = float(candidate["projected"]) * mult
        delta_counted = incoming_counted - outgoing_counted
        if delta_proj < float(min_projected_gain) or delta_counted < float(min_counted_gain):
            continue
        credit_freed = max(0.0, float(outgoing["price"]) - float(candidate["price"]))
        rows.append(
            {
                **candidate,
                "delta_projected": delta_proj,
                "delta_counted": delta_counted,
                "delta_price": float(candidate["price"]) - float(outgoing["price"]),
                "counted": incoming_counted,
                "credit_freed": credit_freed,
            }
        )
    rows.sort(key=lambda row: (row["delta_counted"], row["delta_projected"]), reverse=True)
    capped = rows[: max(int(limit), 1)]
    message = ""
    if not capped:
        message = (
            f"No Available {outgoing['position_group']} at or below {outgoing['price']:.1f} credits "
            f"adds at least +{min_projected_gain:.1f} projected and +{min_counted_gain:.1f} counted "
            f"for your {slot_label(entry)} slot on {outgoing['player_name']}."
        )
    return {
        "outgoing": outgoing,
        "candidates": capped,
        "message": message,
        "outgoing_counted": outgoing_counted,
        "slot_label": slot_label(entry),
    }


def trade_records(projections, day):
    """Player pool for trade search (same as Best team picker)."""
    return _records(projections, day)

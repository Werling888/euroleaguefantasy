"""Fantasy Challenge ownership (popularity) helpers for differentials."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

# Share of managers: below this is a differential; at or above is template risk.
DIFFERENTIAL_MAX = 0.10
TEMPLATE_MIN = 0.20


def _held_set(held_ids: Iterable[str] | None) -> set[str]:
    return {str(player_id) for player_id in (held_ids or []) if player_id not in (None, "")}


def differentials(
    projections: pd.DataFrame,
    held_ids: Iterable[str] | None = None,
    *,
    low: float = DIFFERENTIAL_MAX,
    high: float = TEMPLATE_MIN,
    limit: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Low-owned high-projected pickups and highly owned players you do not have.

    Ownership is the Fantasy Challenge `popularity` share (0–1). Returns
    (differentials, template_risk), each empty when ownership is missing.
    """
    empty = projections.iloc[0:0].copy() if projections is not None else pd.DataFrame()
    if projections is None or projections.empty or "ownership" not in projections.columns:
        return empty, empty
    frame = projections.dropna(subset=["ownership"]).copy()
    if frame.empty:
        return empty, empty
    held = _held_set(held_ids)
    if "player_id" in frame.columns:
        frame["_held"] = frame["player_id"].astype(str).isin(held)
    else:
        frame["_held"] = False
    available = frame
    if "availability" in frame.columns:
        available = frame[frame["availability"].fillna("available") == "available"]
    diffs = available[(~available["_held"]) & (available["ownership"] < float(low))]
    if "projected" in diffs.columns:
        diffs = diffs.sort_values("projected", ascending=False, na_position="last")
    else:
        diffs = diffs.sort_values("ownership", ascending=True, na_position="last")
    risk = available[(~available["_held"]) & (available["ownership"] >= float(high))]
    if "ownership" in risk.columns:
        risk = risk.sort_values(
            ["ownership", "projected"] if "projected" in risk.columns else ["ownership"],
            ascending=[False, False] if "projected" in risk.columns else [False],
            na_position="last",
        )
    return diffs.head(int(limit)).drop(columns="_held", errors="ignore"), risk.head(
        int(limit)
    ).drop(columns="_held", errors="ignore")

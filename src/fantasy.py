"""Official EuroLeague Fantasy Challenge scoring.

Player score is the box-score PIR, plus 10% when the team wins.
Coach score follows the published margin table. Overtime uses the
close-game bucket (win +10, loss -5) regardless of the final margin.
"""

from __future__ import annotations

import math

WIN_BONUS = 0.10
HOME_COURT = 3.5
MARGIN_SCALE = 12.0
COACH_SIGMA = 12.0


def player_fantasy(pir: float, won: bool) -> float:
    """PIR, or PIR * 1.10 when the player's team won."""
    score = float(pir)
    if won:
        return score * (1.0 + WIN_BONUS)
    return score


def is_overtime(quarters) -> bool:
    """True when any overtime period was played."""
    if not isinstance(quarters, dict):
        return False
    for index in range(1, 6):
        if quarters.get(f"ot{index}") is not None:
            return True
    return False


def coach_points(margin: float, overtime: bool = False) -> float:
    """Coach fantasy points from the final margin.

    Official buckets:
    win 1-10 or OT +10, win 11-20 +20, win 21+ +25,
    loss 1-10 or OT -5, loss 11-20 -10, loss 21+ -20.
    """
    margin = float(margin)
    if margin > 0:
        if overtime or margin <= 10:
            return 10.0
        if margin <= 20:
            return 20.0
        return 25.0
    if margin < 0:
        size = abs(margin)
        if overtime or size <= 10:
            return -5.0
        if size <= 20:
            return -10.0
        return -20.0
    return 0.0


def win_probability(expected_margin: float, scale: float = MARGIN_SCALE) -> float:
    """Logistic win chance from an expected point margin."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    return 1.0 / (1.0 + math.exp(-float(expected_margin) / scale))


def expected_margin(team_net: float, opponent_net: float, is_home: bool) -> float:
    """Net-rating difference plus a home-court bump of about 3.5 points."""
    bump = HOME_COURT if is_home else -HOME_COURT
    return float(team_net) - float(opponent_net) + bump


def _normal_cdf(x: float, mean: float, sigma: float) -> float:
    if math.isinf(x):
        return 1.0 if x > 0 else 0.0
    return 0.5 * (1.0 + math.erf((x - mean) / (sigma * math.sqrt(2.0))))


def expected_coach_points(margin: float, sigma: float = COACH_SIGMA) -> float:
    """Probability-weighted coach score around an expected margin.

    Integer buckets are approximated with half-point edges so a margin of
    10.5 sits on the boundary between a 10-point win and an 11-point win.
    """
    mean = float(margin)
    # (low inclusive edge, high exclusive edge, points)
    buckets = (
        (20.5, math.inf, 25.0),
        (10.5, 20.5, 20.0),
        (0.5, 10.5, 10.0),
        (-0.5, 0.5, 0.0),
        (-10.5, -0.5, -5.0),
        (-20.5, -10.5, -10.0),
        (-math.inf, -20.5, -20.0),
    )
    total = 0.0
    for low, high, points in buckets:
        probability = _normal_cdf(high, mean, sigma) - _normal_cdf(low, mean, sigma)
        total += probability * points
    return total


def position_group(position_name: str | None) -> str | None:
    """Map a feed position name onto fantasy slots G / F / C."""
    if not isinstance(position_name, str):
        return None
    key = position_name.strip().lower()
    if key in {"g", "guard"} or "guard" in key:
        return "G"
    if key in {"f", "forward"} or "forward" in key:
        return "F"
    if key in {"c", "center"} or "center" in key:
        return "C"
    return None


def display_name(raw: str | None) -> str:
    """Turn 'AJINCA, MELVIN' into 'Melvin Ajinca'."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    text = raw.strip()
    if "," in text:
        last, first = text.split(",", 1)
        return f"{first.strip().title()} {last.strip().title()}".strip()
    return text.title()

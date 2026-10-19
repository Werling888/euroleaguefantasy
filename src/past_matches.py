"""Opponent players who scored against a club in recent games."""

from __future__ import annotations

import pandas as pd

WINDOWS = ("All", "5", "3", "1")


def window_limit(label: str) -> int | None:
    """How many most recent games to keep. All means every result this season."""
    if label == "All":
        return None
    return int(label)


def opponent_high_scores(
    logs: pd.DataFrame,
    team_code: str,
    season: str,
    limit: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Games the club played, newest first, and the opponent players in those games.

    `limit` None keeps every regular-season game in `season`. Opponent rows are
    players who faced `team_code` and played minutes, highest fantasy first.
    """
    game_columns = [
        "game_code",
        "round",
        "date",
        "opponent_code",
        "opponent_name",
        "is_home",
        "team_score",
        "opp_score",
    ]
    line_columns = [
        "game_code",
        "round",
        "date",
        "player_name",
        "team_name",
        "position_group",
        "is_home",
        "minutes",
        "fantasy",
    ]
    empty_games = pd.DataFrame(columns=game_columns)
    empty_lines = pd.DataFrame(columns=line_columns)
    if logs is None or logs.empty or not team_code:
        return empty_games, empty_lines

    frame = logs.copy()
    if "phase" in frame.columns:
        frame = frame[frame["phase"] == "RS"]
    if "season_code" in frame.columns:
        frame = frame[frame["season_code"] == season]
    if "played" in frame.columns:
        frame = frame[frame["played"] == True]  # noqa: E712
    if frame.empty or "team_code" not in frame.columns:
        return empty_games, empty_lines

    ours = frame[frame["team_code"] == team_code]
    if ours.empty:
        return empty_games, empty_lines
    ours = ours.copy()
    ours["date"] = pd.to_datetime(ours["date"], utc=True, errors="coerce")
    games = (
        ours.groupby("game_code", as_index=False)
        .agg(
            round=("round", "max"),
            date=("date", "max"),
            opponent_code=("opponent_code", "first"),
            opponent_name=("opponent_name", "first"),
            is_home=("is_home", "first"),
            team_score=("team_score", "first"),
            opp_score=("opp_score", "first"),
        )
        .sort_values(["date", "game_code"], ascending=[False, False])
    )
    if limit is not None:
        games = games.head(max(int(limit), 0))
    game_ids = set(games["game_code"])
    lines = frame[frame["game_code"].isin(game_ids) & (frame["opponent_code"] == team_code)].copy()
    if lines.empty:
        return games.reset_index(drop=True), empty_lines
    lines["date"] = pd.to_datetime(lines["date"], utc=True, errors="coerce")
    if "position_group" in lines.columns:
        lines = lines[lines["position_group"].isin(["G", "F", "C"])]
    if lines.empty:
        return games.reset_index(drop=True), empty_lines
    lines = lines.sort_values(
        ["fantasy", "minutes", "player_name"],
        ascending=[False, False, True],
    )
    return games.reset_index(drop=True), lines.reset_index(drop=True)


def position_averages(lines: pd.DataFrame, games: pd.DataFrame) -> dict[str, float | None]:
    """Mean G/F/C fantasy per game across the matches shown.

    Each game's pie is the total fantasy that position scored. A game with
    nobody at that position counts as zero. The mean divides by the number
    of games in the window.
    """
    empty = {"G": None, "F": None, "C": None}
    if games is None or games.empty:
        return empty
    count = len(games)
    totals = {"G": 0.0, "F": 0.0, "C": 0.0}
    if lines is not None and not lines.empty and "position_group" in lines.columns:
        for position, group in lines.groupby("position_group"):
            key = str(position)
            if key in totals:
                totals[key] = float(group["fantasy"].sum())
    return {position: totals[position] / count for position in totals}


def select_venue(
    games: pd.DataFrame,
    lines: pd.DataFrame,
    venue: str,
    limit: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Home, Away, or both of the club's games, then the matches-back limit.

    `games` is newest first. `is_home` is the selected club's venue.
    """
    if games is None or games.empty:
        return games, lines
    chosen = games
    if venue == "Home":
        chosen = games[games["is_home"] == True]  # noqa: E712
    elif venue == "Away":
        chosen = games[games["is_home"] == False]  # noqa: E712
    if limit is not None:
        chosen = chosen.head(max(int(limit), 0))
    chosen = chosen.reset_index(drop=True)
    if lines is None or lines.empty:
        return chosen, lines
    kept = lines[lines["game_code"].isin(set(chosen["game_code"]))].reset_index(drop=True)
    return chosen, kept


def position_highs(lines: pd.DataFrame) -> pd.DataFrame:
    """Highest-fantasy opponent at each position in each game."""
    columns = ["game_code", "position_group", "player_name", "team_name", "fantasy"]
    if lines is None or lines.empty:
        return pd.DataFrame(columns=columns)
    ranked = lines.sort_values(
        ["fantasy", "minutes", "player_name"],
        ascending=[False, False, True],
    )
    return ranked.groupby(["game_code", "position_group"], as_index=False).first()[columns]


def fpts_cost_band(points, cost) -> str | None:
    """Red below the whole number of his price, yellow through 1.1 times it, green above that.

    A price of 11.9 and a score of 11 is yellow. The same whole-number floor applies to every price.
    """
    if points is None or cost is None or pd.isna(points) or pd.isna(cost):
        return None
    scored = float(points)
    price = float(cost)
    if scored < int(price):
        return "red"
    if scored <= price * 1.1:
        return "yellow"
    return "green"

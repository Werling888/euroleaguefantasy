"""Next-game fantasy projections from form, opponent, and win chance."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.fantasy import expected_coach_points, expected_margin, win_probability

CURRENT_SEASON = "E2026"
PRIOR_SEASON = "E2025"
FORM_GAMES = 1
RECENT_WINDOW = 8


@dataclass
class DashboardData:
    projections: pd.DataFrame
    coaches: pd.DataFrame
    defense: pd.DataFrame
    current_season: str
    prior_season: str | None


def _regular_coach_logs(coach_games: pd.DataFrame | None) -> pd.DataFrame:
    if coach_games is None or coach_games.empty:
        return pd.DataFrame()
    logs = coach_games.loc[coach_games["phase"] == "RS"].copy()
    logs["date"] = pd.to_datetime(logs["date"], utc=True, errors="coerce")
    logs["coach_id"] = logs["coach_id"].astype(str)
    return logs


def _coach_stats(logs: pd.DataFrame) -> dict:
    """Season, recent form, and range for one coach's official margin points."""
    empty = {
        "sample_gp": 0,
        "season_fantasy": None,
        "last5_fantasy": None,
        "volatility": None,
        "avg_margin": None,
        "floor": None,
        "ceiling": None,
        "form_source": "none",
    }
    if logs is None or logs.empty:
        return empty
    current = logs[logs["season_code"] == CURRENT_SEASON].sort_values("date")
    prior = logs[logs["season_code"] == PRIOR_SEASON].sort_values("date")

    def _mean(frame: pd.DataFrame) -> float | None:
        if frame.empty:
            return None
        return float(frame["coach_points"].mean())

    current_avg = _mean(current)
    prior_avg = _mean(prior)
    if current_avg is not None:
        sample = current
        source = CURRENT_SEASON
    elif prior_avg is not None:
        sample = prior
        source = PRIOR_SEASON
    else:
        return empty
    ordered = sample
    points = ordered["coach_points"]
    recent = points.tail(RECENT_WINDOW)
    return {
        "sample_gp": int(len(ordered)),
        "season_fantasy": float(points.mean()),
        "last5_fantasy": float(points.tail(5).mean()),
        "volatility": float(points.std(ddof=0)) if len(points) else None,
        "avg_margin": float(ordered["margin"].mean()),
        "floor": float(recent.quantile(0.2)),
        "ceiling": float(recent.quantile(0.8)),
        "form_source": source,
    }


def _played_regular(player_games: pd.DataFrame) -> pd.DataFrame:
    logs = player_games
    if logs is None or logs.empty:
        return pd.DataFrame()
    mask = (logs["phase"] == "RS") & (logs["played"] == True)  # noqa: E712
    logs = logs.loc[mask].copy()
    logs["date"] = pd.to_datetime(logs["date"], utc=True, errors="coerce")
    logs["position_group"] = logs["position_group"].where(logs["position_group"].isin(["G", "F", "C"]))
    return logs


def _form_sample(current: pd.DataFrame, prior: pd.DataFrame) -> pd.DataFrame:
    """This season if it has a game; otherwise last season."""
    if current is not None and not current.empty:
        return current
    if prior is not None and not prior.empty:
        return prior
    return pd.DataFrame()


def _baseline_pir(logs: pd.DataFrame) -> float | None:
    if logs is None or logs.empty:
        return None
    return float(logs["pir"].mean())


def _blend_baseline(current: pd.DataFrame, prior: pd.DataFrame) -> tuple[float | None, str]:
    """PIR per game from this season if he has played; otherwise last season."""
    sample = _form_sample(current, prior)
    if sample.empty:
        return None, "none"
    source = CURRENT_SEASON if current is not None and not current.empty else PRIOR_SEASON
    return _baseline_pir(sample), source


def _playing_time(logs: pd.DataFrame) -> tuple[float | None, float | None]:
    """Average minutes in the sample, and fantasy points produced per minute."""
    if logs is None or logs.empty:
        return None, None
    played_minutes = logs["minutes"].fillna(0)
    total_minutes = float(played_minutes.sum())
    if total_minutes < 1:
        return None, None
    rate = float(logs["fantasy"].fillna(0).sum()) / total_minutes
    return float(played_minutes.mean()), rate


def _blend_playing_time(current: pd.DataFrame, prior: pd.DataFrame) -> tuple[float | None, float | None, str]:
    """This season's average minutes and fantasy if he has played; otherwise last season."""
    current_minutes, current_rate = _playing_time(current)
    if current_minutes is not None:
        return current_minutes, current_minutes * current_rate, CURRENT_SEASON
    prior_minutes, prior_rate = _playing_time(prior)
    if prior_minutes is not None:
        return prior_minutes, prior_minutes * prior_rate, PRIOR_SEASON
    return None, None, "none"


def _home_away_ratios(logs: pd.DataFrame) -> tuple[float, float]:
    """Home and away fantasy multipliers from one split of the same logs."""
    if logs is None or logs.empty:
        return 1.0, 1.0
    home = logs[logs["is_home"] == True]  # noqa: E712
    away = logs[logs["is_home"] == False]  # noqa: E712
    if len(home) < 3 or len(away) < 3:
        return 1.0, 1.0
    overall = float(logs["fantasy"].mean())
    if abs(overall) < 1:
        return 1.0, 1.0
    return float(home["fantasy"].mean()) / overall, float(away["fantasy"].mean()) / overall


def _recent_fantasy(current: pd.DataFrame, prior: pd.DataFrame) -> pd.Series:
    # grouped logs are pre-sorted by date in build_dashboard
    if current is not None and not current.empty:
        return current["fantasy"].tail(RECENT_WINDOW)
    if prior is not None and not prior.empty:
        return prior["fantasy"].tail(RECENT_WINDOW)
    return pd.Series(dtype=float)


# Game pie: total G/F/C fantasy vs that defense. One starter's 31 is that
# night's C slot, not what every opposing center will score.
FACTOR_SHRINK_GAMES = 4
FACTOR_FLOOR = 0.75
FACTOR_CEILING = 1.35


def _position_game_pies(logs: pd.DataFrame, season: str) -> pd.DataFrame:
    """One row per defense, game, and position: sum of that position's fantasy."""
    empty = pd.DataFrame(columns=["opponent_code", "game_code", "position_group", "pie", "date"])
    if logs is None or logs.empty:
        return empty
    subset = logs[logs["season_code"] == season].copy()
    if subset.empty:
        return empty
    subset = subset[subset["position_group"].isin(["G", "F", "C"])]
    if subset.empty:
        return empty
    if "date" in subset.columns:
        subset["date"] = pd.to_datetime(subset["date"], utc=True, errors="coerce")
    else:
        subset["date"] = pd.NaT
    return subset.groupby(["opponent_code", "game_code", "position_group"], as_index=False).agg(
        pie=("fantasy", "sum"),
        date=("date", "max"),
    )


def _means_from_pies(pies: pd.DataFrame) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    league: dict[str, float] = {}
    allowed: dict[tuple[str, str], float] = {}
    if pies is None or pies.empty:
        return league, allowed
    for position, group in pies.groupby("position_group"):
        league[str(position)] = float(group["pie"].mean())
    for (opponent, position), group in pies.groupby(["opponent_code", "position_group"]):
        allowed[(str(opponent), str(position))] = float(group["pie"].mean())
    return league, allowed


def _windows_from_pies(pies: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float], dict[str, int]]:
    empty = pd.DataFrame(
        columns=["opponent_code", "position_group", "l3", "l5", "l10", "allowed_all", "games"]
    )
    league, _allowed = _means_from_pies(pies)
    games: dict[str, int] = {}
    if pies is None or pies.empty:
        return empty, league, games

    def window_mean(frame: pd.DataFrame, codes: list) -> float | None:
        sample = frame[frame["game_code"].isin(codes)]
        if sample.empty:
            return None
        return float(sample["pie"].mean())

    rows = []
    for opponent, club in pies.groupby("opponent_code"):
        order = club.groupby("game_code")["date"].max().sort_values(ascending=False, na_position="last")
        game_ids = list(order.index)
        games[str(opponent)] = len(game_ids)
        for position in ("G", "F", "C"):
            at_pos = club[club["position_group"] == position]
            rows.append(
                {
                    "opponent_code": opponent,
                    "position_group": position,
                    "l3": window_mean(at_pos, game_ids[:3]),
                    "l5": window_mean(at_pos, game_ids[:5]),
                    "l10": window_mean(at_pos, game_ids[:10]),
                    "allowed_all": window_mean(at_pos, game_ids),
                    "games": len(game_ids),
                }
            )
    return pd.DataFrame(rows), league, games


def _defense_profiles(logs: pd.DataFrame):
    """Current-season G/F/C game pies, plus last season's means for shrinkage."""
    current = _position_game_pies(logs, CURRENT_SEASON)
    profiles, league, games = _windows_from_pies(current)
    prior_league, prior_allowed = _means_from_pies(_position_game_pies(logs, PRIOR_SEASON))
    return profiles, league, games, prior_league, prior_allowed


def _season_factor(allowed: float | None, league: float | None) -> float | None:
    """This-season pie versus the league pie. Not shrunk toward last season."""
    if allowed is None or league is None:
        return None
    try:
        base = float(league)
        pie = float(allowed)
    except (TypeError, ValueError):
        return None
    if base <= 0 or pd.isna(base) or pd.isna(pie):
        return None
    return pie / base


def _shrink_factor(current: float | None, prior: float | None, games: int) -> float:
    center = 1.0 if prior is None else float(prior)
    if current is None:
        return max(FACTOR_FLOOR, min(FACTOR_CEILING, center))
    n = max(int(games), 0)
    if n <= 0:
        return max(FACTOR_FLOOR, min(FACTOR_CEILING, center))
    raw = (n * float(current) + FACTOR_SHRINK_GAMES * center) / (n + FACTOR_SHRINK_GAMES)
    return max(FACTOR_FLOOR, min(FACTOR_CEILING, raw))


def _opponent_factor(
    opponent: str,
    position: str | None,
    league: dict[str, float],
    profiles: pd.DataFrame,
    prior_league: dict[str, float] | None = None,
    prior_allowed: dict[tuple[str, str], float] | None = None,
) -> float:
    if position not in {"G", "F", "C"}:
        return 1.0
    prior_league = prior_league or {}
    prior_allowed = prior_allowed or {}
    hit = pd.DataFrame()
    if profiles is not None and not profiles.empty:
        hit = profiles[(profiles["opponent_code"] == opponent) & (profiles["position_group"] == position)]
    current_raw = None if hit.empty else hit.iloc[0]["allowed_all"]
    n = 0 if hit.empty else int(hit.iloc[0]["games"])
    if current_raw is not None and pd.isna(current_raw):
        current_raw = None
    base = league.get(position)
    current = None if current_raw is None or not base else float(current_raw) / float(base)
    prior_raw = prior_allowed.get((opponent, position))
    prior_base = prior_league.get(position)
    prior = None if prior_raw is None or not prior_base else float(prior_raw) / float(prior_base)
    if n >= 1 and current is not None:
        return _shrink_factor(current, prior, n)
    if prior is not None:
        return _shrink_factor(None, prior, 0)
    return 1.0


def _net_lookup(standings: pd.DataFrame) -> dict[tuple, tuple[float, int]]:
    lookup: dict[tuple, tuple[float, int]] = {}
    if standings is None or standings.empty:
        return lookup
    for row in standings.itertuples(index=False):
        net = row.net_per_game
        if net is None or (isinstance(net, float) and math.isnan(net)):
            continue
        lookup[(row.season_code, row.team_code)] = (float(net), int(row.games_played))
    return lookup


def _team_net(team: str, nets: dict) -> float:
    current = nets.get((CURRENT_SEASON, team))
    prior = nets.get((PRIOR_SEASON, team))
    if current:
        return current[0]
    if prior:
        return prior[0]
    return 0.0


def _next_games(games: pd.DataFrame) -> pd.DataFrame:
    upcoming = games[(games["season_code"] == CURRENT_SEASON) & (games["status"] != "result")].copy()
    if upcoming.empty:
        return upcoming
    upcoming["date"] = pd.to_datetime(upcoming["date"], utc=True, errors="coerce")
    return upcoming.sort_values(["date", "round", "game_code"])


def _games_for_team(upcoming: pd.DataFrame, team_code: str, limit: int = 5) -> list[dict]:
    """The next games for one club, earliest first."""
    if upcoming.empty:
        return []
    home = upcoming[upcoming["home_code"] == team_code]
    away = upcoming[upcoming["away_code"] == team_code]
    candidates = pd.concat([home, away], ignore_index=True).sort_values(["date", "round", "game_code"])
    games = []
    for game in candidates.head(limit).itertuples(index=False):
        is_home = game.home_code == team_code
        games.append(
            {
                "game_code": int(game.game_code),
                "date": game.date,
                "round": int(game.round),
                "is_home": bool(is_home),
                "opponent_code": game.away_code if is_home else game.home_code,
                "opponent_name": game.away_name if is_home else game.home_name,
            }
        )
    return games


def _schedule_index(upcoming: pd.DataFrame, limit: int = 5) -> dict[str, list[dict]]:
    if upcoming.empty:
        return {}
    teams = set(upcoming["home_code"].dropna()) | set(upcoming["away_code"].dropna())
    return {team: _games_for_team(upcoming, team, limit) for team in teams}


def _sample_averages(current: pd.DataFrame, prior: pd.DataFrame):
    sample = _form_sample(current, prior)
    empty = (None, None, None, 0, None, None, 0)
    if sample is None or sample.empty:
        return empty
    ordered = sample  # grouped logs are pre-sorted by date in build_dashboard
    season_fantasy = float(ordered["fantasy"].mean())
    last5 = float(ordered.tail(5)["fantasy"].mean())
    minutes = float(ordered["minutes"].mean())
    per36 = float(season_fantasy / minutes * 36.0) if minutes > 0 else None
    volatility = float(ordered["fantasy"].std(ddof=0)) if len(ordered) > 1 else None
    sample_gp = int(len(ordered))
    gp_current = 0 if current is None or current.empty else int(len(current))
    return season_fantasy, last5, minutes, gp_current, per36, volatility, sample_gp


def _shots_per_game(current: pd.DataFrame, prior: pd.DataFrame) -> float | None:
    sample = _form_sample(current, prior)
    if sample is None or sample.empty or "shots" not in sample.columns:
        return None
    return float(sample["shots"].mean())


# A player who takes more shots than his position's average has more chances to
# score, so nudge projected up or down a little for shot volume. Shrunk toward
# 1.0 (no effect) while the sample is small, and capped modestly so it nudges
# rather than overrides the PIR-based baseline.
SHOT_SHRINK_GAMES = 4
SHOT_FLOOR = 0.90
SHOT_CEILING = 1.10


def _shot_factor(shots_per_game: float | None, position_avg_shots: float | None, games: int) -> float:
    if shots_per_game is None or not position_avg_shots:
        return 1.0
    n = max(int(games), 0)
    raw = shots_per_game / position_avg_shots
    shrunk = (n * raw + SHOT_SHRINK_GAMES * 1.0) / (n + SHOT_SHRINK_GAMES)
    return max(SHOT_FLOOR, min(SHOT_CEILING, shrunk))


def build_dashboard(cache: dict[str, pd.DataFrame], season: str | None = None) -> DashboardData:
    """Project every active player and coach for the upcoming round.

    `season` limits logs to one season. None uses this season for anyone who has played,
    and last season only when that player (or defense) has no game yet.
    """
    logs = _played_regular(cache["player_games"])
    rosters = cache["rosters"]
    games = cache["games"]
    standings = cache["standings"] if cache["standings"] is not None else pd.DataFrame()
    coach_logs = _regular_coach_logs(cache.get("coach_games"))
    if season is not None:
        if not logs.empty:
            logs = logs[logs["season_code"] == season]
        if not standings.empty:
            standings = standings[standings["season_code"] == season]
        if not coach_logs.empty:
            coach_logs = coach_logs[coach_logs["season_code"] == season]
    players = rosters[
        (rosters["season_code"] == CURRENT_SEASON) & (rosters["role"] == "player")
    ].copy()
    if players.empty:
        players = rosters[(rosters["season_code"] == PRIOR_SEASON) & (rosters["role"] == "player")].copy()
    from src.roster_overrides import apply_roster_overrides
    from src.prices import apply_fantasy_positions, apply_fantasy_positions_to_logs

    players = apply_roster_overrides(players, CURRENT_SEASON)
    players = apply_fantasy_positions(players, cache.get("prices"))
    logs = apply_fantasy_positions_to_logs(logs, players)
    profiles, league, _games_played, prior_league, prior_allowed = _defense_profiles(logs)
    nets = _net_lookup(standings)
    upcoming = _next_games(games)
    schedule_by_team = _schedule_index(upcoming, limit=5)

    # These depend only on team/opponent/position, not on the individual player,
    # so compute each distinct value once and reuse it across the player, coach,
    # and defense loops below instead of recomputing it per player (~1400 -> ~140).
    net_by_team: dict[str, float] = {}

    def team_net(team: str) -> float:
        if team not in net_by_team:
            net_by_team[team] = _team_net(team, nets)
        return net_by_team[team]

    outlook_memo: dict[tuple, tuple[float, float]] = {}

    def game_outlook(team: str, opponent: str, is_home: bool) -> tuple[float, float]:
        """(expected margin, win probability) for one team's game."""
        key = (team, opponent, is_home)
        if key not in outlook_memo:
            margin = expected_margin(team_net(team), team_net(opponent), is_home)
            outlook_memo[key] = (margin, win_probability(margin))
        return outlook_memo[key]

    factor_memo: dict[tuple, float] = {}

    def opp_factor(opponent: str, position: str | None) -> float:
        key = (opponent, position)
        if key not in factor_memo:
            factor_memo[key] = _opponent_factor(
                opponent, position, league, profiles, prior_league, prior_allowed
            )
        return factor_memo[key]

    position_avg = {}
    shots_avg = {}
    if not logs.empty:
        current_all = logs[logs["season_code"] == CURRENT_SEASON]
        prior_all = logs[logs["season_code"] == PRIOR_SEASON]
        fill = current_all if not current_all.empty else prior_all
        for position, group in fill.groupby("position_group"):
            position_avg[position] = float(group["fantasy"].mean())
            if "shots" in group.columns:
                shots_avg[position] = float(group["shots"].mean())

    grouped = {
        (season, player_id): group.sort_values("date")
        for (season, player_id), group in logs.groupby(["season_code", "player_id"])
    } if not logs.empty else {}

    rows = []
    for player in players.itertuples(index=False):
        current_logs = grouped.get((CURRENT_SEASON, player.person_id), pd.DataFrame())
        prior_logs = grouped.get((PRIOR_SEASON, player.person_id), pd.DataFrame())
        position = player.position_group
        if position not in {"G", "F", "C"}:
            mode_logs = _form_sample(current_logs, prior_logs)
            mode = mode_logs["position_group"].dropna().mode() if not mode_logs.empty else pd.Series(dtype=object)
            position = mode.iloc[0] if not mode.empty else None
        expected_minutes, baseline, source = _blend_playing_time(current_logs, prior_logs)
        if baseline is None and position in position_avg:
            baseline = position_avg[position]
            source = "position"
            expected_minutes = None
        season_fantasy, last5, minutes, gp_current, per36, volatility, sample_gp = _sample_averages(
            current_logs, prior_logs
        )
        shots_per_game = _shots_per_game(current_logs, prior_logs)
        shot_factor = _shot_factor(shots_per_game, shots_avg.get(position), sample_gp)
        form_logs = _form_sample(current_logs, prior_logs)
        home_ratio, away_ratio = _home_away_ratios(form_logs)
        schedule = []
        if baseline is not None:
            recent = _recent_fantasy(current_logs, prior_logs)
            for game in schedule_by_team.get(player.team_code, []):
                factor = opp_factor(game["opponent_code"], position)
                ratio = home_ratio if game["is_home"] else away_ratio
                margin, chance = game_outlook(
                    player.team_code, game["opponent_code"], game["is_home"]
                )
                # baseline is Fpts/g. factor is this team's G/F/C game pie versus
                # the league pie, shrunk while few games are in. shot_factor nudges
                # for shot volume versus the position average, also shrunk early.
                projected = baseline * factor * ratio * (1.0 + 0.10 * chance) * shot_factor
                schedule.append(
                    {
                        "round": game["round"],
                        "date": game["date"],
                        "opponent_code": game["opponent_code"],
                        "opponent_name": game["opponent_name"],
                        "home_away": "Home" if game["is_home"] else "Away",
                        "opp_factor": factor,
                        "win_prob": chance,
                        "projected": projected,
                    }
                )
        nxt = schedule[0] if schedule else None
        row = {
            "player_id": player.person_id,
            "player_name": player.person_name,
            "team_code": player.team_code,
            "team_name": player.team_name,
            "position_group": position,
            "gp_current": gp_current,
            "sample_gp": sample_gp,
            "minutes": minutes,
            "expected_minutes": expected_minutes,
            "season_fantasy": season_fantasy,
            "last5_fantasy": last5,
            "fantasy_per36": per36,
            "volatility": volatility,
            "shots_per_game": shots_per_game,
            "form_source": source,
            "opponent_code": None,
            "opponent_name": None,
            "home_away": None,
            "game_date": None,
            "round": None,
            "opp_factor": None,
            "win_prob": None,
            "projected": None,
            "floor": None,
            "ceiling": None,
            "schedule": schedule,
        }
        if schedule:
            first = schedule[0]
            floor = ceiling = None
            if baseline is not None and not recent.empty:
                floor = float(np.percentile(recent, 20) * first["opp_factor"])
                ceiling = float(np.percentile(recent, 80) * first["opp_factor"])
            row.update(
                {
                    "opponent_code": first["opponent_code"],
                    "opponent_name": first["opponent_name"],
                    "home_away": first["home_away"],
                    "game_date": first["date"],
                    "round": first["round"],
                    "opp_factor": first["opp_factor"],
                    "win_prob": first["win_prob"],
                    "projected": first["projected"],
                    "floor": floor,
                    "ceiling": ceiling,
                }
            )
        rows.append(row)

    projections = pd.DataFrame(rows)
    from src.prices import assign_prices

    projections = assign_prices(projections, cache.get("prices"))
    from src.injuries import apply_injury_minutes, assign_availability

    projections = assign_availability(projections, cache.get("injuries"))
    projections = apply_injury_minutes(projections)
    if not projections.empty:
        projections = projections.sort_values(
            ["projected", "season_fantasy"], ascending=False, na_position="last"
        ).reset_index(drop=True)

    coach_rows = []
    coaches = rosters[
        (rosters["season_code"] == CURRENT_SEASON) & (rosters["role"] == "coach")
    ]
    logs_by_coach = {
        coach_id: frame for coach_id, frame in coach_logs.groupby("coach_id")
    } if not coach_logs.empty else {}
    seen_teams = set()
    for coach in coaches.itertuples(index=False):
        if coach.team_code in seen_teams:
            continue
        seen_teams.add(coach.team_code)
        schedule = []
        for game in schedule_by_team.get(coach.team_code, []):
            margin, chance = game_outlook(coach.team_code, game["opponent_code"], game["is_home"])
            schedule.append(
                {
                    "round": game["round"],
                    "date": game["date"],
                    "opponent_name": game["opponent_name"],
                    "home_away": "Home" if game["is_home"] else "Away",
                    "win_prob": chance,
                    "projected": expected_coach_points(margin),
                }
            )
        nxt = schedule[0] if schedule else None
        record = {
            "coach_id": coach.person_id,
            "coach_name": coach.person_name,
            "team_code": coach.team_code,
            "team_name": coach.team_name,
            "opponent_code": None,
            "opponent_name": None,
            "home_away": None,
            "game_date": None,
            "round": None,
            "win_prob": None,
            "projected": None,
            "schedule": schedule,
        }
        record.update(_coach_stats(logs_by_coach.get(str(coach.person_id), pd.DataFrame())))
        if nxt is not None:
            record.update(
                {
                    "opponent_name": nxt["opponent_name"],
                    "home_away": nxt["home_away"],
                    "game_date": nxt["date"],
                    "round": nxt["round"],
                    "win_prob": nxt["win_prob"],
                    "projected": nxt["projected"],
                }
            )
        coach_rows.append(record)
    coach_frame = pd.DataFrame(coach_rows)
    from src.prices import assign_coach_ownership

    coach_frame = assign_coach_ownership(coach_frame, cache.get("prices"))

    defense_rows = []
    teams = sorted(set(players["team_code"])) if not players.empty else []
    for team in teams:
        team_schedule = schedule_by_team.get(team)
        nxt = team_schedule[0] if team_schedule else None
        if nxt is None:
            continue
        win_prob = game_outlook(team, nxt["opponent_code"], nxt["is_home"])[1]
        for position in ("G", "F", "C"):
            factor = opp_factor(nxt["opponent_code"], position)
            league_avg = league.get(position)
            hit = profiles[
                (profiles["opponent_code"] == nxt["opponent_code"])
                & (profiles["position_group"] == position)
            ]
            allowed_all = l3 = l5 = l10 = None
            sample_games = 0
            if not hit.empty:
                row = hit.iloc[0]
                allowed_all = None if pd.isna(row["allowed_all"]) else float(row["allowed_all"])
                l3 = None if pd.isna(row["l3"]) else float(row["l3"])
                l5 = None if pd.isna(row["l5"]) else float(row["l5"])
                l10 = None if pd.isna(row["l10"]) else float(row["l10"])
                sample_games = int(row["games"])
            defense_rows.append(
                {
                    "team_code": team,
                    "opponent_code": nxt["opponent_code"],
                    "opponent_name": nxt["opponent_name"],
                    "home_away": "Home" if nxt["is_home"] else "Away",
                    "game_date": nxt["date"],
                    "round": nxt["round"],
                    "win_prob": win_prob,
                    "position_group": position,
                    "league_allowed": league_avg,
                    "opp_factor": factor,
                    "opp_factor_raw": _season_factor(allowed_all, league_avg),
                    "opp_allowed": allowed_all,
                    "l3": l3,
                    "l5": l5,
                    "l10": l10,
                    "defense_games": sample_games,
                }
            )
    defense = pd.DataFrame(defense_rows)
    return DashboardData(
        projections=projections,
        coaches=coach_frame,
        defense=defense,
        current_season=CURRENT_SEASON,
        prior_season=PRIOR_SEASON,
    )

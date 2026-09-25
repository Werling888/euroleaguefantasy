"""Next-game fantasy projections from form, opponent, and win chance."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.fantasy import expected_coach_points, expected_margin, win_probability

CURRENT_SEASON = "E2026"
PRIOR_SEASON = "E2025"
FORM_GAMES = 8
DEFENSE_GAMES = 5
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
    games = len(current)

    def _mean(frame: pd.DataFrame) -> float | None:
        if frame.empty:
            return None
        return float(frame["coach_points"].mean())

    current_avg = _mean(current)
    prior_avg = _mean(prior)
    if games >= FORM_GAMES and current_avg is not None:
        sample = current
        source = CURRENT_SEASON
    elif games == 0 and prior_avg is not None:
        sample = prior
        source = PRIOR_SEASON
    elif games == 0:
        return empty
    elif prior_avg is None:
        sample = current
        source = CURRENT_SEASON
    else:
        sample = pd.concat([prior, current], ignore_index=True).sort_values("date")
        source = "blend"
    ordered = sample  # current/prior/blend are all already date-sorted above
    points = ordered["coach_points"]
    recent = points.tail(RECENT_WINDOW)
    return {
        "sample_gp": int(len(ordered)),
        "season_fantasy": float(points.mean()) if source != "blend" else float(
            (1.0 - games / FORM_GAMES) * prior_avg + (games / FORM_GAMES) * current_avg
        ),
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


def _baseline_pir(logs: pd.DataFrame) -> float | None:
    if logs is None or logs.empty:
        return None
    ordered = logs.sort_values("date")
    season_avg = float(ordered["pir"].mean())
    last5 = float(ordered.tail(5)["pir"].mean())
    return 0.6 * last5 + 0.4 * season_avg


def _blend_baseline(current: pd.DataFrame, prior: pd.DataFrame) -> tuple[float | None, str]:
    """60/40 recent form, fading last season until 8 current games exist."""
    current_base = _baseline_pir(current)
    prior_base = _baseline_pir(prior)
    games = 0 if current is None else len(current)
    if games >= FORM_GAMES and current_base is not None:
        return current_base, CURRENT_SEASON
    if games == 0:
        if prior_base is None:
            return None, "none"
        return prior_base, PRIOR_SEASON
    if prior_base is None:
        return current_base, CURRENT_SEASON
    prior_weight = 1.0 - games / FORM_GAMES
    blended = prior_weight * prior_base + (1.0 - prior_weight) * current_base
    return blended, "blend"


def _playing_time(logs: pd.DataFrame) -> tuple[float | None, float | None]:
    """Expected minutes, and PIR produced per minute over the same games."""
    if logs is None or logs.empty:
        return None, None
    ordered = logs  # grouped logs are pre-sorted by date in build_dashboard
    played_minutes = ordered["minutes"].fillna(0)
    total_minutes = float(played_minutes.sum())
    if total_minutes < 1:
        return None, None
    last_minutes = float(played_minutes.tail(5).mean())
    season_minutes = float(played_minutes.mean())
    rate = float(ordered["pir"].fillna(0).sum()) / total_minutes
    return 0.6 * last_minutes + 0.4 * season_minutes, rate


def _blend_playing_time(current: pd.DataFrame, prior: pd.DataFrame) -> tuple[float | None, float | None, str]:
    """Baseline fantasy from how long the player is on the floor times PIR per minute."""
    current_minutes, current_rate = _playing_time(current)
    prior_minutes, prior_rate = _playing_time(prior)
    current_base = None if current_minutes is None else current_minutes * current_rate
    prior_base = None if prior_minutes is None else prior_minutes * prior_rate
    games = 0 if current is None else len(current)
    if games >= FORM_GAMES and current_base is not None:
        return current_minutes, current_base, CURRENT_SEASON
    if games == 0:
        if prior_base is None:
            return None, None, "none"
        return prior_minutes, prior_base, PRIOR_SEASON
    if prior_base is None or current_minutes is None or prior_minutes is None:
        return current_minutes, current_base, CURRENT_SEASON
    weight = games / FORM_GAMES
    return (
        weight * current_minutes + (1.0 - weight) * prior_minutes,
        weight * current_base + (1.0 - weight) * prior_base,
        "blend",
    )


def _home_away_ratios(logs: pd.DataFrame) -> tuple[float, float]:
    """Home and away PIR multipliers from one split of the same logs."""
    if logs is None or logs.empty:
        return 1.0, 1.0
    home = logs[logs["is_home"] == True]  # noqa: E712
    away = logs[logs["is_home"] == False]  # noqa: E712
    if len(home) < 3 or len(away) < 3:
        return 1.0, 1.0
    overall = float(logs["pir"].mean())
    if abs(overall) < 1:
        return 1.0, 1.0
    return float(home["pir"].mean()) / overall, float(away["pir"].mean()) / overall


def _recent_fantasy(current: pd.DataFrame, prior: pd.DataFrame) -> pd.Series:
    # grouped logs are pre-sorted by date in build_dashboard
    current_ordered = current
    prior_ordered = prior
    current_values = (
        current_ordered["fantasy"] if current_ordered is not None and not current_ordered.empty else pd.Series(dtype=float)
    )
    if len(current_values) >= RECENT_WINDOW:
        return current_values.tail(RECENT_WINDOW)
    need = RECENT_WINDOW - len(current_values)
    prior_values = (
        prior_ordered["fantasy"].tail(need)
        if prior_ordered is not None and not prior_ordered.empty
        else pd.Series(dtype=float)
    )
    return pd.concat([prior_values, current_values], ignore_index=True)


def _defense_tables(logs: pd.DataFrame) -> tuple[dict, dict, dict]:
    """League fantasy allowed, opponent fantasy allowed, and games played."""
    league: dict[tuple, float] = {}
    allowed: dict[tuple, float] = {}
    games: dict[tuple, int] = {}
    if logs.empty:
        return league, allowed, games
    usable = logs.dropna(subset=["position_group"])
    for (season, position), group in usable.groupby(["season_code", "position_group"]):
        league[(season, position)] = float(group["fantasy"].mean())
    for (season, opponent, position), group in usable.groupby(
        ["season_code", "opponent_code", "position_group"]
    ):
        allowed[(season, opponent, position)] = float(group["fantasy"].mean())
    for (season, team), group in logs.groupby(["season_code", "team_code"]):
        games[(season, team)] = int(group["game_code"].nunique())
    return league, allowed, games


def _opponent_factor(
    opponent: str,
    position: str | None,
    league: dict,
    allowed: dict,
    games: dict,
) -> float:
    if position not in {"G", "F", "C"}:
        return 1.0
    current_games = games.get((CURRENT_SEASON, opponent), 0)
    current_raw = allowed.get((CURRENT_SEASON, opponent, position))
    current_league = league.get((CURRENT_SEASON, position))
    prior_raw = allowed.get((PRIOR_SEASON, opponent, position))
    prior_league = league.get((PRIOR_SEASON, position))

    def ratio(raw, base) -> float | None:
        if raw is None or base in (None, 0):
            return None
        return raw / base

    current_factor = ratio(current_raw, current_league)
    prior_factor = ratio(prior_raw, prior_league)
    if current_games >= DEFENSE_GAMES and current_factor is not None:
        return current_factor
    if current_games == 0 or current_factor is None:
        return prior_factor if prior_factor is not None else 1.0
    shrunk = 1.0 + (current_games / DEFENSE_GAMES) * (current_factor - 1.0)
    if prior_factor is None:
        return shrunk
    weight = current_games / DEFENSE_GAMES
    return weight * shrunk + (1.0 - weight) * prior_factor


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
    if current and current[1] >= DEFENSE_GAMES:
        return current[0]
    if prior:
        return prior[0]
    if current:
        return current[0]
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
    sample = current if current is not None and not current.empty else prior
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


def build_dashboard(cache: dict[str, pd.DataFrame], season: str | None = None) -> DashboardData:
    """Project every active player and coach for the upcoming round.

    `season` limits the form, matchups, and win chances to one season's games.
    None blends the two seasons.
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
    league, allowed, games_played = _defense_tables(logs)
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
            factor_memo[key] = _opponent_factor(opponent, position, league, allowed, games_played)
        return factor_memo[key]

    players = rosters[
        (rosters["season_code"] == CURRENT_SEASON) & (rosters["role"] == "player")
    ].copy()
    if players.empty:
        players = rosters[(rosters["season_code"] == PRIOR_SEASON) & (rosters["role"] == "player")].copy()
    from src.roster_overrides import apply_roster_overrides

    players = apply_roster_overrides(players, CURRENT_SEASON)

    position_pir = {}
    if not logs.empty:
        prior_logs_all = logs[logs["season_code"] == PRIOR_SEASON]
        for position, group in prior_logs_all.groupby("position_group"):
            position_pir[position] = float(group["pir"].mean())

    grouped = {
        (season, player_id): group.sort_values("date")
        for (season, player_id), group in logs.groupby(["season_code", "player_id"])
    } if not logs.empty else {}

    rows = []
    for player in players.itertuples(index=False):
        current_logs = grouped.get((CURRENT_SEASON, player.person_id), pd.DataFrame())
        prior_logs = grouped.get((PRIOR_SEASON, player.person_id), pd.DataFrame())
        position = player.position_group
        if position not in {"G", "F", "C"} and not prior_logs.empty:
            mode = prior_logs["position_group"].dropna().mode()
            position = mode.iloc[0] if not mode.empty else None
        expected_minutes, baseline, source = _blend_playing_time(current_logs, prior_logs)
        if baseline is None and position in position_pir:
            baseline = position_pir[position]
            source = "position"
            expected_minutes = None
        season_fantasy, last5, minutes, gp_current, per36, volatility, sample_gp = _sample_averages(
            current_logs, prior_logs
        )
        pieces = [
            frame
            for frame in (prior_logs, current_logs)
            if frame is not None and not frame.empty
        ]
        context_logs = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
        home_ratio, away_ratio = _home_away_ratios(context_logs)
        schedule = []
        if baseline is not None:
            recent = _recent_fantasy(current_logs, prior_logs)
            for game in schedule_by_team.get(player.team_code, []):
                factor = opp_factor(game["opponent_code"], position)
                ratio = home_ratio if game["is_home"] else away_ratio
                margin, chance = game_outlook(
                    player.team_code, game["opponent_code"], game["is_home"]
                )
                projected = baseline * factor * ratio * (1.0 + 0.10 * chance)
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
    from src.injuries import assign_availability

    projections = assign_availability(projections, cache.get("injuries"))
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
            league_avg = league.get((PRIOR_SEASON, position))
            if games_played.get((CURRENT_SEASON, nxt["opponent_code"]), 0) >= DEFENSE_GAMES:
                league_avg = league.get((CURRENT_SEASON, position), league_avg)
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
                    "opp_allowed": None if league_avg in (None, 0) else factor * league_avg,
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

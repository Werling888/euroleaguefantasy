"""Check the squad picker on the previous EuroLeague season.

Rounds are split in time: the first 80% are the only games the picker may see
when it chooses, and the last 20% are the test. A random split would leak
later games into the past.

Prices in this test are not the published list. A player who scores above the
training-set average gains credits, and those gains are added to the squad's
total. This script does not change the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.fantasy import expected_margin, win_probability
from src.optimize import build_best_team
from src.project import _home_away_ratios, _playing_time

SEASON = "E2025"
TRAIN_SHARE = 0.80
START_BUDGET = 100.0
MIN_GAMES = 5
PRICE_FLOOR = 4.0
PRICE_CAP = 30.0
# How many fantasy points above the training average move the price by 1 credit.
# ponytail: linear credit change, not the official price table
POINTS_PER_CREDIT = 15.0


def load_season() -> pd.DataFrame:
    logs = pd.read_parquet(ROOT / "data" / "cache" / "player_games.parquet")
    logs = logs[(logs["season_code"] == SEASON) & (logs["phase"] == "RS")].copy()
    logs["date"] = pd.to_datetime(logs["date"], utc=True)
    logs["player_id"] = logs["player_id"].astype(str)
    return logs.sort_values(["date", "game_code", "player_id"])


def _mode_position(frame: pd.DataFrame) -> str | None:
    values = frame["position_group"].dropna()
    values = values[values.isin(["G", "F", "C"])]
    if values.empty:
        return None
    return str(values.mode().iloc[0])


def market_tables(history: pd.DataFrame) -> dict:
    played = history[history["played"] == True]  # noqa: E712
    games = history.drop_duplicates(["game_code", "team_code"])
    net = (games["team_score"] - games["opp_score"]).groupby(games["team_code"]).mean().to_dict()
    league = played.groupby("position_group")["fantasy"].mean().to_dict()
    allowed = played.groupby(["opponent_code", "position_group"])["fantasy"].mean().to_dict()
    samples = played.groupby(["opponent_code", "position_group"]).size().to_dict()
    minutes = played.groupby("position_group")["minutes"].mean().to_dict()
    return {"net": net, "league": league, "allowed": allowed, "samples": samples, "minutes": minutes}


def project_round(history: pd.DataFrame, slate: pd.DataFrame, prices: dict[str, float], by_player: dict) -> pd.DataFrame:
    """One-round projections from games already played. Same pieces as the app."""
    tables = market_tables(history)
    rows = []
    for game in slate.itertuples(index=False):
        past = by_player.get(game.player_id)
        if past is not None:
            past = past[past["round"] < game.round]
        else:
            past = history.iloc[0:0]
        position = _mode_position(past) if past is not None and not past.empty else None
        if position is None:
            position = game.position_group if game.position_group in {"G", "F", "C"} else None
        if position is None:
            continue
        minutes, rate = _playing_time(past) if past is not None and not past.empty else (None, None)
        if minutes is None or rate is None:
            minutes = tables["minutes"].get(position)
            rate = None
            baseline = tables["league"].get(position)
            expected_minutes = None
        else:
            baseline = minutes * rate
            expected_minutes = minutes
        if baseline is None:
            continue
        league = tables["league"].get(position) or 0
        sample = tables["samples"].get((game.opponent_code, position), 0)
        raw = tables["allowed"].get((game.opponent_code, position))
        factor = raw / league if sample >= 5 and raw is not None and league else 1.0
        home_ratio, away_ratio = _home_away_ratios(past)
        ratio = home_ratio if game.is_home else away_ratio
        margin = expected_margin(
            tables["net"].get(game.team_code, 0.0),
            tables["net"].get(game.opponent_code, 0.0),
            bool(game.is_home),
        )
        chance = win_probability(margin)
        projected = float(baseline) * float(factor) * float(ratio) * (1.0 + 0.10 * chance)
        price = prices.get(game.player_id)
        if price is None:
            continue
        rows.append(
            {
                "player_id": game.player_id,
                "player_name": game.player_name,
                "team_code": game.team_code,
                "team_name": game.team_name,
                "position_group": position,
                "opponent_name": game.opponent_name,
                "home_away": "Home" if game.is_home else "Away",
                "game_date": game.date,
                "expected_minutes": expected_minutes,
                "price": float(price),
                "projected": projected,
                "points_per_credit": projected / price if price else None,
                "actual": float(game.fantasy) if game.played else 0.0,
            }
        )
    return pd.DataFrame(rows)


def starting_prices(train: pd.DataFrame, par: float) -> dict[str, float]:
    played = train[train["played"] == True]  # noqa: E712
    prices = {}
    for player_id, group in played.groupby("player_id"):
        if len(group) < MIN_GAMES:
            continue
        position = _mode_position(group)
        if position is None:
            continue
        fpg = float(group["fantasy"].mean())
        prices[str(player_id)] = float(np.clip(fpg * (10.0 / par), PRICE_FLOOR, 18.0))
    return prices


def price_delta(actual: float, par: float) -> float:
    return (float(actual) - par) / POINTS_PER_CREDIT


def apply_prices(prices: dict[str, float], played: pd.DataFrame, owned: set[str], par: float) -> float:
    """Raise prices for good games. Owned gains are added to the squad credits."""
    gain = 0.0
    seen = set()
    for row in played.itertuples(index=False):
        if row.player_id in seen or row.player_id not in prices:
            continue
        seen.add(row.player_id)
        delta = price_delta(row.fantasy, par)
        prices[row.player_id] = float(np.clip(prices[row.player_id] + delta, PRICE_FLOOR, PRICE_CAP))
        if row.player_id in owned:
            gain += delta
    return gain


def score_squad(squad: pd.DataFrame, actual: pd.Series) -> float:
    multipliers = {"Captain": 2.0, "Starter": 1.0, "Sixth": 1.0, "Bench": 0.5}
    total = 0.0
    for row in squad.itertuples(index=False):
        total += float(actual.get(row.player_id, 0.0)) * multipliers[row.slot]
    return total


def played_actuals(slate: pd.DataFrame) -> pd.Series:
    played = slate[slate["played"] == True]  # noqa: E712
    return played.groupby("player_id")["fantasy"].sum()


def pick_ours(history, slate, prices, by_player, budget, averages: dict[str, float] | None = None) -> pd.DataFrame | None:
    projected = project_round(history, slate, prices, by_player)
    if averages is not None:
        projected["projected"] = projected["player_id"].map(averages)
        projected = projected.dropna(subset=["projected"])
        projected["points_per_credit"] = projected["projected"] / projected["price"]
    if projected.empty:
        return None
    result = build_best_team(projected, pd.DataFrame(), coach_price=0.0, budget=budget)
    if result["players"].empty:
        print("  picker:", result["message"])
        return None
    return result["players"]


def run_held(name: str, squad: pd.DataFrame, rounds: list[int], logs: pd.DataFrame, prices: dict, par: float) -> dict:
    book = dict(prices)
    budget = START_BUDGET
    points = []
    owned = set(squad["player_id"].astype(str))
    for rnd in rounds:
        slate = logs[logs["round"] == rnd]
        got = score_squad(squad, played_actuals(slate))
        points.append(got)
        played = slate[(slate["played"] == True) & (slate["player_id"].isin(book))]  # noqa: E712
        budget += apply_prices(book, played, owned, par)
        print(f"  {name} round {rnd}: {got:.1f} points, credits {budget:.1f}")
    return {"points": points, "credits": budget, "squad": squad, "prices": book}


def main() -> None:
    logs = load_season()
    rounds = sorted(int(value) for value in logs["round"].unique())
    cut = rounds[int(len(rounds) * TRAIN_SHARE) - 1]
    train_rounds = [rnd for rnd in rounds if rnd <= cut]
    test_rounds = [rnd for rnd in rounds if rnd > cut]
    train = logs[logs["round"] <= cut]
    played = train[train["played"] == True]  # noqa: E712
    par = float(played.loc[played["minutes"] >= 15, "fantasy"].mean())
    prices = starting_prices(train, par)
    played_logs = logs[logs["played"] == True]  # noqa: E712
    by_player = {pid: group for pid, group in played_logs.groupby("player_id", sort=False)}
    print(
        f"{SEASON} regular season, {len(rounds)} rounds. "
        f"Train rounds 1–{cut} ({len(train_rounds)}), test {test_rounds[0]}–{test_rounds[-1]} ({len(test_rounds)})."
    )
    print(f"Training average for a 15-minute game: {par:.1f}. A game that far above it adds 1 credit per {POINTS_PER_CREDIT:.0f} points.")

    pairs = []
    for rnd in test_rounds:
        history = logs[logs["round"] < rnd]
        slate = logs[logs["round"] == rnd]
        projected = project_round(history, slate, prices, by_player)
        for row in projected.itertuples(index=False):
            pairs.append((row.projected, row.actual))
    pred = np.array([item[0] for item in pairs])
    actual = np.array([item[1] for item in pairs])
    error = actual - pred
    corr = float(np.corrcoef(pred, actual)[0, 1]) if len(pred) > 2 else float("nan")
    print(
        f"Test games {len(pred)}: correlation {corr:.2f}, "
        f"average error {error.mean():+.1f}, typical miss {np.mean(np.abs(error)):.1f}."
    )

    opening = logs[logs["round"] == test_rounds[0]]
    ours = pick_ours(train, opening, prices, by_player, START_BUDGET)
    if ours is None:
        raise SystemExit("The picker could not build a squad from the training window.")
    ours["player_id"] = ours["player_id"].astype(str)
    print("Squad chosen from the training window only:")
    print(ours[["slot", "player_name", "position_group", "price", "projected"]].to_string(index=False))

    averages = {
        player_id: float(group.loc[group["round"] <= cut, "fantasy"].mean())
        for player_id, group in by_player.items()
        if (group["round"] <= cut).sum() >= MIN_GAMES
    }
    plain = pick_ours(train, opening, prices, by_player, START_BUDGET, averages)
    if plain is None:
        raise SystemExit("The season-average squad did not fit.")
    plain["player_id"] = plain["player_id"].astype(str)

    print("Held squads on the test rounds:")
    ours_held = run_held("picker", ours, test_rounds, logs, dict(prices), par)
    plain_held = run_held("season average", plain, test_rounds, logs, dict(prices), par)

    print("Picker rebuilt before each test round, still without future games:")
    live_prices = dict(prices)
    budget = START_BUDGET
    live_points = []
    for rnd in test_rounds:
        history = logs[logs["round"] < rnd]
        slate = logs[logs["round"] == rnd]
        squad = pick_ours(history, slate, live_prices, by_player, budget)
        if squad is None:
            print(f"  round {rnd}: no squad")
            continue
        squad["player_id"] = squad["player_id"].astype(str)
        got = score_squad(squad, played_actuals(slate))
        live_points.append(got)
        played_rows = slate[(slate["played"] == True) & (slate["player_id"].isin(live_prices))]  # noqa: E712
        budget += apply_prices(live_prices, played_rows, set(squad["player_id"]), par)
        print(f"  round {rnd}: {got:.1f} points, credits {budget:.1f}")

    print(
        f"Held picker {sum(ours_held['points']):.1f} points, credits {START_BUDGET:.0f} → {ours_held['credits']:.1f}. "
        f"Held season average {sum(plain_held['points']):.1f} points, credits {START_BUDGET:.0f} → {plain_held['credits']:.1f}. "
        f"Rebuilt picker {sum(live_points):.1f} points, credits {START_BUDGET:.0f} → {budget:.1f}."
    )


if __name__ == "__main__":
    main()

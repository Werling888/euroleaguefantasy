"""Best Fantasy Challenge squad for a round or a single slate day."""

from __future__ import annotations

from itertools import combinations

import pandas as pd

FORMATIONS = ((2, 2, 1), (1, 2, 2), (2, 1, 2), (1, 3, 1), (3, 1, 1))
# One center starts. The other stays on the bench so he can replace a dud.
BACKUP_FORMATIONS = ((2, 2, 1), (1, 3, 1), (3, 1, 1))
ROSTER = {"G": 4, "F": 4, "C": 2}
MAX_SAME_TEAM = 6
SLOT_ORDER = {"Captain": 0, "Starter": 1, "Sixth": 2, "Bench": 3}
STARTER_DEPTH = {"G": 8, "F": 8, "C": 6}
PLAY_MINUTES = 15.0


def _value_pool(players: list[dict], depth: int) -> list[dict]:
    """Players who return the most projected points for each credit."""
    return sorted(players, key=lambda player: player["projected"] / player["price"], reverse=True)[:depth]


def _minutes(player: dict) -> float:
    value = player.get("expected_minutes")
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _plays(player: dict) -> bool:
    return _minutes(player) >= PLAY_MINUTES


def _slate_share(by_pos: dict[str, list[dict]]) -> dict:
    """Share of clubs playing on each tip day. One day, two, or three."""
    clubs: dict = {}
    seen = set()
    for players in by_pos.values():
        for player in players:
            day = player.get("game_day")
            key = (day, player.get("team_code"))
            if day is None or key in seen:
                continue
            seen.add(key)
            clubs[day] = clubs.get(day, 0) + 1
    total = sum(clubs.values()) or 1
    return {day: count / total for day, count in clubs.items()}


def _day_counts(players: list[dict]) -> dict:
    counts: dict = {}
    for player in players:
        day = player.get("game_day")
        if day is not None:
            counts[day] = counts.get(day, 0) + 1
    return counts


def _day_need(day, owned: dict, share: dict) -> float:
    """1 when this tip day has nobody yet. After every day is covered, days are equal."""
    if day is None or len(share) < 2 or day not in share:
        return 0.0
    return 0.0 if owned.get(day, 0) else 1.0


def _backup_center(starters: list[dict], rest: list[dict]) -> bool:
    return any(player["position_group"] == "C" for player in rest)


def _search_formations(starter_pool, cheapest_by_pos, upgrades_by_pos, spend_cap, coach_points, formations=BACKUP_FORMATIONS):
    best = None
    for guards_needed, forwards_needed, centers_needed in formations:
        guards = starter_pool["G"]
        forwards = starter_pool["F"]
        centers = starter_pool["C"]
        if len(guards) < guards_needed or len(forwards) < forwards_needed or len(centers) < centers_needed:
            continue
        for guard_set in combinations(guards, guards_needed):
            for forward_set in combinations(forwards, forwards_needed):
                for center_set in combinations(centers, centers_needed):
                    starters = list(guard_set) + list(forward_set) + list(center_set)
                    if sum(player["price"] for player in starters) > spend_cap:
                        continue
                    filled = _fill_rest(starters, cheapest_by_pos, upgrades_by_pos, spend_cap)
                    if filled is None:
                        continue
                    sixth, bench = filled
                    total = _score(starters, sixth, bench, coach_points)
                    if best is None or total > best[0]:
                        best = (total, starters, sixth, bench)
    return best


def slate_days(projections: pd.DataFrame) -> list[pd.Timestamp]:
    """Athens calendar days that have a game in the upcoming round."""
    if projections.empty or "game_date" not in projections:
        return []
    dates = pd.to_datetime(projections["game_date"], utc=True, errors="coerce").dropna()
    if dates.empty:
        return []
    local = dates.dt.tz_convert("Europe/Athens")
    return sorted({value.normalize() for value in local})


def _records(projections: pd.DataFrame, day: pd.Timestamp | None) -> list[dict]:
    required = ["price", "projected", "position_group", "player_id"]
    if any(column not in projections.columns for column in required):
        return []
    frame = projections.dropna(subset=required).copy()
    frame = frame[frame["position_group"].isin(ROSTER)]
    frame = frame[frame["price"] > 0]
    if day is not None and not frame.empty:
        local = pd.to_datetime(frame["game_date"], utc=True, errors="coerce").dt.tz_convert("Europe/Athens")
        frame = frame[local.dt.normalize() == day]
    if "availability" in frame.columns:
        from src.injuries import eligible_to_play

        frame = frame[frame["availability"].map(lambda value: eligible_to_play(None if pd.isna(value) else value))]
    records = []
    for row in frame.itertuples(index=False):
        records.append(
            {
                "player_id": row.player_id,
                "player_name": row.player_name,
                "team_code": row.team_code,
                "team_name": row.team_name,
                "position_group": row.position_group,
                "opponent_name": row.opponent_name,
                "home_away": row.home_away,
                "price": float(row.price),
                "projected": float(row.projected),
                "expected_minutes": None if "expected_minutes" not in frame.columns or pd.isna(row.expected_minutes) else float(row.expected_minutes),
                "game_day": None
                if "game_date" not in frame.columns or pd.isna(row.game_date)
                else pd.to_datetime(row.game_date, utc=True).tz_convert("Europe/Athens").normalize(),
                "points_per_credit": None
                if "points_per_credit" not in frame.columns or pd.isna(row.points_per_credit)
                else float(row.points_per_credit),
                "availability": getattr(row, "availability", "available") or "available",
                "status_label": getattr(row, "status_label", "Available") or "Available",
                "injury_note": getattr(row, "injury_note", "") or "",
            }
        )
    records.sort(key=lambda player: player["projected"], reverse=True)
    return records


def _score(starters: list[dict], sixth: dict, bench: list[dict], coach_points: float) -> float:
    captain = max(starters, key=lambda player: player["projected"])
    total = coach_points + sixth["projected"]
    for player in starters:
        total += player["projected"] * (2.0 if player is captain else 1.0)
    for player in bench:
        total += player["projected"] * 0.5
    return total


def _team_counts(players: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for player in players:
        counts[player["team_code"]] = counts.get(player["team_code"], 0) + 1
    return counts


def _cap_ok(counts: dict[str, int]) -> bool:
    return all(count <= MAX_SAME_TEAM for count in counts.values())


def _take(player: dict, need: dict[str, int], counts: dict[str, int], money: float, used: set[str]) -> bool:
    if player["player_id"] in used or need[player["position_group"]] <= 0:
        return False
    if player["price"] > money + 1e-6:
        return False
    if counts.get(player["team_code"], 0) >= MAX_SAME_TEAM:
        return False
    need[player["position_group"]] -= 1
    counts[player["team_code"]] = counts.get(player["team_code"], 0) + 1
    used.add(player["player_id"])
    return True


def _cheap_reserves(need: dict[str, int], counts: dict[str, int], money: float, used: set[str], cheapest_by_pos: dict[str, list[dict]], share: dict, owned: dict):
    reserves = []
    for position, required in need.items():
        playable = [player for player in cheapest_by_pos[position] if _plays(player)]
        pool = playable if len(playable) >= required else cheapest_by_pos[position]
        taken = 0
        while taken < required:
            best = None
            best_rank = None
            for player in pool:
                if player["player_id"] in used or player["price"] > money + 1e-6:
                    continue
                if counts.get(player["team_code"], 0) >= MAX_SAME_TEAM:
                    continue
                rank = (
                    0 if _plays(player) else 1,
                    -_day_need(player.get("game_day"), owned, share),
                    player["price"],
                    -player["projected"],
                )
                if best_rank is None or rank < best_rank:
                    best_rank = rank
                    best = player
            if best is None or not _take(best, need, counts, money, used):
                return None
            money -= best["price"]
            reserves.append(best)
            day = best.get("game_day")
            if day is not None:
                owned[day] = owned.get(day, 0) + 1
            taken += 1
    return reserves, money


def _upgrade_reserves(reserves, leftover, counts, used, upgrades_by_pos, share, owned):
    """Spend leftover credits on the reserve that gains the most projected points."""
    for _ in range(10):
        best = None
        for index, current in enumerate(reserves):
            for candidate in upgrades_by_pos[current["position_group"]]:
                if candidate["projected"] <= current["projected"] + 0.05:
                    break
                if candidate["player_id"] in used:
                    continue
                if _plays(current) and not _plays(candidate):
                    continue
                if (
                    len(share) > 1
                    and current.get("game_day") != candidate.get("game_day")
                    and owned.get(current.get("game_day"), 0) <= 1
                ):
                    continue
                extra = candidate["price"] - current["price"]
                if extra > leftover + 1e-6:
                    continue
                if counts.get(candidate["team_code"], 0) >= MAX_SAME_TEAM and candidate["team_code"] != current["team_code"]:
                    continue
                gain = candidate["projected"] - current["projected"]
                if best is None or gain > best[0]:
                    best = (gain, index, candidate, extra)
                break
        if best is None:
            break
        _gain, index, candidate, extra = best
        current = reserves[index]
        counts[current["team_code"]] -= 1
        counts[candidate["team_code"]] = counts.get(candidate["team_code"], 0) + 1
        if not _cap_ok(counts):
            counts[candidate["team_code"]] -= 1
            counts[current["team_code"]] += 1
            used.add(candidate["player_id"])
            continue
        used.discard(current["player_id"])
        used.add(candidate["player_id"])
        leftover -= extra
        old_day = current.get("game_day")
        new_day = candidate.get("game_day")
        if old_day is not None:
            owned[old_day] = owned.get(old_day, 0) - 1
        if new_day is not None:
            owned[new_day] = owned.get(new_day, 0) + 1
        reserves[index] = candidate
    return reserves


def _fill_rest(starters: list[dict], cheapest_by_pos: dict[str, list[dict]], upgrades_by_pos: dict[str, list[dict]], budget: float):
    need = dict(ROSTER)
    counts: dict[str, int] = {}
    spent = 0.0
    used: set[str] = set()
    for player in starters:
        need[player["position_group"]] -= 1
        counts[player["team_code"]] = counts.get(player["team_code"], 0) + 1
        spent += player["price"]
        used.add(player["player_id"])
    if spent > budget + 1e-6 or any(value < 0 for value in need.values()) or not _cap_ok(counts):
        return None
    share = _slate_share(cheapest_by_pos)
    owned = _day_counts(starters)
    filled = _cheap_reserves(dict(need), dict(counts), budget - spent, set(used), cheapest_by_pos, share, owned)
    if filled is None:
        return None
    reserves, leftover = filled
    reserve_counts = _team_counts(starters + reserves)
    reserve_ids = used | {player["player_id"] for player in reserves}
    reserves = _upgrade_reserves(reserves, leftover, reserve_counts, reserve_ids, upgrades_by_pos, share, owned)
    if len(reserves) != 5:
        return None
    sixth = max(reserves, key=lambda player: player["projected"])
    bench = [player for player in reserves if player is not sixth]
    return sixth, bench


def _improve(starters, sixth, bench, available, budget, coach_points):
    """Swap in a higher-scoring player when the roster rules and budget still hold."""
    current = (starters, sixth, bench, _score(starters, sixth, bench, coach_points))
    for _ in range(3):
        starters, sixth, bench, best_score = current
        improved = False
        for candidate in available:
            ids = {player["player_id"] for player in starters + [sixth] + bench}
            if candidate["player_id"] in ids:
                continue
            for role in ("starter", "sixth", "bench"):
                group = starters if role == "starter" else bench
                targets = [sixth] if role == "sixth" else [player for player in group if player["position_group"] == candidate["position_group"]]
                for target in targets:
                    if candidate["projected"] <= target["projected"]:
                        continue
                    if role == "starter":
                        trial_starters = [candidate if player is target else player for player in starters]
                        trial_sixth, trial_bench = sixth, bench
                    elif role == "sixth":
                        trial_starters, trial_sixth, trial_bench = starters, candidate, bench
                    else:
                        trial_starters, trial_sixth = starters, sixth
                        trial_bench = [candidate if player is target else player for player in bench]
                    lineup = trial_starters + [trial_sixth] + trial_bench
                    counts = {"G": 0, "F": 0, "C": 0}
                    for player in lineup:
                        counts[player["position_group"]] += 1
                    if counts != ROSTER:
                        continue
                    if sum(player["price"] for player in lineup) > budget + 1e-6:
                        continue
                    if not _cap_ok(_team_counts(lineup)):
                        continue
                    # Starters must be a legal formation.
                    starter_shape = tuple(sum(player["position_group"] == position for player in trial_starters) for position in ("G", "F", "C"))
                    if starter_shape not in BACKUP_FORMATIONS:
                        continue
                    rest = [trial_sixth] + trial_bench
                    if _plays(target) and not _plays(candidate):
                        continue
                    squad = starters + [sixth] + bench
                    same_day = sum(1 for player in squad if player.get("game_day") == target.get("game_day"))
                    if target.get("game_day") != candidate.get("game_day") and same_day <= 1 and target.get("game_day") is not None:
                        days = {player.get("game_day") for player in squad if player.get("game_day") is not None}
                        if len(days) > 1:
                            continue
                    if not _backup_center(trial_starters, rest):
                        continue
                    score = _score(trial_starters, trial_sixth, trial_bench, coach_points)
                    if score > best_score + 0.05:
                        current = (trial_starters, trial_sixth, trial_bench, score)
                        best_score = score
                        improved = True
        if not improved:
            break
    return current[0], current[1], current[2]


def _window_sum(schedule, horizon: int) -> float | None:
    if not isinstance(schedule, list) or not schedule:
        return None
    games = schedule[:horizon]
    if not games:
        return None
    return float(sum(float(game["projected"]) for game in games))


def _apply_horizon(projections: pd.DataFrame, coaches: pd.DataFrame, horizon: int):
    """Replace next-game projections with the sum across the next `horizon` rounds."""
    if horizon <= 1:
        return projections, coaches
    frame = projections.copy()
    if "schedule" in frame.columns:
        frame["projected"] = frame["schedule"].map(lambda schedule: _window_sum(schedule, horizon))
        if "price" in frame.columns:
            frame["points_per_credit"] = [
                None
                if price is None or pd.isna(price) or price == 0 or projected is None or pd.isna(projected)
                else float(projected) / float(price)
                for projected, price in zip(frame["projected"], frame["price"])
            ]
    coach_frame = coaches
    if coaches is not None and not coaches.empty and "schedule" in coaches.columns:
        coach_frame = coaches.copy()
        coach_frame["projected"] = coach_frame["schedule"].map(lambda schedule: _window_sum(schedule, horizon))
    return frame, coach_frame


def _best_slots(players: list[dict], coach_points: float):
    """Best captain, starters, sixth man, and bench for a fixed group of 10."""
    by_position = {position: [player for player in players if player["position_group"] == position] for position in ROSTER}
    if any(len(by_position[position]) != ROSTER[position] for position in ROSTER):
        return None
    best = None
    for guards_needed, forwards_needed, centers_needed in BACKUP_FORMATIONS:
        for guards in combinations(by_position["G"], guards_needed):
            for forwards in combinations(by_position["F"], forwards_needed):
                for centers in combinations(by_position["C"], centers_needed):
                    starters = list(guards) + list(forwards) + list(centers)
                    starter_ids = {player["player_id"] for player in starters}
                    rest = [player for player in players if player["player_id"] not in starter_ids]
                    sixth = max(rest, key=lambda player: player["projected"])
                    bench = [player for player in rest if player is not sixth]
                    total = _score(starters, sixth, bench, coach_points)
                    if best is None or total > best[0]:
                        best = (total, starters, sixth, bench)
    return best


def _best_adds(pool: list[dict], need: dict[str, int], money: float, counts: dict[str, int]) -> list[list[dict]]:
    groups = {}
    for position, count in need.items():
        if count <= 0:
            continue
        options = [player for player in pool if player["position_group"] == position]
        playing = [player for player in options if _plays(player)]
        options = playing or options
        options.sort(key=lambda player: player["projected"], reverse=True)
        cheap = sorted(options, key=lambda player: player["price"])[:5]
        merged = []
        seen = set()
        for player in options[:8] + cheap:
            if player["player_id"] not in seen:
                seen.add(player["player_id"])
                merged.append(player)
        if len(merged) < count:
            return []
        groups[position] = (count, merged)
    if not groups:
        return [[]]
    found = []
    positions = list(groups)

    def walk(index: int, chosen: list[dict], spent: float, team_counts: dict[str, int]) -> None:
        if index == len(positions):
            found.append((sum(player["projected"] for player in chosen), list(chosen)))
            return
        position = positions[index]
        count, options = groups[position]
        for combo in combinations(options, count):
            price = sum(player["price"] for player in combo)
            if spent + price > money + 1e-6:
                continue
            trial = dict(team_counts)
            legal = True
            for player in combo:
                trial[player["team_code"]] = trial.get(player["team_code"], 0) + 1
                if trial[player["team_code"]] > MAX_SAME_TEAM:
                    legal = False
                    break
            if legal:
                walk(index + 1, chosen + list(combo), spent + price, trial)

    walk(0, [], 0.0, dict(counts))
    found.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in found[:8]]


def _search_changes(records: list[dict], held_ids: list[str], changes: int, spend_cap: float, coach_points: float):
    """Replace at most `changes` players from the saved squad."""
    by_id = {player["player_id"]: player for player in records}
    held = [by_id[player_id] for player_id in held_ids if player_id in by_id]
    if not held:
        return ("message", "None of the saved players have a price and a projection.")
    kept = list(held)
    forced = 0
    for position, limit in ROSTER.items():
        group = sorted(
            (player for player in kept if player["position_group"] == position),
            key=lambda player: player["projected"],
        )
        overflow = len(group) - limit
        if overflow > 0:
            drop_ids = {player["player_id"] for player in group[:overflow]}
            kept = [player for player in kept if player["player_id"] not in drop_ids]
            forced += overflow
    if forced > changes:
        return (
            "message",
            f"My team needs {forced} changes before it matches 4 guards, 4 forwards, and 2 centers.",
        )
    optional = changes - forced
    vacancies = 10 - len(kept)
    if vacancies > optional:
        return (
            "message",
            f"My team has {len(kept)} priced players. Reaching 10 takes {vacancies} changes, and {changes} {'is' if changes == 1 else 'are'} allowed.",
        )
    extra_swaps = optional - vacancies
    kept_ids = {player["player_id"] for player in kept}
    pool = [player for player in records if player["player_id"] not in kept_ids]
    ranked = []
    for drop_count in range(extra_swaps + 1):
        for dropped in combinations(kept, drop_count):
            dropped_ids = {player["player_id"] for player in dropped}
            remain = [player for player in kept if player["player_id"] not in dropped_ids]
            need = {
                position: ROSTER[position] - sum(player["position_group"] == position for player in remain)
                for position in ROSTER
            }
            if any(count < 0 for count in need.values()):
                continue
            spent = sum(player["price"] for player in remain)
            if spent > spend_cap + 1e-6:
                continue
            adds = _best_adds(pool, need, spend_cap - spent, _team_counts(remain))
            for added in adds:
                squad = remain + added
                if len(squad) != 10 or not _cap_ok(_team_counts(squad)):
                    continue
                if sum(player["price"] for player in squad) > spend_cap + 1e-6:
                    continue
                ranked.append((sum(player["projected"] for player in squad), squad, {player["player_id"] for player in remain}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    best = None
    seen = set()
    for _raw, squad, remain_ids in ranked[:40]:
        key = tuple(sorted(player["player_id"] for player in squad))
        if key in seen:
            continue
        seen.add(key)
        slotted = _best_slots(squad, coach_points)
        if slotted is None:
            continue
        total, starters, sixth, bench = slotted
        if best is None or total > best[0]:
            best = (total, starters, sixth, bench, remain_ids)
    if best is None:
        return ("message", "No squad fits the budget within that many changes.")
    return ("squad",) + best


def build_best_team(
    projections: pd.DataFrame,
    coaches: pd.DataFrame,
    coach_price: float = 0.0,
    day: pd.Timestamp | None = None,
    budget: float = 100.0,
    horizon: int = 1,
    changes: int = 10,
    held_ids: list[str] | None = None,
    coach_id: str | None = None,
) -> dict:
    """Pick 4 guards, 4 forwards, 2 centers and the best coach for one slate."""
    horizon = max(int(horizon or 1), 1)
    projections, coaches = _apply_horizon(projections, coaches, horizon)
    if horizon > 1:
        day = None
    coach_frame = coaches
    if day is not None and coaches is not None and not coaches.empty and "game_date" in coaches.columns:
        local = pd.to_datetime(coaches["game_date"], utc=True, errors="coerce").dt.tz_convert("Europe/Athens")
        coach_frame = coaches[local.dt.normalize() == day]
    coach = None
    coach_points = 0.0
    chosen = None
    if coach_id and coaches is not None and not coaches.empty:
        match = coaches[coaches["coach_id"].astype(str) == str(coach_id)]
        if not match.empty:
            chosen = match.iloc[0]
    if chosen is None and coach_frame is not None and not coach_frame.empty and coach_frame["projected"].notna().any():
        chosen = coach_frame.sort_values("projected", ascending=False).iloc[0]
    if chosen is not None and not pd.isna(chosen.projected):
        coach = chosen
        coach_points = float(chosen.projected)
    spend_cap = budget - max(float(coach_price or 0), 0.0)
    if projections is None or projections.empty or "price" not in projections.columns:
        return _empty_result(
            coach,
            coach_points,
            coach_price,
            day,
            "Published prices are not loaded, so a squad cannot be built.",
        )
    records = _records(projections, day)
    held = [str(player_id) for player_id in (held_ids or [])]
    use_changes = bool(held) and int(changes) < 10
    if use_changes:
        outcome = _search_changes(records, held, int(changes), spend_cap, coach_points)
        if outcome[0] == "message":
            return _empty_result(coach, coach_points, coach_price, day, outcome[1], horizon)
        _kind, _total, starters, sixth, bench, remain_ids = outcome
        starters, sixth, bench = _mark_kept(starters, sixth, bench, set(held))
        starters, sixth, bench = _tidy_slots(starters, sixth, bench)
        result = _present(
            {"starters": starters, "sixth": sixth, "bench": bench, "total": _score(starters, sixth, bench, coach_points)},
            coach,
            coach_points,
            coach_price,
            day,
            horizon,
        )
        chosen = [player["player_id"] for player in starters + [sixth] + bench]
        result["changes_used"] = sum(1 for player_id in chosen if player_id not in set(held))
        return result
    by_position = {position: [player for player in records if player["position_group"] == position] for position in ROSTER}
    if spend_cap <= 0 or any(len(by_position[position]) < ROSTER[position] for position in ROSTER):
        return _empty_result(coach, coach_points, coach_price, day, "Not enough priced players on this slate.")

    cheapest_by_pos = {}
    upgrades_by_pos = {}
    starter_pool = {}
    improve_pool = []
    for position, players in by_position.items():
        cheapest_by_pos[position] = sorted(players, key=lambda player: (player["price"], -player["projected"]))
        starter_pool[position] = players[: STARTER_DEPTH[position]]
        upgrades_by_pos[position] = players
        improve_pool.extend(players[:25])
        improve_pool.extend(_value_pool([player for player in players if _plays(player)], 15))
        improve_pool.extend(cheapest_by_pos[position][:8])

    best = _search_formations(starter_pool, cheapest_by_pos, upgrades_by_pos, spend_cap, coach_points)
    if best is None:
        value_pool = {
            position: _value_pool(players, STARTER_DEPTH[position]) for position, players in by_position.items()
        }
        best = _search_formations(value_pool, cheapest_by_pos, upgrades_by_pos, spend_cap, coach_points)
    if best is None:
        best = _search_formations(
            starter_pool, cheapest_by_pos, upgrades_by_pos, spend_cap, coach_points, formations=FORMATIONS
        )
    if best is None:
        return _empty_result(coach, coach_points, coach_price, day, "No squad fits the budget and roster rules on this slate.")
    _total, starters, sixth, bench = best
    starters, sixth, bench = _improve(starters, sixth, bench, improve_pool, spend_cap, coach_points)
    starters, sixth, bench = _tidy_slots(starters, sixth, bench)
    if held:
        starters, sixth, bench = _mark_kept(starters, sixth, bench, set(held))
    result = _present(
        {"starters": starters, "sixth": sixth, "bench": bench, "total": _score(starters, sixth, bench, coach_points)},
        coach,
        coach_points,
        coach_price,
        day,
        horizon,
    )
    if held:
        chosen = [player["player_id"] for player in starters + [sixth] + bench]
        result["changes_used"] = sum(1 for player_id in chosen if player_id not in set(held))
    return result


def _tidy_slots(starters: list[dict], sixth: dict, bench: list[dict]):
    """Prefer a higher projection in the starting five when the formation still fits."""
    rest = [sixth] + list(bench)
    while True:
        weakest = min(starters, key=lambda player: player["projected"])
        best_rest = max(rest, key=lambda player: player["projected"])
        if best_rest["projected"] <= weakest["projected"] + 1e-9:
            break
        trial = [best_rest if player is weakest else player for player in starters]
        shape = tuple(sum(player["position_group"] == position for player in trial) for position in ("G", "F", "C"))
        if shape not in BACKUP_FORMATIONS:
            break
        trial_rest = [weakest if player is best_rest else player for player in rest]
        if not _backup_center(trial, trial_rest):
            break
        rest = [weakest if player is best_rest else player for player in rest]
        starters = trial
    sixth = max(rest, key=lambda player: player["projected"])
    bench = [player for player in rest if player is not sixth]
    return starters, sixth, bench


def _mark_kept(starters, sixth, bench, held_ids: set[str]):
    def tag(player):
        tagged = dict(player)
        tagged["kept"] = player["player_id"] in held_ids
        return tagged

    return [tag(player) for player in starters], tag(sixth), [tag(player) for player in bench]


def _present(best: dict, coach, coach_points: float, coach_price: float, day, horizon: int = 1) -> dict:
    captain = max(best["starters"], key=lambda player: player["projected"])
    rows = []
    for player in best["starters"]:
        slot = "Captain" if player is captain else "Starter"
        multiplier = 2.0 if slot == "Captain" else 1.0
        rows.append(_line(player, slot, multiplier))
    rows.append(_line(best["sixth"], "Sixth", 1.0))
    for player in best["bench"]:
        rows.append(_line(player, "Bench", 0.5))
    frame = pd.DataFrame(rows)
    frame["_order"] = frame["slot"].map(SLOT_ORDER)
    frame = frame.sort_values(["_order", "counted"], ascending=[True, False]).drop(columns="_order")
    price_sum = float(frame["price"].sum()) + max(coach_price, 0.0)
    return {
        "players": frame.reset_index(drop=True),
        "coach_name": None if coach is None else coach.coach_name,
        "coach_id": None if coach is None else coach.coach_id,
        "coach_team": None if coach is None else coach.team_name,
        "coach_opponent": None if coach is None else coach.opponent_name,
        "coach_home_away": None if coach is None else coach.home_away,
        "coach_points": coach_points,
        "coach_price": coach_price,
        "total": best["total"],
        "price_sum": price_sum,
        "day": day,
        "horizon": horizon,
        "changes_used": None,
        "message": "",
    }


def _line(player: dict, slot: str, multiplier: float) -> dict:
    return {
        "slot": slot,
        "player_id": player["player_id"],
        "player_name": player["player_name"],
        "team_name": player["team_name"],
        "position_group": player["position_group"],
        "opponent_name": player["opponent_name"],
        "home_away": player["home_away"],
        "expected_minutes": player.get("expected_minutes"),
        "tip_day": "" if player.get("game_day") is None else pd.Timestamp(player["game_day"]).strftime("%a"),
        "price": player["price"],
        "projected": player["projected"],
        "points_per_credit": player["points_per_credit"],
        "counted": player["projected"] * multiplier,
        "move": None if "kept" not in player else ("Keep" if player["kept"] else "New"),
        "availability": player.get("availability") or "available",
        "status_label": player.get("status_label") or "Available",
        "injury_note": player.get("injury_note") or "",
    }


def _empty_result(coach, coach_points: float, coach_price: float, day, message: str, horizon: int = 1) -> dict:
    return {
        "players": pd.DataFrame(),
        "coach_name": None if coach is None else coach.coach_name,
        "coach_id": None if coach is None else coach.coach_id,
        "coach_team": None if coach is None else coach.team_name,
        "coach_opponent": None if coach is None else coach.opponent_name,
        "coach_home_away": None if coach is None else coach.home_away,
        "coach_points": coach_points,
        "coach_price": coach_price,
        "total": coach_points,
        "price_sum": coach_price,
        "day": day,
        "horizon": horizon,
        "changes_used": None,
        "message": message,
    }

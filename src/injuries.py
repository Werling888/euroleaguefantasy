"""EuroLeague injury report from the public BasketNews list."""

from __future__ import annotations

import time
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests

from src.prices import _firsts_match, name_tokens, teams_overlap

INJURY_PAGE = "https://basketnews.com/leagues/25-euroleague/injured.html"
MAX_AGE_SECONDS = 6 * 60 * 60

# Ready is confirmed. Anything else on the report is not a verified starter.
KNOWN_LABELS = {
    "Ready": "available",
    "Expected": "uncertain",
    "Questionable": "uncertain",
    "Game-time": "uncertain",
    "Doubtful": "uncertain",
    "Uncertain": "uncertain",
    "Out": "out",
}


class _InjuryPage(HTMLParser):
    """Walk the injury table. Team rows set the club; player rows follow."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self._team = ""
        self._in_tr = False
        self._is_team = False
        self._cells: list[str] = []
        self._in_td = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self._in_tr = True
            classes = attributes.get("class") or ""
            self._is_team = "injury_reports__team-row" in classes
            self._cells = []
        elif self._in_tr and tag == "td":
            self._in_td = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if not self._in_td:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_td:
            self._cells.append(" ".join(self._parts).strip())
            self._in_td = False
            return
        if tag != "tr" or not self._in_tr:
            return
        if self._is_team and self._cells:
            self._team = self._cells[0]
        elif self._team and len(self._cells) >= 3:
            status = self._cells[2]
            player = self._cells[1]
            if status in KNOWN_LABELS and player:
                self.rows.append(
                    {
                        "source_name": player,
                        "source_team": self._team,
                        "status_label": status,
                        "availability": KNOWN_LABELS[status],
                        "injury_note": self._cells[4] if len(self._cells) > 4 else "",
                        "round_label": self._cells[3] if len(self._cells) > 3 else "",
                    }
                )
        self._in_tr = False


def fetch_injuries() -> pd.DataFrame:
    """Download the current EuroLeague injury report."""
    response = requests.get(
        INJURY_PAGE,
        timeout=30,
        headers={"User-Agent": "euroleague-fantasy-dashboard/0.1"},
    )
    response.raise_for_status()
    parser = _InjuryPage()
    parser.feed(response.text)
    if not parser.rows:
        raise RuntimeError("Injury report did not include any players")
    return pd.DataFrame(parser.rows)


def injury_cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "injuries.parquet"


def ensure_injuries(root: Path, force: bool = False) -> pd.DataFrame:
    """Return the cached injury report, refreshing when the file is old or missing."""
    path = injury_cache_path(root)
    fresh = path.exists() and not force
    if fresh:
        fresh = (time.time() - path.stat().st_mtime) < MAX_AGE_SECONDS
    if fresh:
        return pd.read_parquet(path)
    try:
        frame = fetch_injuries()
    except Exception:
        if path.exists():
            return pd.read_parquet(path)
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame


SAME_POS_SHARE = 0.60
OTHER_POS_SHARE = 0.40
MINUTE_CAP = 38.0


def eligible_to_play(availability: str | None) -> bool:
    """True only when the player is confirmed available."""
    return (availability or "available") == "available"


def _as_games(value) -> int:
    if value is None or pd.isna(value):
        return 0
    return int(value)


def _as_minutes(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _role_weight(minutes: float) -> float:
    return max(minutes, 1.0)


def _give_minutes(
    share: float,
    indexes: list[int],
    extras: dict[int, float],
    base: dict[int, float],
) -> float:
    """Split share among teammates who still have room under the minute cap."""
    leftover = share
    while leftover > 1e-9:
        open_slots = []
        weights = []
        for idx in indexes:
            room = MINUTE_CAP - (base[idx] + extras[idx])
            if room <= 1e-9:
                continue
            open_slots.append((idx, room))
            weights.append(_role_weight(base[idx]))
        if not open_slots:
            return leftover
        total = sum(weights)
        next_leftover = 0.0
        moved = False
        for (idx, room), weight in zip(open_slots, weights):
            piece = leftover * (weight / total)
            take = min(piece, room)
            extras[idx] += take
            next_leftover += piece - take
            if take > 1e-12:
                moved = True
        leftover = next_leftover
        if not moved:
            break
    return leftover


def _take_minutes(
    share: float,
    indexes: list[int],
    extras: dict[int, float],
    base: dict[int, float],
) -> float:
    """Take share back from teammates, not below zero minutes."""
    leftover = share
    while leftover > 1e-9:
        open_slots = []
        weights = []
        for idx in indexes:
            current = base[idx] + extras[idx]
            if current <= 1e-9:
                continue
            open_slots.append((idx, current))
            weights.append(_role_weight(base[idx]))
        if not open_slots:
            return leftover
        total = sum(weights)
        next_leftover = 0.0
        moved = False
        for (idx, current), weight in zip(open_slots, weights):
            piece = leftover * (weight / total)
            take = min(piece, current)
            extras[idx] -= take
            next_leftover += piece - take
            if take > 1e-12:
                moved = True
        leftover = next_leftover
        if not moved:
            break
    return leftover


def _split_by_position(
    share: float,
    position: str,
    available: list[tuple[int, str]],
    extras: dict[int, float],
    base: dict[int, float],
    give: bool,
) -> None:
    same = [idx for idx, pos in available if pos == position]
    other = [idx for idx, pos in available if pos != position]
    same_share = share * SAME_POS_SHARE
    other_share = share * OTHER_POS_SHARE
    if not same:
        other_share += same_share
        same_share = 0.0
    if not other:
        same_share += other_share
        other_share = 0.0
    move = _give_minutes if give else _take_minutes
    move(same_share, same, extras, base)
    move(other_share, other, extras, base)


def apply_injury_minutes(players: pd.DataFrame) -> pd.DataFrame:
    """Move minutes when someone is newly out, and put them back when he returns.

    A listed Out or unconfirmed player with as many current-season games as the
    club donates expected minutes (60% same position). If he already missed
    games, teammate averages already include that time, so nothing is added.

    When he is Available again with fewer games than the club, that extra is
    still in teammate averages. Take it back in the same 60/40 split, scaled by
    the share of club games he missed.
    """
    frame = players.copy()
    frame["injury_boost_min"] = 0.0
    if frame.empty or "availability" not in frame.columns:
        return frame
    extras = {int(idx): 0.0 for idx in frame.index}
    for _, club in frame.groupby("team_code", dropna=False):
        base: dict[int, float] = {}
        donors: list[tuple[int, str, float, int]] = []
        available: list[tuple[int, str]] = []
        available_games: dict[int, int] = {}
        club_games = 0
        for row in club.itertuples():
            minutes = _as_minutes(getattr(row, "expected_minutes", None))
            if minutes is None:
                continue
            idx = int(row.Index)
            position = str(getattr(row, "position_group", "") or "")
            status = getattr(row, "availability", "available") or "available"
            games = _as_games(getattr(row, "gp_current", 0))
            if status == "available":
                base[idx] = minutes
                available.append((idx, position))
                available_games[idx] = games
                if games > club_games:
                    club_games = games
            else:
                donors.append((idx, position, minutes, games))
        if not available:
            continue
        for _, position, vacated, games in donors:
            if games < club_games:
                continue
            _split_by_position(vacated, position, available, extras, base, give=True)
        if club_games <= 0:
            continue
        for idx, position in available:
            games = available_games[idx]
            if games >= club_games:
                continue
            missed = (club_games - games) / club_games
            vacated = base[idx] * missed
            others = [(other, pos) for other, pos in available if other != idx]
            if not others or vacated <= 1e-9:
                continue
            _split_by_position(vacated, position, others, extras, base, give=False)
    boosts = []
    expected = []
    projected = []
    floors = []
    ceilings = []
    schedules = []
    has_schedule = "schedule" in frame.columns
    for idx, row in frame.iterrows():
        extra = extras.get(int(idx), 0.0)
        boosts.append(extra)
        old_min = _as_minutes(row.get("expected_minutes"))
        if old_min is None:
            expected.append(row.get("expected_minutes"))
            projected.append(row.get("projected"))
            floors.append(row.get("floor"))
            ceilings.append(row.get("ceiling"))
            if has_schedule:
                schedules.append(row.get("schedule"))
            continue
        new_min = min(MINUTE_CAP, max(0.0, old_min + extra))
        expected.append(new_min)
        ratio = new_min / old_min if old_min > 0 else 1.0

        def _scale(value):
            if value is None or pd.isna(value):
                return value
            return float(value) * ratio

        projected.append(_scale(row.get("projected")))
        floors.append(_scale(row.get("floor")))
        ceilings.append(_scale(row.get("ceiling")))
        if has_schedule:
            games = row.get("schedule")
            if isinstance(games, list):
                scaled = []
                for game in games:
                    if not isinstance(game, dict):
                        scaled.append(game)
                        continue
                    copy = dict(game)
                    copy["projected"] = _scale(copy.get("projected"))
                    scaled.append(copy)
                schedules.append(scaled)
            else:
                schedules.append(games)
    frame["injury_boost_min"] = boosts
    frame["expected_minutes"] = expected
    frame["projected"] = projected
    frame["floor"] = floors
    frame["ceiling"] = ceilings
    if has_schedule:
        frame["schedule"] = schedules
    from src.squad import fill_points_per_credit

    return fill_points_per_credit(frame)


def _candidate_indexes(injuries: pd.DataFrame) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for row_index, row in injuries.iterrows():
        tokens = name_tokens(row.source_name)
        if len(tokens) < 2:
            continue
        surnames = {tokens[-1]}
        if len(tokens) >= 3:
            surnames.add(tokens[-2])
        for surname in surnames:
            index.setdefault(surname, []).append(int(row_index))
    return index


def _match_row(player_name: str, team_name: str, injuries: pd.DataFrame, index: dict[str, list[int]]):
    tokens = name_tokens(player_name)
    if len(tokens) < 2:
        return None
    surnames = {tokens[-1]}
    if len(tokens) >= 3:
        surnames.add(tokens[-2])
    candidate_ids = []
    for surname in surnames:
        candidate_ids.extend(index.get(surname, []))
    if not candidate_ids:
        return None
    candidates = injuries.loc[list(dict.fromkeys(candidate_ids))]
    first = tokens[0]

    def _first_matches(source: str) -> bool:
        source_tokens = name_tokens(source)
        return bool(source_tokens) and _firsts_match(first, source_tokens[0])

    candidates = candidates[candidates["source_name"].map(_first_matches)]
    if candidates.empty:
        return None
    if len(candidates) > 1:
        same_team = candidates[
            candidates["source_team"].map(lambda team: teams_overlap(team_name, team))
        ]
        if len(same_team) == 1:
            return same_team.iloc[0]
        if len(same_team) > 1:
            candidates = same_team
        else:
            return None
    if len(candidates) != 1:
        return None
    return candidates.iloc[0]


def assign_availability(players: pd.DataFrame, injuries: pd.DataFrame | None) -> pd.DataFrame:
    """Attach availability, status, and the injury note. Unlisted players are available."""
    frame = players.copy()
    frame["availability"] = "available"
    frame["status_label"] = "Available"
    frame["injury_note"] = ""
    if injuries is None or injuries.empty or frame.empty:
        return frame
    index = _candidate_indexes(injuries)
    availability = []
    labels = []
    notes = []
    for player in frame.itertuples(index=False):
        chosen = _match_row(player.player_name, player.team_name, injuries, index)
        if chosen is None or chosen.availability == "available":
            availability.append("available")
            labels.append("Available")
            notes.append("")
            continue
        note = str(chosen.injury_note or "").strip()
        round_label = str(chosen.round_label or "").strip()
        if round_label and note:
            note = f"{round_label}. {note}"
        elif round_label:
            note = round_label
        availability.append(str(chosen.availability))
        labels.append(str(chosen.status_label))
        notes.append(note)
    frame["availability"] = availability
    frame["status_label"] = labels
    frame["injury_note"] = notes
    return frame

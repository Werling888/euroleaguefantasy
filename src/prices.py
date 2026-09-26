"""Fantasy Challenge credit prices from the public 2026/27 player list."""

from __future__ import annotations

import html
import json
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

PRICE_PAGE = "https://givemestats.com/euroleague/fantasy-basketball-risers/2026"
MAX_AGE_SECONDS = 6 * 60 * 60

# First-name spellings that refer to the same player across the two feeds.
FIRST_NAME_ALIASES = {
    "nathan": "nate",
    "nate": "nate",
    "daniel": "dan",
    "dan": "dan",
    "danny": "dan",
    "nikolaos": "nikos",
    "nikos": "nikos",
    "nicholas": "nick",
    "nick": "nick",
    "georgios": "giorgos",
    "giorgos": "giorgos",
    "yorgos": "giorgos",
    "olek": "aleksander",
    "aleksander": "aleksander",
    "alexander": "aleksander",
    "alex": "aleksander",
    "panagiotis": "panos",
    "panos": "panos",
    "ioannis": "giannis",
    "giannis": "giannis",
    "dimitrios": "dimitris",
    "dimitris": "dimitris",
    "konstantinos": "kostas",
    "kostas": "kostas",
    "vasileios": "vasilis",
    "vasilis": "vasilis",
    "antonios": "antonis",
    "antonis": "antonis",
    "eleftherios": "lefteris",
    "lefteris": "lefteris",
    "maksym": "max",
    "max": "max",
    "omiros": "omer",
    "omer": "omer",
    "alvaro": "alvaro",
    "william": "will",
    "will": "will",
}

# Surname spellings that refer to the same player across the two feeds.
SURNAME_ALIASES = {
    "lavi": "lavi",
    "lavy": "lavi",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character))


@lru_cache(maxsize=None)
def name_tokens(value: str) -> tuple[str, ...]:
    text = _strip_accents(value).lower().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in {"jr", "sr", "ii", "iii", "iv"}]
    if len(tokens) >= 2 and len(tokens[-1]) == 1 and len(tokens[-2]) > 1:
        tokens = tokens[:-1]
    lead = []
    rest = []
    for token in tokens:
        if not rest and len(token) == 1:
            lead.append(token)
        else:
            rest.append(token)
    if lead and rest:
        tokens = ["".join(lead), *rest]
    if len(tokens) >= 3:
        tokens = [tokens[0], *[token for token in tokens[1:-1] if len(token) > 1], tokens[-1]]
    return tuple(SURNAME_ALIASES.get(token, token) for token in tokens)


def _firsts_match(left: str, right: str) -> bool:
    canonical_left = _first_key(left)
    canonical_right = _first_key(right)
    if canonical_left == canonical_right:
        return True
    short, long = sorted((canonical_left, canonical_right), key=len)
    return len(short) >= 3 and long.startswith(short)


def _first_key(token: str) -> str:
    return FIRST_NAME_ALIASES.get(token, token)


def team_tokens(value: str) -> set[str]:
    skip = {"bc", "fc", "bk", "sk", "acb", "the", "de"}
    return {token for token in name_tokens(value) if token not in skip}


def teams_overlap(left: str, right: str) -> bool:
    return bool(team_tokens(left) & team_tokens(right))


def fetch_fantasy_prices() -> pd.DataFrame:
    """Download the current Fantasy Challenge credit for each Euroleague player."""
    response = requests.get(
        PRICE_PAGE,
        timeout=30,
        headers={"User-Agent": "euroleague-fantasy-dashboard/0.1"},
    )
    response.raise_for_status()
    match = re.search(r'data-page="([^"]+)"', response.text)
    if not match:
        raise RuntimeError("Fantasy price page did not include a player list")
    payload = json.loads(html.unescape(match.group(1)))
    rows = []
    for item in payload["props"]["fantasyStats"]:
        if item.get("position") not in {"G", "F", "C"}:
            continue
        price = item.get("price")
        if price in (None, ""):
            continue
        change = item.get("priceChange")
        try:
            change_value = None if change in (None, "") else float(change)
        except (TypeError, ValueError):
            change_value = None
        rows.append(
            {
                "source_name": item.get("player") or "",
                "source_team": item.get("shortTeamTitle") or item.get("team") or "",
                "position_group": item["position"],
                "price": float(price),
                "price_change": change_value,
            }
        )
    if not rows:
        raise RuntimeError("Fantasy price page returned no prices")
    return pd.DataFrame(rows)


def price_cache_path(root: Path) -> Path:
    return root / "data" / "cache" / "fantasy_prices.parquet"


def price_meta_path(root: Path) -> Path:
    return root / "data" / "cache" / "fantasy_prices_meta.json"


def load_price_meta(root: Path) -> dict:
    path = price_meta_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_meta(root: Path, source: str, extra: dict | None = None) -> None:
    payload = {"source": source, "fetched_at": time.time()}
    if extra:
        payload.update(extra)
    path = price_meta_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_prices(root: Path, force: bool = False) -> pd.DataFrame:
    """Return cached prices, preferring the official logged-in list when configured."""
    path = price_cache_path(root)
    fresh = path.exists() and not force
    if fresh:
        fresh = (time.time() - path.stat().st_mtime) < MAX_AGE_SECONDS
    if fresh:
        return pd.read_parquet(path)

    frame = None
    source = "public"
    official_error = None
    from src.credentials import fantasy_login

    if fantasy_login(root):
        try:
            from src.official import fetch_official_prices

            frame = fetch_official_prices(root)
            source = "official"
        except Exception as exc:
            official_error = str(exc)
            frame = None
    if frame is None:
        try:
            frame = fetch_fantasy_prices()
            source = "public"
        except Exception:
            if path.exists():
                return pd.read_parquet(path)
            raise
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    extra = {"players": int(len(frame))}
    if official_error:
        extra["official_error"] = official_error
    _write_meta(root, source, extra)
    return frame


def _candidate_indexes(prices: pd.DataFrame) -> dict[str, list[int]]:
    """Index price rows by every plausible surname token."""
    index: dict[str, list[int]] = {}
    for row_index, row in prices.iterrows():
        tokens = name_tokens(row.source_name)
        if len(tokens) < 2:
            continue
        surnames = {tokens[-1]}
        if len(tokens) >= 3:
            surnames.add(tokens[-2])
        for surname in surnames:
            index.setdefault(surname, []).append(int(row_index))
    return index


def _chosen_list_row(name: str, team_name: str, prices: pd.DataFrame, index: dict[str, list[int]]):
    """Match one EuroLeague name to a Fantasy Challenge list row."""
    tokens = name_tokens(name)
    if len(tokens) < 2:
        return None
    surnames = {tokens[-1]}
    if len(tokens) >= 3:
        surnames.add(tokens[-2])
    candidate_ids = []
    for surname in surnames:
        candidate_ids.extend(index.get(surname, []))
    candidates = prices.loc[list(dict.fromkeys(candidate_ids))]
    if candidates.empty:
        return None
    first = tokens[0]

    def _first_matches(source: str) -> bool:
        source_tokens = name_tokens(source)
        return bool(source_tokens) and _firsts_match(first, source_tokens[0])

    candidates = candidates[candidates["source_name"].map(_first_matches)]
    if len(candidates) == 1:
        return candidates.iloc[0]
    if len(candidates) > 1:
        same_team = candidates[
            candidates["source_team"].map(lambda team: teams_overlap(team_name, team))
        ]
        pool = same_team if not same_team.empty else candidates
        if len(pool) == 1 or pool["price"].nunique() == 1:
            return pool.iloc[0]
    return None


def assign_prices(players: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Attach a published credit price and points per credit to each player."""
    frame = players.copy()
    frame["price"] = pd.NA
    if prices is None or prices.empty:
        frame["points_per_credit"] = pd.NA
        return frame
    index = _candidate_indexes(prices)
    assigned = []
    for player in frame.itertuples(index=False):
        chosen = _chosen_list_row(player.player_name, player.team_name, prices, index)
        assigned.append(None if chosen is None else float(chosen.price))
    frame["price"] = assigned
    from src.squad import fill_points_per_credit

    return fill_points_per_credit(frame)


def apply_fantasy_positions(players: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Use Fantasy Challenge G/F/C from the official/public list, not EuroLeague Center/Forward."""
    if players is None or players.empty or prices is None or prices.empty:
        return players
    if "position_group" not in prices.columns:
        return players
    name_col = "person_name" if "person_name" in players.columns else "player_name"
    team_col = "team_name"
    frame = players.copy()
    index = _candidate_indexes(prices)
    mapped = []
    for row in frame.itertuples(index=False):
        chosen = _chosen_list_row(getattr(row, name_col), getattr(row, team_col), prices, index)
        if chosen is not None:
            slot = chosen["position_group"] if "position_group" in chosen.index else None
            if slot in {"G", "F", "C"}:
                mapped.append(slot)
                continue
        mapped.append(getattr(row, "position_group", None))
    frame["position_group"] = mapped
    return frame


def apply_fantasy_positions_to_logs(logs: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Tag box scores with the same Fantasy Challenge slot as the roster row."""
    if logs is None or logs.empty or players is None or players.empty:
        return logs
    if "person_id" not in players.columns or "player_id" not in logs.columns:
        return logs
    lookup = dict(zip(players["person_id"].astype(str), players["position_group"]))
    frame = logs.copy()
    mapped = frame["player_id"].astype(str).map(lookup)
    keep = mapped.isin(["G", "F", "C"])
    frame.loc[keep, "position_group"] = mapped[keep]
    return frame

"""Official Fantasy Challenge credits via a local logged-in session."""

from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path

import pandas as pd
import requests

from src.credentials import fantasy_login

FANTAKING = "https://fantaking-api.dunkest.com/api/v1"
FANSCORE_TOKEN = "https://oauth.fanscore.com/oauth/token"
ORIGIN = "https://euroleaguefantasy.euroleaguebasketball.net"
FAN_ORIGIN = "https://www.euroleaguebasketball.net"
# Fantaking game 7 is EuroLeague + EuroCup. Game 10 is SLGR, not Fantasy Challenge.
GAME_ID = 7
LEAGUE_ID = 10
CLIENT_ID = "EUROLEAGUE"
PROVIDER_NAME = "euroleague"
POSITIONS = {
    "g": "G",
    "pg": "G",
    "sg": "G",
    "guard": "G",
    "guards": "G",
    "f": "F",
    "sf": "F",
    "pf": "F",
    "forward": "F",
    "forwards": "F",
    "c": "C",
    "center": "C",
    "centres": "C",
    "centers": "C",
}


def session_path(root: Path) -> Path:
    return root / "data" / "fantasy_session.json"


def price_meta_path(root: Path) -> Path:
    return root / "data" / "cache" / "fantasy_prices_meta.json"


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Origin": ORIGIN,
        "Referer": ORIGIN + "/",
        "User-Agent": "euroleague-fantasy-dashboard/0.1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _jwt_payload(token: str) -> dict:
    part = token.split(".")[1]
    padded = part + "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def _extract_token(payload: dict) -> str | None:
    token = payload.get("token") or (payload.get("data") or {}).get("token")
    user = payload.get("user")
    if not token and isinstance(user, dict):
        token = user.get("token")
    nested = payload.get("data")
    if not token and isinstance(nested, dict) and isinstance(nested.get("user"), dict):
        token = nested["user"].get("token")
    return str(token) if token else None


def _api_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict) and payload.get("message"):
        return str(payload["message"])
    return response.text[:200]


def _fan_id_token(email: str, password: str, device_id: str) -> tuple[str, dict]:
    """EuroLeague Fan ID access token from Fanscore (same login as the official site)."""
    response = requests.post(
        FANSCORE_TOKEN,
        data={
            "username": email,
            "password": password,
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "device_id": device_id,
        },
        timeout=30,
        headers={
            "Accept": "application/json",
            "Origin": FAN_ORIGIN,
            "Referer": FAN_ORIGIN + "/en/login/",
            "User-Agent": "euroleague-fantasy-dashboard/0.1",
        },
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if response.status_code >= 400 or not token:
        raise RuntimeError(
            f"EuroLeague Fan ID login failed ({_api_message(response)}). "
            "Use the email and password from euroleaguebasketball.net, then Refresh data."
        )
    claims = {}
    try:
        claims = _jwt_payload(str(token))
    except Exception:
        claims = {}
    return str(token), claims if isinstance(claims, dict) else {}


def _social_payload(email: str, provider_id: str, provider_token: str, claims: dict) -> dict:
    return {
        "provider_id": provider_id,
        "provider_name": PROVIDER_NAME,
        "provider_token": provider_token,
        "email": email,
        "game_id": GAME_ID,
        "first_name": str(claims.get("first_name") or "Fan"),
        "last_name": str(claims.get("last_name") or "User"),
        "language": "en",
        "country": "GB",
    }


def _fantaking_login(email: str, password: str, device_id: str) -> str:
    provider_token, claims = _fan_id_token(email, password, device_id)
    provider_id = str(claims.get("sub") or "")
    if not provider_id:
        raise RuntimeError("EuroLeague Fan ID token did not include a user id.")
    body = _social_payload(email, provider_id, provider_token, claims)
    headers = _headers()
    response = requests.post(f"{FANTAKING}/social/login", json=body, timeout=30, headers=headers)
    if response.status_code >= 400:
        response = requests.post(f"{FANTAKING}/social/register", json=body, timeout=30, headers=headers)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or not isinstance(payload, dict):
        raise RuntimeError(
            f"Fantasy Challenge login failed ({_api_message(response)}). "
            "Finish Login to play once on euroleaguefantasy.euroleaguebasketball.net, then Refresh data."
        )
    token = _extract_token(payload)
    if not token:
        raise RuntimeError("Fantasy API login did not return a session token.")
    return token


def _load_session(root: Path) -> dict:
    path = session_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_session(root: Path, payload: dict) -> None:
    path = session_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _api_token(root: Path) -> str:
    login = fantasy_login(root)
    if login is None:
        raise RuntimeError("Add FANTASY_EMAIL and FANTASY_PASSWORD in data/fantasy_credentials.properties")
    email, password = login
    stored = _load_session(root)
    now = time.time()
    api_token = stored.get("api_token")
    expires = float(stored.get("expires_at") or 0)
    if api_token and stored.get("email") == email and expires > now + 60:
        return str(api_token)
    device_id = str(stored.get("device_id") or uuid.uuid4())
    api_token = _fantaking_login(email, password, device_id)
    _save_session(
        root,
        {
            "api_token": api_token,
            "expires_at": now + 50 * 60,
            "email": email,
            "device_id": device_id,
        },
    )
    return api_token


def _unwrap(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "players", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("data"), list):
            return value["data"]
    return []


def _position_group(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("abbreviation", "short_name", "name", "code"):
            mapped = _position_group(value.get(key))
            if mapped:
                return mapped
        return None
    text = str(value).strip().lower()
    return POSITIONS.get(text)


def _team_name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("abbreviation") or value.get("short_name") or "")
    return str(value or "")


def _pick(payload: dict, *keys):
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
        nested = payload.get("data")
        if isinstance(nested, dict) and nested.get(key) not in (None, ""):
            return nested[key]
    return None


def _league_ids(token: str) -> tuple[int, int]:
    config = requests.get(
        f"{FANTAKING}/leagues/{LEAGUE_ID}/config",
        timeout=30,
        headers=_headers(token),
    )
    payload = config.json() if config.ok else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    list_id = _pick(data, "current_players_list_id")
    matchday = _pick(data, "current_matchday")
    matchday_id = None
    if isinstance(matchday, dict):
        matchday_id = matchday.get("id")
    elif matchday not in (None, ""):
        matchday_id = matchday
    if list_id in (None, "") or matchday_id in (None, ""):
        user = requests.get(f"{FANTAKING}/user/config", params={"game": GAME_ID}, timeout=30, headers=_headers(token))
        extra = user.json() if user.ok else {}
        extra = extra.get("data") if isinstance(extra.get("data"), dict) else extra
        list_id = list_id or _pick(extra, "current_players_list_id", "default_league_id")
        matchday = matchday or _pick(extra, "current_matchday")
        if isinstance(matchday, dict):
            matchday_id = matchday.get("id")
        elif matchday not in (None, ""):
            matchday_id = matchday
    if list_id in (None, "") or matchday_id in (None, ""):
        raise RuntimeError("Logged in, but the current Fantasy round list was not in the API response.")
    return int(list_id), int(matchday_id)


def _fetch_players(token: str, list_id: int, matchday_id: int) -> list[dict]:
    rows = []
    page = 1
    while page <= 20:
        response = requests.get(
            f"{FANTAKING}/players-lists/{list_id}/matchdays/{matchday_id}/players",
            params={"per_page": 100, "page": page, "sort_by": "quotation", "sort_order": "desc"},
            timeout=30,
            headers=_headers(token),
        )
        if not response.ok:
            raise RuntimeError(f"Official player list failed ({response.status_code}).")
        chunk = _unwrap(response.json())
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    if not rows:
        raise RuntimeError("Official player list was empty.")
    return rows


CLASSIC_GAME_MODE = 1


def fetch_user_fantasy_teams(root: Path, game_mode: int = CLASSIC_GAME_MODE) -> list[dict]:
    """Classic (or draft) Fantasy Challenge teams for the logged-in Fan ID."""
    token = _api_token(root)
    response = requests.get(
        f"{FANTAKING}/user/fantasy-teams",
        params={"league": LEAGUE_ID, "game_mode": int(game_mode)},
        timeout=30,
        headers=_headers(token),
    )
    if not response.ok:
        raise RuntimeError(f"Could not load Fantasy Challenge teams ({_api_message(response)}).")
    teams = _unwrap(response.json())
    rows = []
    for item in teams:
        if not isinstance(item, dict) or item.get("id") in (None, ""):
            continue
        rows.append(
            {
                "id": int(item["id"]),
                "name": str(item.get("name") or f"Team {item['id']}").strip(),
                "matchday_id": _pick(item, "matchday_id")
                or ((item.get("matchday") or {}).get("id") if isinstance(item.get("matchday"), dict) else None),
            }
        )
    return rows


def fetch_official_roster(root: Path, team_id: int, matchday_id: int | None = None) -> dict:
    """Current round lineup for one Fantasy Challenge team (preview with names)."""
    token = _api_token(root)
    _, current_matchday = _league_ids(token)
    round_id = int(matchday_id or current_matchday)
    response = requests.get(
        f"{FANTAKING}/fantasy-teams/{int(team_id)}/matchdays/{round_id}/roster/preview",
        timeout=30,
        headers=_headers(token),
    )
    if not response.ok:
        raise RuntimeError(f"Could not load Fantasy Challenge roster ({_api_message(response)}).")
    payload = response.json() if response.content else {}
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        raise RuntimeError("Fantasy Challenge roster response was empty.")
    players = data.get("players")
    if not isinstance(players, list) or not players:
        raise RuntimeError("Fantasy Challenge roster had no players.")
    return {
        "team_id": int(team_id),
        "matchday_id": round_id,
        "formation_id": data.get("formation_id"),
        "players": players,
    }


def fetch_official_prices(root: Path) -> pd.DataFrame:
    """Current official quotations for the logged-in Fantasy Challenge account."""
    token = _api_token(root)
    list_id, matchday_id = _league_ids(token)
    items = _fetch_players(token, list_id, matchday_id)
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        group = _position_group(item.get("position"))
        if group not in {"G", "F", "C"}:
            continue
        price = item.get("quotation")
        if price in (None, ""):
            continue
        first = str(item.get("first_name") or "").strip()
        last = str(item.get("last_name") or "").strip()
        name = " ".join(part for part in (first, last) if part)
        if not name:
            continue
        rows.append(
            {
                "source_name": name,
                "source_team": _team_name(item.get("team")),
                "position_group": group,
                "price": float(price),
                "price_change": None,
            }
        )
    if not rows:
        raise RuntimeError("Official list had no priced guards, forwards, or centers.")
    frame = pd.DataFrame(rows)
    meta = {
        "source": "official",
        "fetched_at": time.time(),
        "players": int(len(frame)),
        "matchday_id": matchday_id,
        "players_list_id": list_id,
    }
    path = price_meta_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return frame

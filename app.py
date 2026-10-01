"""Local Euroleague Fantasy Challenge dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cache import cache_dir, load_cache, refresh_cache
from src.credentials import credentials_path, example_path, fantasy_login
from src.import_squad import import_official_squad
from src.official import change_radio_options, suggested_changes_label
from src.prices import ensure_prices, load_price_meta, map_coach_prices, price_cache_path
from src.injuries import ensure_injuries, injury_cache_path
from src.optimize import _apply_horizon, _pid, build_best_team, slate_days
from src.trades import suggest_trade_upgrades, trade_records
from src.ownership import DIFFERENTIAL_MAX, TEMPLATE_MIN, differentials
from src.project import FORM_GAMES, build_dashboard
from src.squad import (
    BUDGET,
    create_team,
    delete_team,
    load_book,
    load_credits,
    load_squad,
    points_per_credit,
    rename_team,
    save_credits,
    save_named_squad,
    save_squad,
    score_squad,
    set_active_team,
    apply_player_credits,
)

POSITIONS = ["G", "F", "C"]
SLOTS = ["starter", "sixth", "bench"]
SAVED_SLOT = {
    "Captain": ("starter", True),
    "Starter": ("starter", False),
    "Sixth": ("sixth", False),
    "Bench": ("bench", False),
}
FORM_LABELS = {
    "E2025": "2025-26",
    "E2026": "2026-27",
    "blend": "Blend",
    "position": "Pos. avg",
    "none": "No games",
}
HIGHER_COLUMNS = {
    "minutes": "Min",
    "expected_minutes": "Exp min",
    "season_fantasy": "Fpts/g",
    "last5_fantasy": "Last 5",
    "fantasy_per36": "Per 36",
    "shots_per_game": "Shots/g",
    "points_per_credit": "Points per credit",
    "projected": "Projected",
    "floor": "Floor",
    "ceiling": "Ceiling",
    "win_prob": "Win %",
    "opp_factor": "Opp factor",
    "counted": "Counted",
}
LOWER_COLUMNS = {"volatility": "Volatility"}
GOOD = "background-color: #2e7d32; color: #ffffff"
MID = "background-color: #f9a825; color: #1a1a1a"
BAD = "background-color: #c62828; color: #ffffff"
COLOR_NOTE = (
    "Green is the top third of the league, yellow the middle third, and red the bottom third. "
    "Volatility is reversed, so a low number is green. Price is not colored."
)
STATUS_NOTE = (
    "Status is separate: green means available, yellow means not confirmed, and red means out."
)
PLAYER_COLUMNS = [
    "**Player** — name on the active roster.",
    "**Team** — EuroLeague club.",
    "**Pos** — G guard, F forward, or C center from the Fantasy Challenge player list (the same slots as the official game). EuroLeague box-score Center/Forward is not used when the list has a slot.",
    "**Status** — Available when he is confirmed to play. Yellow means it is not confirmed: Expected, Questionable, Game-time, Doubtful, or Uncertain. Out means he will not play. Players missing from the injury report are Available.",
    "**Note** — the injury comment. Blank when the player is Available.",
    "**GP** — games behind the averages.",
    "**Min** — average minutes in those games.",
    "**Exp min** — average minutes in the games behind Form, plus extra time when a teammate just went Out or unconfirmed (60% to the same position, cap 38). That extra is skipped if he already missed games this season, so the bump is not applied twice. When he is Available again, extra minutes that are still in teammate averages are taken back. One game of 30 minutes is 30. Two games of 30 and 15 is 22.5. Last season is used only if he has no game yet. Projected is that time times fantasy per minute, then what the opponent allows to G, F, or C, then venue and win bonus.",
    "**Fpts/g** — fantasy points per game. A win is PIR plus 10%; a loss is PIR.",
    "**Last 5** — average fantasy points over the last five games.",
    "**Per 36** — fantasy points scaled to 36 minutes.",
    "**Shots/g** — average field goal attempts per game. Feeds a small nudge (±10%) in Projected: more shots than his position's average raises it a little, fewer lowers it, shrunk toward no effect in a small sample.",
    "**Volatility** — how much the fantasy score swings. A low number is steadier, so it is green.",
    "**Price** — Fantasy Challenge credits. The public list can lag the official game after a round. Type current credits on Best team.",
    "**Owned %** — share of Fantasy Challenge managers who own him (official Fan ID list only). Blank on the public price list.",
    "**Points per credit** — Fpts/g (the average of every game in the sample) divided by Price. One game of 10 is 10 per game. Two games of 10 and 30 is 20.",
    "**Projected** — expected fantasy points for the next game: his Fpts/g times how much fantasy this opponent allows to all G, or all F, or all C in a game versus the league (one star C is the whole C pie, not cloned onto every center), times home or away, times a 10% win bonus weighted by Win %, times the Shots/g nudge. A one-game matchup is pulled toward last season.",
    "**Floor** / **Ceiling** — low and high outcomes from the last eight games, adjusted for the opponent, then scaled if Exp min rose because of a teammate injury.",
    "**Opponent** — next rival.",
    "**H/A** — Home or Away for that game.",
    "**Win %** — chance the club wins the next game.",
    "**Opp factor** — this team's G/F/C game total versus the league game total, pulled toward last season until a few games are in. Above 1 is easier. Four centers share one C pie; they do not each get the starter's night.",
    "**Form** — where the baseline comes from: 2025-26, 2026-27, or Pos. avg when the player has no history. After one game this season, Form is this season.",
    "**Turn** — only shown when the slate has more than one tip day. T1 is the first day, T2 the next, T3 if there is one. Filters the board to players whose next game is on that day.",
]
COACH_COLUMNS = [
    "**Coach** — the club's head coach. The same GP, Opponent, H/A, Win %, and Form titles apply.",
    "Coach **Fpts/g** and **Last 5** are official margin points, not PIR. Win by 1–10 or in overtime is +10, 11–20 is +20, 21+ is +25. Loss by 1–10 or overtime is −5, 11–20 is −10, 21+ is −20.",
    "**Avg margin** — average score difference in the sample. Positive means the club won by that many points on average.",
    "Coach **Projected** is the chance-weighted margin score for the next game. It counts in full, with no captain or bench multiplier.",
    "Coach **Floor** and **Ceiling** are the low and high margin scores from the last eight games.",
    "Coach **Owned %** — share of managers who picked this coach (official list only).",
    "**Form** No games means this coach has no EuroLeague results in the cache, so only the next-game projection is filled in.",
]
MATCHUP_COLUMNS = [
    "**Next opponent** — the club and whether the game is home or away.",
    "**Tip** — start time in Athens.",
    "**Win chance** — same idea as Win %.",
    "**L3 / L5 / L10 / ALL** — average fantasy this defense allowed to the whole G, F, or C group in a game this season (the pie). After 1 game they match. Factor uses ALL versus League, shrunk toward last season.",
    "**League** — league average of those game pies at that position.",
    "**Factor** — ALL divided by League, pulled toward last season. Used in Projected. Above 1 is an easier matchup.",
]
BEST_COLUMNS = [
    "**Slate** — the full next round, or only the clubs that play on the chosen day.",
    "**Coach credits** — filled from the official Fantasy Challenge list when your Fan ID is configured. You can still edit them. Best team only considers coaches with credits, then picks the one that leaves the strongest ten players inside the remaining budget.",
    "**Projected round** — squad total after captain, sixth-man, and bench multipliers, plus the coach. With more than one round, this is the sum over that window.",
    "**Rounds** — how many upcoming rounds to plan for. Each round uses that game's opponent, venue, and win chance. Form stays at today's numbers.",
    "**Start best team** — runs the picker. Opening the page does not start it. After you save My team, press Start again; the old table is not shown.",
    "**Changes** — 1, 2, 3, or 4 is how many new players come in from outside the saved team. The others stay. All builds a new squad. Prefills from your official free trades left when Fan ID data is loaded. Press Start best team after you pick.",
    "**Mode** — Exact brings in that many new players. Up to lets Best team use fewer than that if a smaller change scores just as well or better.",
    "**Include coach in changes** — checked: Best team may pick a different priced coach. Unchecked: the coach from the selected saved team stays.",
    "**Move** — Keep means the player is already on the selected saved team. New means they are not.",
    "**Credits** — squad budget, coach included. Prefills from your Fantasy Challenge bank when the official login is configured. Player prices plus the coach price must stay inside that number.",
    "**Formation (G-F-C)** — guards, forwards, and centers in the starting five. Legal shapes are 2-2-1, 1-2-2, 2-1-2, 1-3-1, and 3-1-1.",
    "**Status** — only Available players are chosen. Out and unconfirmed players are left out.",
    "**Note** — why a player on the left-out list is not confirmed.",
    "**Coming in / Going out** — after the suggestion, compared with the Saved team you have selected. Coming in is new to that team. Going out is on that team and not in the suggestion, including a coach change.",
    "**Slot** — Captain counts double, Starter and Sixth count in full, Bench counts at half.",
    "**Day** — tip day in Athens. **Turn** is T1, T2, or T3. At most six of the ten can be T1 when a later day exists, so those players can replace a low T1 score. A one-day slate has only T1.",
    "**Form** — 2026-27 if he has played this season, 2025-26 if not. Best team uses that same mix; there is no season button.",
    "**Exp min** — minutes expected in each game of the window, including extra time when a teammate just went Out or unconfirmed (same games played as the club). Same position gets 60%. If he already missed games in the sample, those minutes are not added again. When he returns, teammate Exp min goes back toward normal. The projection is that time times fantasy per minute, then what the opponent allows to the position. Reserves need about 15.",
    "**Counted** — Projected times that slot multiplier.",
    "**Projected** — expected fantasy points for the next game, before the slot multiplier. Matchup is that opponent's G/F/C game pie versus the league, not one starter's line times every player. Includes the Shots/g nudge.",
    "**Shots/g** — average field goal attempts per game. More than his position's average nudges Projected up a little (less than average nudges it down), capped at ±10% and shrunk toward no effect in a small sample.",
    "**Price** and **Points per credit** — published credits, and Fpts/g divided by that price.",
    "**Owned %** — share of managers who own him (official Fan ID list). Blank without official prices.",
    "**Trade one player** — same-position upgrades at or below his price; sorted by +Counted for his My team slot (captain 2×, bench 0.5×). Needs at least +1.0 projected and +0.5 counted. Shows bank freed when the pick is cheaper.",
]
SQUAD_COLUMNS = [
    "**Status** — Available, a yellow unconfirmed status, or Out. Best team will not use anyone who is not Available.",
    "**Note** — the injury comment for players who are not Available.",
    "**Slot** — starter, sixth, or bench. Five starters, one sixth man, four bench.",
    "**Captain** — one starter. That player counts double.",
    "**Price** — published credits. It counts toward the 100-credit budget.",
    "**Owned %** — share of Fantasy Challenge managers who own him when official prices are loaded.",
    "**Points per credit** — Fpts/g (the average of every game in the sample) divided by Price. One game of 10 is 10 per game. Two games of 10 and 30 is 20.",
    "**Projected** — expected fantasy points for the next game, before the slot multiplier.",
    "**Counted** — Projected times the slot multiplier.",
    "**Coach price** — from the official Fantasy Challenge list when credentials are configured.",
    "**Projected round** — lineup total plus the coach.",
]


def _show_columns(lines: list[str]) -> None:
    with st.expander("Column guide"):
        st.markdown("\n".join(f"- {line}" for line in lines))


def _round(value, digits=1):
    if pd.isna(value):
        return None
    return round(float(value), digits)


def _owned_label(value) -> str | None:
    """Format ownership share 0–1 as a percent string."""
    if value is None or pd.isna(value):
        return None
    return f"{float(value) * 100:.0f}%"


def _bands(frame: pd.DataFrame, columns: list[str]) -> dict[str, tuple[float, float]]:
    bands = {}
    for column in columns:
        if column not in frame.columns:
            continue
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            continue
        bands[column] = (float(series.quantile(0.33)), float(series.quantile(0.66)))
    return bands


def _color_values(values, low: float, high: float, higher: bool) -> list[str]:
    styles = []
    for value in values:
        if value is None or pd.isna(value):
            styles.append("")
            continue
        number = float(value)
        if higher:
            styles.append(GOOD if number >= high else BAD if number <= low else MID)
        else:
            styles.append(GOOD if number <= low else BAD if number >= high else MID)
    return styles


def _paint(
    view: pd.DataFrame,
    source: pd.DataFrame,
    bands: dict[str, tuple[float, float]],
    columns: dict[str, str],
    lower: set[str] | None = None,
):
    lower_keys = set(LOWER_COLUMNS) if lower is None else lower
    styler = view.style
    for key, display in columns.items():
        if key not in bands or display not in view.columns or key not in source.columns:
            continue
        low, high = bands[key]
        numeric = pd.to_numeric(source[key], errors="coerce")
        colors = _color_values(numeric.tolist(), low, high, key not in lower_keys)
        styler = styler.apply(lambda _column, colors=colors: colors, subset=[display])
    return styler


def _status_colors(availability: pd.Series) -> list[str]:
    colors = []
    for value in availability:
        if value == "out":
            colors.append(BAD)
        elif value == "uncertain":
            colors.append(MID)
        elif value == "available":
            colors.append(GOOD)
        else:
            colors.append("")
    return colors


def _paint_status(styler, source: pd.DataFrame):
    data = getattr(styler, "data", None)
    if data is None or "Status" not in data.columns or "availability" not in source.columns:
        return styler
    if len(source) != len(data):
        return styler
    colors = _status_colors(source["availability"])
    return styler.apply(lambda _column, colors=colors: colors, subset=["Status"])


def _styled_board(filtered: pd.DataFrame, projections: pd.DataFrame):
    bands = _bands(projections, list(HIGHER_COLUMNS) + list(LOWER_COLUMNS))
    painted = _paint(_board_view(filtered), filtered, bands, {**HIGHER_COLUMNS, **LOWER_COLUMNS})
    return _paint_status(painted, filtered)


COACH_HIGHER = {
    "season_fantasy": "Fpts/g",
    "last5_fantasy": "Last 5",
    "avg_margin": "Avg margin",
    "projected": "Projected",
    "floor": "Floor",
    "ceiling": "Ceiling",
    "win_prob": "Win %",
}


def _coach_view(frame: pd.DataFrame) -> pd.DataFrame:
    view = frame.copy()
    for column, digits in (
        ("season_fantasy", 1),
        ("last5_fantasy", 1),
        ("volatility", 1),
        ("avg_margin", 1),
        ("projected", 1),
        ("floor", 1),
        ("ceiling", 1),
    ):
        if column in view:
            view[column] = view[column].map(lambda value, digits=digits: _round(value, digits))
    if "win_prob" in view:
        view["win_prob"] = view["win_prob"].map(
            lambda value: None if value is None or pd.isna(value) else f"{float(value):.0%}"
        )
    if "form_source" in view:
        view["form_source"] = view["form_source"].map(lambda value: FORM_LABELS.get(value, value))
    if "ownership" in view:
        view["ownership"] = view["ownership"].map(_owned_label)
    rename = {
        "coach_name": "Coach",
        "team_name": "Team",
        "sample_gp": "GP",
        "season_fantasy": "Fpts/g",
        "last5_fantasy": "Last 5",
        "volatility": "Volatility",
        "avg_margin": "Avg margin",
        "projected": "Projected",
        "floor": "Floor",
        "ceiling": "Ceiling",
        "ownership": "Owned %",
        "opponent_name": "Opponent",
        "home_away": "H/A",
        "win_prob": "Win %",
        "form_source": "Form",
    }
    keep = [column for column in rename if column in view.columns]
    return view[keep].rename(columns=rename)


def _styled_coaches(frame: pd.DataFrame, coaches: pd.DataFrame):
    if frame is None or frame.empty:
        return _coach_view(frame)
    bands = _bands(coaches, list(COACH_HIGHER) + ["volatility"])
    return _paint(
        _coach_view(frame),
        frame,
        bands,
        {**COACH_HIGHER, "volatility": "Volatility"},
        lower={"volatility"},
    )


def _coaches_for(coaches: pd.DataFrame, team_code: str | None = None) -> pd.DataFrame:
    view = coaches if team_code is None else coaches[coaches["team_code"] == team_code]
    if view.empty or "projected" not in view.columns:
        return view
    return view.sort_values("projected", ascending=False, na_position="last")


def _board_view(frame: pd.DataFrame) -> pd.DataFrame:
    view = frame.copy()
    for column, digits in (
        ("minutes", 1),
        ("expected_minutes", 1),
        ("season_fantasy", 1),
        ("last5_fantasy", 1),
        ("opp_factor", 2),
        ("win_prob", 2),
        ("projected", 1),
        ("price", 1),
        ("fantasy_per36", 1),
        ("shots_per_game", 1),
        ("volatility", 1),
        ("points_per_credit", 2),
        ("floor", 1),
        ("ceiling", 1),
    ):
        if column in view:
            view[column] = view[column].map(lambda value, digits=digits: _round(value, digits))
    view["win_prob"] = view["win_prob"].map(
        lambda value: None if value is None or pd.isna(value) else f"{float(value):.0%}"
    )
    view["form_source"] = view["form_source"].map(lambda value: FORM_LABELS.get(value, value))
    if "ownership" in view.columns:
        view["ownership"] = view["ownership"].map(_owned_label)
    rename = {
        "player_name": "Player",
        "team_name": "Team",
        "position_group": "Pos",
        "status_label": "Status",
        "injury_note": "Note",
        "sample_gp": "GP",
        "minutes": "Min",
        "expected_minutes": "Exp min",
        "season_fantasy": "Fpts/g",
        "last5_fantasy": "Last 5",
        "fantasy_per36": "Per 36",
        "shots_per_game": "Shots/g",
        "volatility": "Volatility",
        "price": "Price",
        "ownership": "Owned %",
        "points_per_credit": "Points per credit",
        "projected": "Projected",
        "floor": "Floor",
        "ceiling": "Ceiling",
        "opponent_name": "Opponent",
        "home_away": "H/A",
        "win_prob": "Win %",
        "opp_factor": "Opp factor",
        "form_source": "Form",
    }
    keep = [column for column in rename if column in view.columns]
    view = view[keep].rename(columns=rename)
    return view.set_index("Player") if "Player" in view.columns else view


def _filter_board(frame: pd.DataFrame) -> pd.DataFrame:
    teams = ["All teams"] + sorted(frame["team_name"].dropna().unique())
    positions = ["All positions"] + POSITIONS
    team_col, position_col, venue_col, sort_col = st.columns(4)
    with team_col:
        team = st.selectbox("Team", teams, key="board_team")
    with position_col:
        position = st.selectbox("Position", positions, key="board_position")
    with venue_col:
        venue = st.selectbox("Venue", ["All venues", "Home", "Away"], key="board_venue")
    with sort_col:
        sort = st.selectbox(
            "Sort",
            ["Points per credit", "Projected", "Owned %", "Per 36", "Last 5", "Minutes"],
            key="board_sort",
        )
    search_col, minutes_col, status_col, turn_col = st.columns([2, 1, 1, 1])
    with search_col:
        query = st.text_input("Player", key="board_query")
    with minutes_col:
        minimum_minutes = st.number_input("Minimum minutes", min_value=0.0, max_value=40.0, value=0.0, step=1.0, key="board_minutes")
    with status_col:
        status = st.selectbox(
            "Status",
            ["All statuses", "Available", "Not confirmed", "Out"],
            key="board_status",
        )
    turn_labels = {day: f"T{index + 1}" for index, day in enumerate(slate_days(frame))}
    turn = "All days"
    with turn_col:
        if len(turn_labels) > 1:
            turn = st.selectbox("Turn", ["All days"] + list(turn_labels.values()), key="board_turn")
    view = frame
    if team != "All teams":
        view = view[view["team_name"] == team]
    if position != "All positions":
        view = view[view["position_group"] == position]
    if venue != "All venues":
        view = view[view["home_away"] == venue]
    if query.strip():
        view = view[view["player_name"].str.contains(query.strip(), case=False, na=False)]
    if minimum_minutes > 0:
        view = view[view["minutes"].fillna(0) >= minimum_minutes]
    if status != "All statuses" and "availability" in view.columns:
        wanted = {"Available": "available", "Not confirmed": "uncertain", "Out": "out"}[status]
        view = view[view["availability"] == wanted]
    if turn != "All days":
        wanted_day = next(day for day, label in turn_labels.items() if label == turn)
        local = pd.to_datetime(view["game_date"], utc=True, errors="coerce").dt.tz_convert("Europe/Athens").dt.normalize()
        view = view[local == wanted_day]
    sort_column = {
        "Points per credit": "points_per_credit",
        "Projected": "projected",
        "Owned %": "ownership",
        "Per 36": "fantasy_per36",
        "Last 5": "last5_fantasy",
        "Minutes": "minutes",
    }[sort]
    if sort_column not in view.columns:
        sort_column = "projected"
    return view.sort_values(sort_column, ascending=False, na_position="last")


def _stored_price(value):
    if pd.isna(value):
        return None
    number = float(value)
    if number <= 0:
        return None
    return number


def _page_board(data) -> None:
    st.subheader("Player board")
    st.caption(
        "Next-game fantasy points for the active roster. Filter by club, position, venue, or minutes. "
        "A player who has played this season uses this season only for minutes, points, Last 5, Exp min, floor, ceiling, and projection. Last season is used only when he has no game yet. "
        "When a teammate is Out or unconfirmed, Available players on that club get extra Exp min (60% to the same position), but only if that teammate has not already missed games in this season's sample. When he is Available again, that extra is taken back. Min and Last 5 stay historical."
    )
    _show_columns(PLAYER_COLUMNS + COACH_COLUMNS)
    filtered = _filter_board(data.projections)
    st.dataframe(_styled_board(filtered, data.projections), width="stretch")
    st.caption(
        f"{len(filtered)} players. Leave Team on All teams to see the league, or pick one club. {COLOR_NOTE} {STATUS_NOTE}"
    )
    _show_differentials(data.projections)
    st.subheader("Coaches")
    coaches = _coaches_for(data.coaches)
    st.dataframe(_styled_coaches(coaches, data.coaches), hide_index=True, width="stretch")
    st.caption(f"{len(coaches)} coaches. Colors compare coaches with each other. {COLOR_NOTE}")


def _show_differentials(projections: pd.DataFrame, held_ids: list[str] | None = None) -> None:
    """Low-owned pickups and highly owned players missing from the saved team."""
    if held_ids is None:
        squad = load_squad(ROOT)
        held_ids = [entry.get("player_id") for entry in squad.get("players") or []]
    diffs, risk = differentials(projections, held_ids)
    has_ownership = (
        projections is not None
        and not projections.empty
        and "ownership" in projections.columns
        and projections["ownership"].notna().any()
    )
    with st.expander("Differentials and template risk", expanded=False):
        if not has_ownership:
            st.caption(
                "Owned % needs the official Fantasy Challenge list. Add Fan ID credentials and press Refresh data."
            )
            return
        low_pct = int(DIFFERENTIAL_MAX * 100)
        high_pct = int(TEMPLATE_MIN * 100)
        st.caption(
            f"Compared with your saved My team. Differentials: Available, under {low_pct}% owned, sorted by Projected. "
            f"Template risk: Available, {high_pct}%+ owned, not on your team."
        )
        left, right = st.columns(2)
        with left:
            st.markdown("**Differentials**")
            if diffs.empty:
                st.caption("None under the ownership cutoff.")
            else:
                st.dataframe(_styled_board(diffs, projections), width="stretch")
        with right:
            st.markdown("**Template risk**")
            if risk.empty:
                st.caption("You cover the highly owned Available players.")
            else:
                st.dataframe(_styled_board(risk, projections), width="stretch")


def _page_matchup(data) -> None:
    st.subheader("Matchup")
    st.caption(
        "One club’s next game. Opponent G/F/C allowed is the fantasy that whole position scored in a game "
        "(this season). Factor is that pie versus the league, pulled toward last season while games are few."
    )
    _show_columns(MATCHUP_COLUMNS + PLAYER_COLUMNS + COACH_COLUMNS)
    if data.defense.empty:
        st.info("No upcoming games are on the schedule yet.")
        return
    teams = (
        data.projections[["team_code", "team_name"]]
        .drop_duplicates()
        .sort_values("team_name")
    )
    labels = {row.team_name: row.team_code for row in teams.itertuples(index=False)}
    team_name = st.selectbox("Team", list(labels), key="matchup_team")
    team_code = labels[team_name]
    defense = data.defense[data.defense["team_code"] == team_code]
    if defense.empty:
        st.info("This team has no upcoming game in the cached schedule.")
        return
    first = defense.iloc[0]
    date = pd.to_datetime(first["game_date"]).tz_convert("Europe/Athens").strftime("%d %b %Y %H:%M")
    left, middle, right = st.columns(3)
    left.metric("Next opponent", f"{first['opponent_name']} ({first['home_away']})")
    middle.metric("Tip", date)
    right.metric("Win chance", f"{float(first['win_prob']):.0%}")
    table = defense[
        ["position_group", "l3", "l5", "l10", "opp_allowed", "league_allowed", "opp_factor"]
    ].copy()
    numeric = table.copy()
    for column in ("l3", "l5", "l10", "opp_allowed", "league_allowed"):
        table[column] = table[column].map(lambda value: _round(value, 1))
    table["opp_factor"] = table["opp_factor"].map(lambda value: _round(value, 2))
    table = table.rename(
        columns={
            "position_group": "Pos",
            "l3": "L3",
            "l5": "L5",
            "l10": "L10",
            "opp_allowed": "ALL",
            "league_allowed": "League",
            "opp_factor": "Factor",
        }
    )
    defense_bands = _bands(data.defense, ["opp_allowed", "opp_factor"])
    painted = _paint(
        table,
        numeric.rename(columns={"opp_allowed": "opp_allowed", "opp_factor": "opp_factor"}),
        defense_bands,
        {"opp_allowed": "ALL", "opp_factor": "Factor"},
    )
    st.dataframe(painted, hide_index=True, width="stretch")
    games = int(first["defense_games"]) if "defense_games" in first.index else 0
    st.caption(
        "Same idea as a game pie, not a starter cloned onto every player: ALL is total G, F, or C fantasy "
        "allowed in a game this season. L3/L5/L10 are the last 3/5/10 games. Factor is ALL versus the league, "
        f"shrunk toward last season ({games} games for this opponent). Four centers share the C pie. "
        + COLOR_NOTE
    )
    coach = _coaches_for(data.coaches, team_code)
    if not coach.empty:
        st.subheader("Coach")
        st.dataframe(_styled_coaches(coach, data.coaches), hide_index=True, width="stretch")
    players = data.projections[data.projections["team_code"] == team_code]
    position = st.selectbox("Position", ["All positions"] + POSITIONS, key="matchup_position")
    if position != "All positions":
        players = players[players["position_group"] == position]
    players = players.sort_values("points_per_credit", ascending=False, na_position="last")
    st.dataframe(_styled_board(players, data.projections), width="stretch")


def _page_squad(data) -> None:
    st.subheader("My team")
    st.caption("Your own 4-guard, 4-forward, 2-center squad. Starters and the sixth man count in full, the bench at half, and one starter is captain at double.")
    _show_columns(SQUAD_COLUMNS + COACH_COLUMNS)
    book = load_book(ROOT)
    names = list(book["teams"])
    active = book["active"]
    pick_col, create_col = st.columns(2)
    with pick_col:
        chosen = st.selectbox("Saved team", names, index=names.index(active), key="squad_pick")
    if chosen != active:
        set_active_team(ROOT, chosen)
        st.rerun()
    with create_col:
        new_name = st.text_input("New team name", key="new_team_name")
        if st.button("Create team", key="create_team"):
            error = create_team(ROOT, new_name)
            if error:
                st.warning(error)
            else:
                st.rerun()
    rename_col, delete_col = st.columns(2)
    with rename_col:
        renamed = st.text_input("Rename this team", value=active, key=f"rename_input_{active}")
        if st.button("Rename", key="rename_team"):
            error = rename_team(ROOT, active, renamed)
            if error:
                st.warning(error)
            else:
                st.rerun()
    with delete_col:
        st.write("")
        st.write("")
        if st.button("Delete this team", key="delete_team"):
            error = delete_team(ROOT, active)
            if error:
                st.warning(error)
            else:
                st.rerun()
    squad = load_squad(ROOT)
    projections = apply_player_credits(data.projections, load_credits(ROOT))
    _import_official_section(active, squad, projections, data.coaches)
    existing_ids = {entry.get("player_id") for entry in squad["players"]}
    available = projections[~projections["player_id"].isin(existing_ids)].sort_values("player_name")
    options = {}
    for row in available.itertuples(index=False):
        label = f"{row.player_name} ({row.team_name}, {row.position_group})"
        player_status = getattr(row, "status_label", "Available")
        if player_status and player_status != "Available":
            label = f"{label}, {player_status}"
        options[label] = row.player_id

    with st.form("add_player"):
        choice = st.selectbox("Add player", ["—"] + list(options), key="add_choice")
        slot = st.selectbox("Slot", SLOTS, key="add_slot")
        captain = st.checkbox("Captain", key="add_captain")
        submitted = st.form_submit_button("Add to squad")
    if submitted and choice != "—":
        squad["players"].append(
            {
                "player_id": options[choice],
                "slot": slot,
                "captain": captain and slot == "starter",
                "price": None,
            }
        )
        save_squad(ROOT, squad)
        st.rerun()

    scored = score_squad(squad, projections, data.coaches)
    players = scored["players"]
    if players.empty:
        st.info("Add 10 players: 4 guards, 4 forwards, 2 centers.")
    else:
        columns = [
            "player_id",
            "player_name",
            "team_name",
            "position_group",
            "status_label",
            "injury_note",
            "slot",
            "captain",
            "price",
            "per_credit",
            "projected",
            "points",
        ]
        if "ownership" in players.columns:
            columns.insert(columns.index("price") + 1, "ownership")
        editor = players[columns].copy()
        if "ownership" in editor.columns:
            editor["ownership"] = editor["ownership"].map(_owned_label)
        disabled = [column for column in columns if column not in {"slot", "captain"}]
        column_config = {
            "player_id": st.column_config.TextColumn("Id"),
            "player_name": st.column_config.TextColumn("Player"),
            "team_name": st.column_config.TextColumn("Team"),
            "position_group": st.column_config.TextColumn("Pos"),
            "status_label": st.column_config.TextColumn("Status"),
            "injury_note": st.column_config.TextColumn("Note"),
            "slot": st.column_config.SelectboxColumn("Slot", options=SLOTS, required=True),
            "captain": st.column_config.CheckboxColumn("Captain"),
            "price": st.column_config.NumberColumn("Price", format="%.1f"),
            "per_credit": st.column_config.NumberColumn("Points per credit", format="%.2f"),
            "projected": st.column_config.NumberColumn("Projected", format="%.1f"),
            "points": st.column_config.NumberColumn("Counted", format="%.1f"),
        }
        if "ownership" in editor.columns:
            column_config["ownership"] = st.column_config.TextColumn("Owned %")
        edited = st.data_editor(
            editor,
            hide_index=True,
            width="stretch",
            key=f"squad_editor_{active}",
            disabled=disabled,
            column_config=column_config,
        )
        if "availability" in players.columns:
            blocked = players[players["availability"] != "available"]
            if not blocked.empty:
                names = ", ".join(
                    f"{row.player_name} ({row.status_label})" for row in blocked.itertuples(index=False)
                )
                st.warning(f"Not confirmed to play: {names}.")
        _show_differentials(
            projections,
            held_ids=[entry.get("player_id") for entry in squad.get("players") or []],
        )
        remove = st.multiselect(
            "Remove",
            options=players["player_id"].tolist(),
            format_func=lambda player_id: players.loc[players["player_id"] == player_id, "player_name"].iloc[0],
            key=f"remove_players_{active}",
        )
        if st.button("Save lineup", key=f"save_lineup_{active}"):
            keep = []
            for row in edited.itertuples(index=False):
                if row.player_id in remove:
                    continue
                keep.append(
                    {
                        "player_id": row.player_id,
                        "slot": row.slot,
                        "captain": bool(row.captain),
                        "price": None,
                    }
                )
            squad["players"] = keep
            save_squad(ROOT, squad)
            st.rerun()

    coach_options = {"No coach": None}
    if not data.coaches.empty:
        for row in data.coaches.sort_values("coach_name").itertuples(index=False):
            coach_options[f"{row.coach_name} ({row.team_name})"] = row.coach_id
    official_coach_prices = map_coach_prices(data.coaches, ensure_prices(ROOT))
    current_label = "No coach"
    for label, coach_id in coach_options.items():
        if coach_id == squad.get("coach_id"):
            current_label = label
            break
    with st.form(f"coach_form_{active}"):
        coach_label = st.selectbox(
            "Coach",
            list(coach_options),
            index=list(coach_options).index(current_label),
            key=f"coach_choice_{active}",
        )
        chosen_preview = coach_options[coach_label]
        if chosen_preview and str(chosen_preview) in official_coach_prices:
            st.caption(
                f"Coach credits: {official_coach_prices[str(chosen_preview)]:.1f} "
                "(from the official Fantasy Challenge list)."
            )
        elif chosen_preview:
            st.caption("No official coach price loaded yet. Refresh data with your Fan ID configured.")
        else:
            st.caption("Coach credits come from the official Fantasy Challenge list.")
        if st.form_submit_button("Save coach"):
            chosen_id = coach_options[coach_label]
            price = None
            if chosen_id:
                price = _stored_price(official_coach_prices.get(str(chosen_id)))
                if price is None:
                    st.warning(
                        "That coach has no official price yet. Refresh data with your Fan ID, then save again."
                    )
                    return
            squad["coach_id"] = chosen_id
            squad["coach_price"] = price
            save_squad(ROOT, squad)
            st.rerun()

    # Prefer live official coach quotation for scoring when the coach is set.
    scoring_squad = dict(load_squad(ROOT))
    coach_id = scoring_squad.get("coach_id")
    if coach_id and str(coach_id) in official_coach_prices:
        scoring_squad["coach_price"] = float(official_coach_prices[str(coach_id)])
    price_meta = load_price_meta(ROOT)
    bank_limit = BUDGET
    raw_bank = price_meta.get("team_bank")
    if raw_bank not in (None, ""):
        try:
            bank_limit = float(raw_bank)
        except (TypeError, ValueError):
            bank_limit = BUDGET
    scored = score_squad(scoring_squad, projections, data.coaches, budget=bank_limit)
    counts = scored["counts"]
    slots = scored["slot_counts"]
    summary = st.columns(4)
    summary[0].metric("Projected round", f"{scored['total']:.1f}")
    summary[1].metric("Guards / forwards / centers", f"{counts['G']}/4 · {counts['F']}/4 · {counts['C']}/2")
    summary[2].metric(
        "Starters / sixth / bench",
        f"{slots.get('starter', 0)}/5 · {slots.get('sixth', 0)}/1 · {slots.get('bench', 0)}/4",
    )
    price_sum = scored["price_sum"]
    budget_limit = float(scored.get("budget") or bank_limit)
    summary[3].metric(
        "Credits",
        "—" if price_sum is None else f"{price_sum:.1f} / {budget_limit:.1f}",
    )
    coach = scored["coach"]
    if coach is not None and scored["coach_points"] is not None:
        coach_value = points_per_credit(scored["coach_points"], scored["coach_price"])
        value_text = "" if coach_value is None else f" Points per credit: {coach_value:.2f}."
        price_text = ""
        if scored.get("coach_price") is not None:
            price_text = f" Credits {float(scored['coach_price']):.1f}."
        st.write(
            f"Coach {coach.coach_name} vs {coach.opponent_name} ({coach.home_away}): "
            f"{scored['coach_points']:.1f} projected points.{price_text}{value_text}"
        )
        detail = data.coaches[data.coaches["coach_id"] == coach.coach_id]
        if not detail.empty:
            st.dataframe(_styled_coaches(detail, data.coaches), hide_index=True, width="stretch")
    for message in scored["messages"]:
        st.warning(message)
    if not scored["messages"] and len(scored["players"]) == 10 and coach is not None:
        st.success("Roster shape matches the Fantasy Challenge: 4 guards, 4 forwards, 2 centers, and a coach.")


def _import_official_section(active: str, squad: dict, projections: pd.DataFrame, coaches: pd.DataFrame) -> None:
    """Optional one-click import from the logged-in Fantasy Challenge account."""
    flash = st.session_state.pop("import_flash", None)
    if flash:
        st.success(flash)
        for message in st.session_state.pop("import_flash_warnings", []):
            st.warning(message)
    with st.expander("Import from Fantasy Challenge", expanded=False):
        st.caption(
            "Pull the current official lineup into this saved team. Does nothing until you press Import. "
            "Needs the same Fan ID file used for live credits."
        )
        if not fantasy_login(ROOT):
            st.info(
                f"Copy {example_path(ROOT).name} to {credentials_path(ROOT).name}, "
                "add your EuroLeague Fan ID email and password, then try again."
            )
            return
        remote_teams = st.session_state.get("import_fantasy_teams") or []
        team_labels = {f"{team['name']} (id {team['id']})": int(team["id"]) for team in remote_teams}
        selected_id = None
        if len(team_labels) > 1:
            choice = st.selectbox(
                "Fantasy Challenge team",
                list(team_labels),
                key="import_fantasy_team_pick",
            )
            selected_id = team_labels[choice]
        elif len(team_labels) == 1:
            only_id = next(iter(team_labels.values()))
            selected_id = only_id
            st.caption(f"Will import: {next(iter(team_labels))}.")
        has_players = bool(squad.get("players"))
        replace = True
        if has_players:
            replace = st.checkbox(
                f"Replace the players and coach on “{active}”",
                value=False,
                key="import_replace_confirm",
                help="Import overwrites this saved team. Leave unchecked to cancel.",
            )
        if st.button("Import lineup", type="primary", key="import_official_lineup"):
            if has_players and not replace:
                st.warning(f"Check Replace to overwrite “{active}”, or create a new empty team first.")
                return
            with st.spinner("Loading Fantasy Challenge lineup..."):
                try:
                    result = import_official_squad(
                        ROOT,
                        projections,
                        coaches,
                        team_id=selected_id,
                    )
                except Exception as exc:
                    st.error(str(exc))
                    return
            if result.get("teams"):
                st.session_state["import_fantasy_teams"] = result["teams"]
            if result.get("needs_team_choice"):
                st.info("Choose which Fantasy Challenge team to import, then press Import lineup again.")
                st.rerun()
                return
            mapped = result.get("squad") or {}
            matched = int(result.get("matched_players") or 0)
            if matched == 0:
                st.error("No players from Fantasy Challenge could be matched to the local board.")
                for message in result.get("warnings") or []:
                    st.warning(message)
                return
            save_squad(ROOT, mapped)
            st.session_state.pop("best_result", None)
            label = result.get("team_name") or "Fantasy Challenge"
            st.session_state["import_flash"] = (
                f"Imported {matched} players"
                + (" and a coach" if mapped.get("coach_id") else "")
                + f" from {label} into “{active}”."
            )
            st.session_state["import_flash_warnings"] = list(result.get("warnings") or [])
            st.rerun()


def _with_player_status(players: pd.DataFrame, projections: pd.DataFrame) -> pd.DataFrame:
    """Fill status from the board when a cached squad was built without it."""
    frame = players.copy()
    if frame.empty or "player_id" not in frame.columns or "status_label" not in projections.columns:
        return frame
    lookup = projections.drop_duplicates("player_id").copy()
    lookup["player_id"] = lookup["player_id"].astype(str)
    lookup = lookup.set_index("player_id")
    ids = frame["player_id"].astype(str)
    for column, default in (
        ("status_label", "Available"),
        ("injury_note", ""),
        ("availability", "available"),
        ("form_source", ""),
    ):
        if column not in lookup.columns:
            continue
        mapped = ids.map(lookup[column])
        if column not in frame.columns:
            frame[column] = mapped
        else:
            blank = frame[column].isna() | (frame[column].astype(str).str.strip() == "")
            frame[column] = frame[column].where(~blank, mapped)
        frame[column] = frame[column].fillna(default)
    return frame


def _best_view(frame: pd.DataFrame) -> pd.DataFrame:
    view = frame.copy()
    for column, digits in (
        ("price", 1),
        ("projected", 1),
        ("points_per_credit", 2),
        ("shots_per_game", 1),
        ("counted", 1),
        ("expected_minutes", 1),
    ):
        if column in view.columns:
            view[column] = view[column].map(lambda value, digits=digits: _round(value, digits))
    if "form_source" in view.columns:
        view["form_source"] = view["form_source"].map(lambda value: FORM_LABELS.get(value, value) if value else "")
    if "ownership" in view.columns:
        view["ownership"] = view["ownership"].map(_owned_label)
    rename = {
        "slot": "Slot",
        "player_name": "Player",
        "team_name": "Team",
        "position_group": "Pos",
        "status_label": "Status",
        "injury_note": "Note",
        "opponent_name": "Opponent",
        "home_away": "H/A",
        "tip_day": "Day",
        "turn": "Turn",
        "form_source": "Form",
        "expected_minutes": "Exp min",
        "price": "Price",
        "ownership": "Owned %",
        "projected": "Projected",
        "points_per_credit": "Points per credit",
        "shots_per_game": "Shots/g",
        "counted": "Counted",
        "move": "Move",
    }
    if "move" in view.columns and not view["move"].notna().any():
        rename.pop("move")
    rename = {key: label for key, label in rename.items() if key in view.columns}
    return view[list(rename)].rename(columns=rename)


def _mark_moves(players: pd.DataFrame, saved_ids: list[str]) -> pd.DataFrame:
    """Tag suggestion rows Keep or New against the selected saved team."""
    frame = players.copy()
    if frame.empty or "player_id" not in frame.columns:
        return frame
    held = {str(player_id) for player_id in saved_ids}
    if not held:
        if "move" in frame.columns:
            frame = frame.drop(columns=["move"])
        return frame
    frame["move"] = frame["player_id"].astype(str).map(lambda player_id: "Keep" if player_id in held else "New")
    return frame


def _show_squad_diff(
    team_name: str,
    saved: dict,
    chosen: pd.DataFrame,
    projections: pd.DataFrame,
    coaches: pd.DataFrame,
    result: dict,
) -> None:
    """Who is new in the suggestion and who drops from the selected saved team."""
    saved_ids = [_pid(entry.get("player_id")) for entry in saved.get("players", []) if entry.get("player_id")]
    if not saved_ids and not saved.get("coach_id"):
        return
    chosen_ids = set() if chosen is None or chosen.empty else set(chosen["player_id"].map(_pid))
    held = set(saved_ids)
    coming = pd.DataFrame() if chosen is None or chosen.empty else chosen[~chosen["player_id"].map(_pid).isin(held)]
    going = projections[projections["player_id"].map(_pid).isin(held)]
    going = going[~going["player_id"].map(_pid).isin(chosen_ids)]
    saved_coach = None if not saved.get("coach_id") else str(saved.get("coach_id"))
    result_coach = None if not result.get("coach_id") else str(result.get("coach_id"))
    coach_changed = bool(saved_coach or result_coach) and saved_coach != result_coach

    st.subheader(f"Compared with {team_name}")
    if coming.empty and going.empty and not coach_changed:
        st.caption(f"The suggestion matches {team_name}.")
        return

    in_col, out_col = st.columns(2)
    with in_col:
        st.markdown("**Coming in**")
        if coming.empty and not (coach_changed and result.get("coach_name")):
            st.caption("Nobody new.")
        else:
            if not coming.empty:
                st.dataframe(_best_view(coming), hide_index=True, width="stretch")
            if coach_changed and result.get("coach_name"):
                st.caption(
                    f"Coach in: {result['coach_name']} ({result.get('coach_team') or ''}) "
                    f"at {float(result.get('coach_price') or 0):.1f} credits."
                )
    with out_col:
        st.markdown("**Going out**")
        if going.empty and not (coach_changed and saved_coach):
            st.caption("Nobody dropped.")
        else:
            if not going.empty:
                going = going.sort_values("projected", ascending=False, na_position="last")
                st.dataframe(_styled_board(going, projections), width="stretch")
            if coach_changed and saved_coach:
                names = coaches[coaches["coach_id"].astype(str) == saved_coach] if coaches is not None and not coaches.empty else coaches
                label = saved_coach
                if names is not None and not names.empty:
                    row = names.iloc[0]
                    label = f"{row.coach_name} ({row.team_name})"
                st.caption(f"Coach out: {label}.")
    st.caption(
        f"Coming in is not on {team_name}. Going out is on {team_name} and is not in this suggestion. "
        "Press Use to rebuild from that team with a change limit."
    )


def _trade_view(frame: pd.DataFrame) -> pd.DataFrame:
    view = frame.copy()
    for column, digits in (
        ("price", 1),
        ("projected", 1),
        ("counted", 1),
        ("delta_projected", 1),
        ("delta_counted", 1),
        ("delta_price", 1),
        ("credit_freed", 1),
        ("expected_minutes", 1),
        ("floor", 1),
        ("ceiling", 1),
        ("opp_factor", 2),
        ("points_per_credit", 2),
    ):
        if column in view.columns:
            view[column] = view[column].map(lambda value, digits=digits: _round(value, digits))
    if "ownership" in view.columns:
        view["ownership"] = view["ownership"].map(_owned_label)
    rename = {
        "player_name": "Player",
        "team_name": "Team",
        "position_group": "Pos",
        "opponent_name": "Opponent",
        "home_away": "H/A",
        "turn": "Turn",
        "price": "Price",
        "projected": "Projected",
        "counted": "Counted",
        "delta_projected": "+Proj",
        "delta_counted": "+Counted",
        "delta_price": "Price Δ",
        "credit_freed": "Bank freed",
        "expected_minutes": "Exp min",
        "floor": "Floor",
        "ceiling": "Ceiling",
        "opp_factor": "Opp factor",
        "ownership": "Owned %",
        "points_per_credit": "Points per credit",
    }
    keep = [key for key in rename if key in view.columns]
    return view[keep].rename(columns=rename)


def _trade_suggestions_box(
    team_name: str,
    saved: dict,
    saved_ids: list[str],
    projections: pd.DataFrame,
    coaches: pd.DataFrame,
    horizon: int,
    day,
    price_meta: dict | None = None,
) -> None:
    meta = price_meta or {}
    free_trades = meta.get("free_trades")
    max_trades = meta.get("max_trades")
    team_bank = meta.get("team_bank")
    with st.expander("Trade one player", expanded=False):
        st.caption(
            f"Upgrade one spot on **{team_name}**: same G/F/C, Available only, price at or below the player you drop. "
            f"Sorted by **+Counted** for his My team slot. Needs at least +1.0 projected and +0.5 counted. "
            f"Uses **Rounds** and **Slate** above. Six-per-club and T1 cap use the other nine."
        )
        if free_trades not in (None, ""):
            try:
                free_n = int(free_trades)
            except (TypeError, ValueError):
                free_n = None
            if free_n is not None:
                cap = f" / {int(max_trades)}" if max_trades not in (None, "") else ""
                if free_n > 0:
                    st.caption(
                        f"Official account: **{free_n}{cap}** free trade(s) left — this swap uses **one** in Fantasy Challenge."
                    )
                else:
                    st.caption(
                        "Official account: **no free trades** left; a move in the app may cost a hit. "
                        "This list still respects the price cap you set here."
                    )
        if team_bank not in (None, ""):
            try:
                st.caption(f"Fantasy bank (players + coach): **{float(team_bank):.1f}** credits.")
            except (TypeError, ValueError):
                pass
        entries = saved.get("players") or []
        if not entries:
            st.info("This saved team has no players. Add or import a lineup on My team.")
            return
        window_players, _ = _apply_horizon(projections, coaches, int(horizon))
        if window_players is None or window_players.empty:
            st.info("Projections are not loaded.")
            return
        lookup = window_players.copy()
        lookup["_pid"] = lookup["player_id"].map(_pid)
        labels: dict[str, str] = {}
        for entry in entries:
            pid = _pid(entry.get("player_id"))
            row = lookup[lookup["_pid"] == pid]
            if row.empty:
                name = pid
                labels[f"{name} (not on this slate)"] = pid
                continue
            info = row.iloc[0]
            name = info.player_name if hasattr(info, "player_name") else info["player_name"]
            pos = info.position_group
            price = info.price
            proj = info.projected
            price_text = "—" if pd.isna(price) else f"{float(price):.1f}"
            proj_text = "—" if pd.isna(proj) else f"{float(proj):.1f}"
            labels[f"{name} · {pos} · {price_text} cr · {proj_text} proj"] = pid
        if not labels:
            st.warning("No players on this saved team.")
            return
        choice = st.selectbox("Player to trade out", list(labels), key="trade_out_pick")
        outgoing_id = labels[choice]
        if st.button("Find upgrades", key="trade_find_upgrades"):
            records = trade_records(window_players, day)
            outcome = suggest_trade_upgrades(
                outgoing_id,
                saved_ids,
                records,
                saved_players=entries,
            )
            st.session_state["trade_result"] = outcome
        outcome = st.session_state.get("trade_result")
        if not outcome:
            return
        outgoing = outcome.get("outgoing")
        if outgoing and _pid(outgoing.get("player_id")) != _pid(outgoing_id):
            return
        if outcome.get("message") and not outcome.get("candidates"):
            st.warning(outcome["message"])
            return
        candidates = outcome.get("candidates") or []
        if outgoing:
            slot = outcome.get("slot_label") or "slot"
            counted = outcome.get("outgoing_counted")
            counted_text = ""
            if counted is not None:
                counted_text = f", {float(counted):.1f} counted as {slot}"
            st.caption(
                f"Trading out **{outgoing['player_name']}** ({outgoing['position_group']}, "
                f"{float(outgoing['price']):.1f} credits, {float(outgoing['projected']):.1f} projected{counted_text})."
            )
        if not candidates:
            if outcome.get("message"):
                st.warning(outcome["message"])
            return
        frame = pd.DataFrame(candidates)
        bands = _bands(
            window_players,
            ["projected", "delta_projected", "delta_counted", "opp_factor", "expected_minutes"],
        )
        st.dataframe(
            _paint(
                _trade_view(frame),
                frame,
                bands,
                {
                    "projected": "Projected",
                    "delta_projected": "+Proj",
                    "delta_counted": "+Counted",
                    "opp_factor": "Opp factor",
                    "expected_minutes": "Exp min",
                },
            ),
            hide_index=True,
            width="stretch",
        )
        freed = frame["credit_freed"].fillna(0) if "credit_freed" in frame.columns else None
        freed_note = ""
        if freed is not None and (freed > 0).any():
            best = float(freed.max())
            freed_note = f" Up to **{best:.1f}** credits returned to bank on the cheapest pick."
        st.caption(
            f"Top {len(candidates)} upgrade(s) by +Counted (min +1.0 proj, +0.5 counted).{freed_note} {COLOR_NOTE}"
        )


def _show_unavailable(projections: pd.DataFrame, day) -> None:
    left_out = (
        projections[projections["availability"] != "available"].copy()
        if "availability" in projections.columns
        else projections.iloc[0:0]
    )
    if day is not None and not left_out.empty and "game_date" in left_out.columns:
        local = pd.to_datetime(left_out["game_date"], utc=True, errors="coerce").dt.tz_convert("Europe/Athens")
        left_out = left_out[local.dt.normalize() == day]
    st.subheader(f"Unavailable players ({len(left_out)})")
    if left_out.empty:
        st.caption("No out or unconfirmed players on this slate.")
        return
    left_out = left_out.sort_values("projected", ascending=False, na_position="last")
    st.dataframe(_styled_board(left_out, projections), width="stretch")
    st.caption("These players are Out or not confirmed, so they are not used in the squad.")


def _page_best(data) -> None:
    st.subheader("Best team")
    st.caption(
        "Type the credits you have. Ten players are chosen from published prices, and the coach is chosen the same way among coaches with typed credits. "
        "Select a saved team to see who would come in and who would go out after the suggestion. "
        "Each round's projection already includes that opponent, home or away, and win chance (the same matchup used on Matchup). Opponent G/F/C is the game pie versus the league, not one star cloned onto every player. "
        "A player who has played this season is scored from this season only. Last season is used only when he has no game yet. "
        "Out and unconfirmed players are left out. If someone just went out (same games played as his club), his minutes go to remaining Available teammates (60% same position). If he already missed games in the sample, those averages already include the extra time, so it is not added again. When he returns, teammate minutes go back toward normal. "
        "The bench is players expected to play at least 15 minutes, with one center kept off the starting five. "
        "Credits left after the starters are spent on a same-position upgrade so unused budget stays small. "
        "Each tip day keeps a player when someone with minutes is available. "
        "At most six of the ten play on T1 (the first tip day) so T2 and T3 players are there to replace a low T1 score after that day. "
        "Pick the saved team, changes, and credits, then press Start best team. Opening this page does not start the picker."
    )
    _show_columns(BEST_COLUMNS + COACH_COLUMNS)
    book = load_book(ROOT)
    names = list(book["teams"])
    active = book["active"] if book["active"] in names else names[0]
    if st.session_state.get("_best_follow_active") != active:
        st.session_state["best_saved_team"] = active
        st.session_state["_best_follow_active"] = active
    if st.session_state.get("best_saved_team") not in names:
        st.session_state["best_saved_team"] = active
    team_name = st.selectbox("Saved team", names, key="best_saved_team")
    days = slate_days(data.projections)
    options = {"Full next round": None}
    for day in days:
        options[day.strftime("%a %d %b")] = day
    budget_col, round_col = st.columns(2)
    price_meta = load_price_meta(ROOT)
    bank_value = None
    raw_bank = price_meta.get("team_bank")
    if raw_bank not in (None, ""):
        try:
            bank_value = float(raw_bank)
        except (TypeError, ValueError):
            bank_value = None
    default_budget = float(bank_value) if bank_value is not None else 100.0
    if "best_budget" not in st.session_state:
        st.session_state["best_budget"] = default_budget
        if bank_value is not None:
            st.session_state["_best_budget_token"] = f"bank:{round(bank_value, 1)}"
    elif bank_value is not None:
        bank_token = f"bank:{round(bank_value, 1)}"
        if st.session_state.get("_best_budget_token") != bank_token:
            st.session_state["best_budget"] = bank_value
            st.session_state["_best_budget_token"] = bank_token
    with budget_col:
        squad_budget = st.number_input(
            "Credits",
            min_value=20.0,
            max_value=200.0,
            step=0.5,
            key="best_budget",
            help="Full squad budget including the coach. Prefills from your Fantasy Challenge bank when the official login is configured.",
        )
        if bank_value is not None:
            bank_name = price_meta.get("team_bank_name") or "Fantasy Challenge"
            st.caption(f"Bank from {bank_name}: {bank_value:.1f} (players + coach).")
    with round_col:
        horizon = st.selectbox("Rounds", [1, 2, 3, 4, 5], index=0, key="best_rounds")
    credits = load_credits(ROOT)
    saved = book["teams"][team_name]
    official_coach_prices = map_coach_prices(data.coaches, ensure_prices(ROOT))
    coach_prices = {str(key): float(value) for key, value in official_coach_prices.items() if float(value) > 0}
    for key, value in (credits.get("coaches") or {}).items():
        if float(value) > 0:
            coach_prices[str(key)] = float(value)
    saved_coach_id = saved.get("coach_id")
    saved_coach_price = saved.get("coach_price")
    if saved_coach_id and (saved_coach_price in (None, "") or float(saved_coach_price or 0) <= 0):
        saved_coach_price = coach_prices.get(str(saved_coach_id))
    if saved_coach_id and saved_coach_price and float(saved_coach_price) > 0:
        coach_prices.setdefault(str(saved_coach_id), float(saved_coach_price))
    coach_rows = data.coaches.sort_values("projected", ascending=False, na_position="last").copy()
    if coach_rows.empty:
        st.caption("No coaches on this slate.")
    else:
        editor = pd.DataFrame(
            {
                "coach_id": coach_rows["coach_id"].astype(str),
                "Coach": coach_rows["coach_name"],
                "Team": coach_rows["team_name"],
                "Projected": coach_rows["projected"].map(lambda value: None if pd.isna(value) else round(float(value), 1)),
                "Credits": coach_rows["coach_id"].astype(str).map(lambda ident: coach_prices.get(ident, 0.0)),
            }
        ).set_index("coach_id")
        with st.expander("Coach credits", expanded=not coach_prices):
            if official_coach_prices:
                st.caption(
                    "Credits come from the official Fantasy Challenge list. Edit a row only to override. "
                    "Best team skips anyone at 0, then picks the coach that leaves the strongest ten players inside the remaining budget."
                )
            else:
                st.caption(
                    "Type each coach's credits. Configure your Fan ID and Refresh data to load official coach prices. "
                    "Best team skips anyone at 0, then picks the coach the same way it picks players."
                )
            edited = st.data_editor(
                editor,
                width="stretch",
                disabled=["Coach", "Team", "Projected"],
                column_config={
                    "Credits": st.column_config.NumberColumn(min_value=0.0, max_value=40.0, step=0.5, format="%.1f"),
                },
                key="best_coach_credits",
            )
            typed = {}
            for ident, row in edited.iterrows():
                value = float(row["Credits"] or 0)
                if value > 0:
                    typed[str(ident)] = value
            official_rounded = {
                str(key): round(float(value), 1)
                for key, value in official_coach_prices.items()
                if float(value) > 0
            }
            rounded = {key: round(float(value), 1) for key, value in typed.items()}
            # Persist only overrides that differ from the official list.
            overrides = {
                key: value
                for key, value in rounded.items()
                if official_rounded.get(key) != value
            }
            stored = {
                str(key): round(float(value), 1)
                for key, value in (credits.get("coaches") or {}).items()
                if float(value) > 0
            }
            if overrides != stored:
                credits["coaches"] = overrides
                save_credits(ROOT, credits)
            coach_prices = dict(typed)
            if saved_coach_id and saved_coach_price and float(saved_coach_price) > 0:
                coach_prices.setdefault(str(saved_coach_id), float(saved_coach_price))
    free_trades = price_meta.get("free_trades")
    max_trades = price_meta.get("max_trades")
    try:
        free_trades = None if free_trades in (None, "") else int(free_trades)
    except (TypeError, ValueError):
        free_trades = None
    try:
        max_trades = None if max_trades in (None, "") else int(max_trades)
    except (TypeError, ValueError):
        max_trades = None
    suggested_changes = suggested_changes_label(free_trades)
    change_options = change_radio_options(free_trades)
    if suggested_changes is not None and suggested_changes not in change_options:
        suggested_changes = change_options[0] if change_options else None
    if suggested_changes is not None:
        trades_token = f"trades:{suggested_changes}:{max_trades}:{','.join(change_options)}"
        if "best_change_pick" not in st.session_state:
            st.session_state["best_change_pick"] = suggested_changes
            st.session_state["_best_change_token"] = trades_token
        elif st.session_state.get("_best_change_token") != trades_token:
            st.session_state["best_change_pick"] = suggested_changes
            st.session_state["_best_change_token"] = trades_token
    elif "best_change_pick" not in st.session_state:
        st.session_state["best_change_pick"] = "2" if "2" in change_options else change_options[0]
    if st.session_state.get("best_change_pick") not in change_options:
        fallback = suggested_changes or ("2" if "2" in change_options else change_options[0])
        st.session_state["best_change_pick"] = fallback
    change_col, mode_col = st.columns([3, 1])
    with change_col:
        change_label = st.radio(
            "Changes",
            change_options,
            horizontal=True,
            key="best_change_pick",
        )
    with mode_col:
        change_mode = st.radio(
            "Mode",
            ["Exact", "Up to"],
            horizontal=True,
            key="best_change_mode",
            disabled=change_label == "All",
            help="Exact: bring in exactly that many new players. Up to: Best team may use fewer if that scores higher.",
        )
    exact_changes = change_mode == "Exact"
    if free_trades is not None:
        cap = f" / {max_trades}" if max_trades is not None else ""
        st.caption(
            f"Official free trades left: {free_trades}{cap} "
            f"(Fantasy Challenge account — not the local saved team)."
        )
        if free_trades <= 0:
            st.caption("No free trades left on the official team; only All is offered for a full local rebuild.")
        elif free_trades < 4:
            hidden = [str(n) for n in range(free_trades + 1, 5)]
            st.caption(
                f"Hidden above your free trades: {', '.join(hidden)}. "
                "All remains available for a full local rebuild."
            )
    changes = 10 if change_label == "All" else int(change_label)
    include_coach = st.checkbox(
        "Include coach in changes",
        value=False,
        key="best_change_coach",
        help="Checked: Best team may replace the coach, among those with typed credits. "
        "Unchecked: keep the coach from the selected saved team.",
        disabled=not bool(saved_coach_id),
    )
    lock_coach = bool(saved_coach_id) and not include_coach
    saved_ids = [_pid(entry.get("player_id")) for entry in saved.get("players", []) if entry.get("player_id")]
    use_saved = int(changes) < 10 and bool(saved_ids)
    held_ids = saved_ids if use_saved else []
    day = None
    if int(horizon) == 1:
        choice = st.selectbox("Slate", list(options), key="best_slate")
        day = options[choice]
    else:
        choice = f"{int(horizon)} rounds"
        st.caption("The day filter applies to one round. A longer window uses every club's next games.")
    if changes >= 10:
        st.caption(f"All: a new squad. Coming in and Going out are still compared with {team_name}.")
    elif not saved_ids:
        st.caption(
            f"{team_name} has no players, so All is used and the squad is built from scratch. "
            "Import or add a lineup on My team to use limited Changes."
        )
    elif exact_changes:
        st.caption(f"From {team_name}: keep {10 - int(changes)} players, bring in exactly {int(changes)} new.")
        st.caption(
            "Coming in / Going out compares to this local saved team. "
            "Use Import on My team if you want it to match Fantasy Challenge."
        )
    else:
        st.caption(f"From {team_name}: up to {int(changes)} new players come in — Best team uses fewer if that scores higher.")
        st.caption(
            "Coming in / Going out compares to this local saved team. "
            "Use Import on My team if you want it to match Fantasy Challenge."
        )
    if lock_coach:
        st.caption(f"The coach from {team_name} stays. Check Include coach in changes to let Best team pick another.")
    elif include_coach:
        st.caption("The coach is included in the update: Best team picks among coaches with typed credits.")
    _trade_suggestions_box(
        team_name,
        saved,
        saved_ids,
        data.projections,
        data.coaches,
        int(horizon),
        day,
        price_meta,
    )
    st.markdown(
        "<style>.st-key-start_best_team button {background-color:#2e7d32 !important;border-color:#2e7d32 !important;color:#ffffff !important;}</style>",
        unsafe_allow_html=True,
    )
    started = st.button("Start best team", type="primary", key="start_best_team")
    projections = data.projections
    fingerprint = (
        choice,
        int(horizon),
        use_saved,
        team_name,
        int(changes),
        bool(exact_changes),
        tuple(sorted(held_ids)),
        tuple(sorted(saved_ids)),
        round(float(squad_budget), 1),
        tuple(sorted((key, round(float(value), 1)) for key, value in coach_prices.items())),
        bool(include_coach),
        bool(lock_coach),
        str(saved_coach_id or ""),
        "start-button",
        len(projections),
        round(float(pd.to_numeric(projections["projected"], errors="coerce").sum()), 1),
        tuple(
            sorted(
                projections.loc[
                    projections["availability"].fillna("available") != "available",
                    "player_id",
                ].astype(str)
            )
        )
        if "availability" in projections.columns
        else (),
    )
    if started:
        with st.spinner("Building the best squad..."):
            st.session_state["best_result"] = build_best_team(
                projections,
                data.coaches,
                budget=float(squad_budget),
                day=day,
                horizon=int(horizon),
                changes=int(changes),
                held_ids=held_ids,
                coach_id=str(saved_coach_id) if lock_coach else None,
                coach_price=float(saved_coach_price or 0) if lock_coach else 0.0,
                coach_prices=coach_prices,
                lock_coach=lock_coach,
                exact=exact_changes,
            )
        st.session_state["best_key"] = fingerprint
    result = st.session_state.get("best_result")
    if not result:
        st.caption("Pick the saved team, changes, credits, and slate, then press Start best team.")
        return
    if st.session_state.get("best_key") != fingerprint:
        st.caption(
            "The saved team or settings changed. The last suggestion is hidden so it is not mixed with the new lineup. "
            "Press Start best team to rebuild."
        )
        return
    players_frame = result.get("players")
    if result.get("message"):
        st.warning(result["message"])
        if players_frame is None or getattr(players_frame, "empty", True):
            return
    players = _mark_moves(_with_player_status(result["players"], projections), saved_ids)
    coach_price = float(result.get("coach_price") or 0)
    summary = st.columns(4)
    window = int(result.get("horizon") or 1)
    summary[0].metric("Projected round" if window == 1 else f"Projected {window} rounds", f"{result['total']:.1f}")
    summary[1].metric("Credits", f"{result['price_sum']:.1f} / {float(squad_budget):.1f}")
    player_credits = float(result["price_sum"]) - coach_price
    st.caption(
        f"Players {player_credits:.1f} + coach {coach_price:.1f} = {result['price_sum']:.1f} of {float(squad_budget):.1f}."
    )
    starters = players[players["slot"].isin(["Captain", "Starter"])]
    shape = "-".join(str(int((starters["position_group"] == position).sum())) for position in POSITIONS)
    summary[2].metric("Formation (G-F-C)", shape)
    used = result.get("changes_used")
    summary[3].metric("Changes used", "—" if used is None else str(used))
    if use_saved and used is not None and int(changes) < 10 and int(used) > int(changes):
        st.caption(
            f"No legal squad stayed inside {int(changes)} changes "
            "(Out or unconfirmed players on the saved team still have to be replaced). "
            f"This squad uses {int(used)}."
        )
    if result["coach_name"]:
        venue = result["coach_home_away"] or ""
        opponent = result["coach_opponent"] or "the opponent"
        if window == 1:
            coach_label = "Best coach" if include_coach or not lock_coach else "Coach"
            coach_text = (
                f"{coach_label} {result['coach_name']} ({result['coach_team']}) vs {opponent} ({venue}): "
                f"{result['coach_points']:.1f} projected points."
            )
        else:
            coach_label = "Best coach" if include_coach or not lock_coach else "Coach"
            coach_text = (
                f"{coach_label} {result['coach_name']} ({result['coach_team']}) over {window} rounds: "
                f"{result['coach_points']:.1f} projected points. Next game vs {opponent} ({venue})."
            )
        st.write(coach_text)
        detail = data.coaches[
            (data.coaches["coach_name"] == result["coach_name"])
            & (data.coaches["team_name"] == result["coach_team"])
        ]
        if not detail.empty:
            _players, adjusted_coaches = _apply_horizon(data.projections, data.coaches, window)
            detail = adjusted_coaches[
                (adjusted_coaches["coach_name"] == result["coach_name"])
                & (adjusted_coaches["team_name"] == result["coach_team"])
            ]
            if not detail.empty:
                st.dataframe(_styled_coaches(detail, adjusted_coaches), hide_index=True, width="stretch")
    window_players, _window_coaches = _apply_horizon(data.projections, data.coaches, window)
    bands = _bands(window_players, ["projected", "points_per_credit", "expected_minutes"])
    if "projected" in bands:
        bands["counted"] = bands["projected"]
    st.dataframe(
        _paint_status(
            _paint(_best_view(players), players, bands, {
                "projected": "Projected",
                "expected_minutes": "Exp min",
                "points_per_credit": "Points per credit",
                "counted": "Counted",
            }),
            players,
        ),
        hide_index=True,
        width="stretch",
    )
    if "turn" in players.columns and players["turn"].astype(str).str.len().gt(0).any():
        counts = players["turn"].fillna("").value_counts()
        parts = [f"{counts.get(label, 0)} {label}" for label in ("T1", "T2", "T3") if counts.get(label, 0)]
        if parts:
            extra = ""
            if int(counts.get("T1", 0)) > 0 and (int(counts.get("T2", 0)) + int(counts.get("T3", 0))) > 0:
                extra = " T2/T3 can replace a low T1 score after that day."
            st.caption("Turns: " + ", ".join(parts) + "." + extra)
    _show_squad_diff(team_name, saved, players, projections, data.coaches, result)
    _show_unavailable(data.projections, day)
    st.subheader("Copy to My team")
    copy_col, name_col = st.columns(2)
    with copy_col:
        target = st.selectbox("Existing team", names, index=names.index(team_name), key="copy_target")
    with name_col:
        fresh = st.text_input("New team name", key="copy_new_name")
    if st.button("Copy this squad", key="copy_best"):
        destination = " ".join(fresh.split()) or target
        copied_players = []
        for row in result["players"].itertuples(index=False):
            slot, captain = SAVED_SLOT.get(row.slot, ("bench", False))
            copied_players.append(
                {
                    "player_id": row.player_id,
                    "slot": slot,
                    "captain": captain,
                    "price": None,
                }
            )
        save_named_squad(
            ROOT,
            destination,
            {
                "players": copied_players,
                "coach_id": result.get("coach_id"),
                "coach_price": _stored_price(result.get("coach_price")),
            },
        )
        st.success(f"Copied into {destination}. Open My team to see it.")
    st.caption(f"{COLOR_NOTE} {STATUS_NOTE}")


def _cache_token() -> tuple[float, ...]:
    """Fingerprint of the on-disk data, so the cached build invalidates on change."""
    paths = [
        cache_dir(ROOT) / "meta.json",
        price_cache_path(ROOT),
        injury_cache_path(ROOT),
    ]
    return tuple(path.stat().st_mtime if path.exists() else 0.0 for path in paths) + (float(FORM_GAMES), 13.0)


@st.cache_data(show_spinner=False)
def _load_dashboard(token: tuple[float, ...], season: str | None = None):
    """Load the cache, prices and injuries and build the projection.

    Streamlit reruns the whole script on every widget interaction; wrapping the
    expensive pipeline here means it only recomputes when `token` (the data-file
    mtimes) changes or the Refresh button clears the cache, not on every click.
    Returns (DashboardData | None, warnings).
    """
    warnings: list[str] = []
    cache = load_cache(ROOT)
    if cache is None:
        return None, warnings
    try:
        cache["prices"] = ensure_prices(ROOT)
    except Exception as exc:
        cache["prices"] = pd.DataFrame()
        warnings.append(f"Fantasy prices could not be loaded ({exc}).")
    try:
        cache["injuries"] = ensure_injuries(ROOT)
    except Exception as exc:
        cache["injuries"] = pd.DataFrame()
        warnings.append(
            f"Injury report could not be loaded ({exc}). Every player is treated as available."
        )
    return build_dashboard(cache, season), warnings


def main() -> None:
    st.set_page_config(page_title="Euroleague Fantasy", layout="wide")
    st.title("Euroleague Fantasy")
    st.caption(
        "Personal dashboard for the EuroLeague Fantasy Challenge. "
        "Stats come from the public Euroleague feeds. Player credits come from your Fantasy Challenge login when configured, otherwise the public list."
    )
    page = st.sidebar.radio("Page", ["Player board", "Matchup", "Best team", "My team"], key="page")
    if st.sidebar.button("Refresh data", key="refresh"):
        note = st.empty()
        bar = st.progress(0.0)

        def progress(message: str, fraction: float | None = None) -> None:
            note.write(message)
            if fraction is not None:
                bar.progress(min(max(float(fraction), 0.0), 1.0))

        refresh_cache(ROOT, progress=progress)
        st.cache_data.clear()
        st.rerun()

    data, load_warnings = _load_dashboard(_cache_token())
    if data is None:
        st.info(
            "No box scores cached yet. Use Refresh data in the sidebar. "
            "The first run downloads last season and takes a few minutes."
        )
        st.stop()
    for message in load_warnings:
        st.sidebar.warning(message)

    upcoming = data.projections["round"].dropna()
    if not upcoming.empty:
        st.sidebar.write(f"Next round: {int(upcoming.iloc[0])}")
    st.sidebar.write(f"Season {data.current_season}, history {data.prior_season}")
    priced = int(data.projections["price"].notna().sum()) if "price" in data.projections else 0
    st.sidebar.write(f"Prices loaded: {priced}")
    meta = load_price_meta(ROOT)
    if meta.get("source") == "official":
        parts = ["Credits are the official Fantasy Challenge quotations from your local login."]
        if meta.get("coaches"):
            parts.append(f"{int(meta['coaches'])} coaches priced.")
        if meta.get("team_bank") not in (None, ""):
            parts.append(f"Bank {float(meta['team_bank']):.1f}.")
        if meta.get("free_trades") not in (None, ""):
            free = int(meta["free_trades"])
            if meta.get("max_trades") not in (None, ""):
                parts.append(f"Free trades {free}/{int(meta['max_trades'])}.")
            else:
                parts.append(f"Free trades {free}.")
        st.sidebar.caption(" ".join(parts))
    elif fantasy_login(ROOT):
        official_error = str(meta.get("official_error") or "").strip()
        if official_error:
            st.sidebar.warning(official_error)
        else:
            st.sidebar.warning(
                "Official login is configured, but the last successful price file was the public list. Press Refresh data."
            )
    else:
        st.sidebar.caption(
            f"Credits are the public givemestats list. Copy {example_path(ROOT).name} to "
            f"{credentials_path(ROOT).name} and add your EuroLeague Fan ID email and password, then Refresh data."
        )
    if "availability" in data.projections.columns:
        out = int((data.projections["availability"] == "out").sum())
        unsure = int((data.projections["availability"] == "uncertain").sum())
        st.sidebar.write(f"Injuries: {out} out, {unsure} unconfirmed")

    if page == "Player board":
        _page_board(data)
    elif page == "Matchup":
        _page_matchup(data)
    elif page == "Best team":
        _page_best(data)
    else:
        _page_squad(data)


main()

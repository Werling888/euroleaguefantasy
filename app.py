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
from src.injuries import ensure_injuries, injury_cache_path
from src.optimize import _apply_horizon, build_best_team, slate_days
from src.prices import ensure_prices, price_cache_path
from src.project import build_dashboard
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
    "**Pos** — G guard, F forward, or C center.",
    "**Status** — Available when he is confirmed to play. Yellow means it is not confirmed: Expected, Questionable, Game-time, Doubtful, or Uncertain. Out means he will not play. Players missing from the injury report are Available.",
    "**Note** — the injury comment. Blank when the player is Available.",
    "**GP** — games behind the averages.",
    "**Min** — average minutes in those games.",
    "**Exp min** — minutes expected next game: 60% of the last 5 games and 40% of the season. Projected is that time times PIR per minute, then the opponent, venue, and win bonus.",
    "**Fpts/g** — fantasy points per game. A win is PIR plus 10%; a loss is PIR.",
    "**Last 5** — average fantasy points over the last five games.",
    "**Per 36** — fantasy points scaled to 36 minutes.",
    "**Volatility** — how much the fantasy score swings. A low number is steadier, so it is green.",
    "**Price** — published Fantasy Challenge credits.",
    "**Points per credit** — Projected divided by Price.",
    "**Projected** — expected fantasy points for the next game: recent form, times the opponent factor, times the home or away split, times a 10% win bonus weighted by Win %.",
    "**Floor** / **Ceiling** — low and high outcomes from the last eight games, adjusted only for the opponent.",
    "**Opponent** — next rival.",
    "**H/A** — Home or Away for that game.",
    "**Win %** — chance the club wins the next game.",
    "**Opp factor** — fantasy points this rival allows to the position, divided by the league average. Above 1 is an easier matchup.",
    "**Form** — where the baseline comes from: 2025-26, 2026-27, Blend until eight games this season, or Pos. avg when the player has no history.",
]
COACH_COLUMNS = [
    "**Coach** — the club's head coach. The same GP, Opponent, H/A, Win %, and Form titles apply.",
    "Coach **Fpts/g** and **Last 5** are official margin points, not PIR. Win by 1–10 or in overtime is +10, 11–20 is +20, 21+ is +25. Loss by 1–10 or overtime is −5, 11–20 is −10, 21+ is −20.",
    "**Avg margin** — average score difference in the sample. Positive means the club won by that many points on average.",
    "Coach **Projected** is the chance-weighted margin score for the next game. It counts in full, with no captain or bench multiplier.",
    "Coach **Floor** and **Ceiling** are the low and high margin scores from the last eight games.",
    "**Form** No games means this coach has no EuroLeague results in the cache, so only the next-game projection is filled in.",
]
MATCHUP_COLUMNS = [
    "**Next opponent** — the club and whether the game is home or away.",
    "**Tip** — start time in Athens.",
    "**Win chance** — same idea as Win %.",
    "**Opponent allows** — fantasy points this defense gives up to that position.",
    "**League allows** — typical fantasy points allowed to that position.",
    "**Factor** — Opponent allows divided by League allows. Above 1 is an easier matchup.",
]
BEST_COLUMNS = [
    "**Season data** — Current season projects from this season's games only. Last season projects from last season's games only. Opponent, venue, and win chance come from the same season.",
    "**Slate** — the full next round, or only the clubs that play on the chosen day.",
    "**Coach price** — credits for the coach. They are not on the published player list, so 0 leaves all 100 credits for players.",
    "**Projected round** — squad total after captain, sixth-man, and bench multipliers, plus the coach. With more than one round, this is the sum over that window.",
    "**Rounds** — how many upcoming rounds to plan for. Each round uses that game's opponent, venue, and win chance. Form stays at today's numbers.",
    "**Changes** — shown after you press Use. Pick 1, 2, 3, or 4 players from the named team to replace, or All to rebuild the whole squad.",
    "**Move** — Keep means the player stays from that team. New means a change was spent.",
    "**Credits** — the budget you type. Player prices plus the coach price must stay inside that number. The usual Fantasy Challenge budget is 100.",
    "**Formation (G-F-C)** — guards, forwards, and centers in the starting five. Legal shapes are 2-2-1, 1-2-2, 2-1-2, 1-3-1, and 3-1-1.",
    "**Status** — only Available players are chosen. Out and unconfirmed players are left out.",
    "**Note** — why a player on the left-out list is not confirmed.",
    "**Slot** — Captain counts double, Starter and Sixth count in full, Bench counts at half.",
    "**Day** — tip day in Athens. One, two, or three days. Each day keeps someone, then the other spots follow the projections.",
    "**Exp min** — minutes expected in each game of the window. The projection is that time times PIR per minute. Reserves need about 15.",
    "**Counted** — Projected times that slot multiplier.",
    "**Projected** — expected fantasy points for the next game, before the slot multiplier.",
    "**Price** and **Points per credit** — published credits, and Projected divided by that price.",
]
SQUAD_COLUMNS = [
    "**Status** — Available, a yellow unconfirmed status, or Out. Best team will not use anyone who is not Available.",
    "**Note** — the injury comment for players who are not Available.",
    "**Slot** — starter, sixth, or bench. Five starters, one sixth man, four bench.",
    "**Captain** — one starter. That player counts double.",
    "**Price** — published credits. It counts toward the 100-credit budget.",
    "**Points per credit** — Projected divided by Price.",
    "**Projected** — expected fantasy points for the next game, before the slot multiplier.",
    "**Counted** — Projected times the slot multiplier.",
    "**Coach price** — typed by you. Coach credits are not on the published player list.",
    "**Projected round** — lineup total plus the coach.",
]


def _show_columns(lines: list[str]) -> None:
    with st.expander("Column guide"):
        st.markdown("\n".join(f"- {line}" for line in lines))


def _round(value, digits=1):
    if pd.isna(value):
        return None
    return round(float(value), digits)


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
        "volatility": "Volatility",
        "price": "Price",
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
    return view[keep].rename(columns=rename)


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
            ["Points per credit", "Projected", "Per 36", "Last 5", "Minutes"],
            key="board_sort",
        )
    search_col, minutes_col, status_col = st.columns([2, 1, 1])
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
    sort_column = {
        "Points per credit": "points_per_credit",
        "Projected": "projected",
        "Per 36": "fantasy_per36",
        "Last 5": "last5_fantasy",
        "Minutes": "minutes",
    }[sort]
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
    st.caption("Next-game fantasy points for the active roster. Filter by club, position, venue, or minutes.")
    _show_columns(PLAYER_COLUMNS + COACH_COLUMNS)
    filtered = _filter_board(data.projections)
    st.dataframe(_styled_board(filtered, data.projections), hide_index=True, width="stretch")
    st.caption(
        f"{len(filtered)} players. Leave Team on All teams to see the league, or pick one club. {COLOR_NOTE} {STATUS_NOTE}"
    )
    st.subheader("Coaches")
    coaches = _coaches_for(data.coaches)
    st.dataframe(_styled_coaches(coaches, data.coaches), hide_index=True, width="stretch")
    st.caption(f"{len(coaches)} coaches. Colors compare coaches with each other. {COLOR_NOTE}")


def _page_matchup(data) -> None:
    st.subheader("Matchup")
    st.caption("One club’s next game, how soft the opponent is by position, and that club’s players.")
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
    table = defense[["position_group", "opp_allowed", "league_allowed", "opp_factor"]].copy()
    numeric = table.copy()
    table["opp_allowed"] = table["opp_allowed"].map(lambda value: _round(value, 1))
    table["league_allowed"] = table["league_allowed"].map(lambda value: _round(value, 1))
    table["opp_factor"] = table["opp_factor"].map(lambda value: _round(value, 2))
    table = table.rename(
        columns={
            "position_group": "Pos",
            "opp_allowed": "Opponent allows",
            "league_allowed": "League allows",
            "opp_factor": "Factor",
        }
    )
    defense_bands = _bands(data.defense, ["opp_allowed", "opp_factor"])
    painted = _paint(
        table,
        numeric.rename(columns={"opp_allowed": "opp_allowed", "opp_factor": "opp_factor"}),
        defense_bands,
        {"opp_allowed": "Opponent allows", "opp_factor": "Factor"},
    )
    st.dataframe(painted, hide_index=True, width="stretch")
    st.caption("Factor above 1 means this opponent has allowed more fantasy points than a typical defense. " + COLOR_NOTE)
    coach = _coaches_for(data.coaches, team_code)
    if not coach.empty:
        st.subheader("Coach")
        st.dataframe(_styled_coaches(coach, data.coaches), hide_index=True, width="stretch")
    players = data.projections[data.projections["team_code"] == team_code]
    position = st.selectbox("Position", ["All positions"] + POSITIONS, key="matchup_position")
    if position != "All positions":
        players = players[players["position_group"] == position]
    players = players.sort_values("points_per_credit", ascending=False, na_position="last")
    st.dataframe(_styled_board(players, data.projections), hide_index=True, width="stretch")


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
        editor = players[
            [
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
        ].copy()
        edited = st.data_editor(
            editor,
            hide_index=True,
            width="stretch",
            key=f"squad_editor_{active}",
            disabled=[
                "player_id",
                "player_name",
                "team_name",
                "position_group",
                "status_label",
                "injury_note",
                "price",
                "per_credit",
                "projected",
                "points",
            ],
            column_config={
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
            },
        )
        if "availability" in players.columns:
            blocked = players[players["availability"] != "available"]
            if not blocked.empty:
                names = ", ".join(
                    f"{row.player_name} ({row.status_label})" for row in blocked.itertuples(index=False)
                )
                st.warning(f"Not confirmed to play: {names}.")
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
        coach_price = st.number_input(
            "Coach price",
            min_value=0.0,
            max_value=100.0,
            value=squad.get("coach_price"),
            step=0.5,
            key=f"coach_price_{active}",
        )
        if st.form_submit_button("Save coach"):
            squad["coach_id"] = coach_options[coach_label]
            squad["coach_price"] = _stored_price(coach_price)
            save_squad(ROOT, squad)
            st.rerun()

    scored = score_squad(load_squad(ROOT), projections, data.coaches)
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
    summary[3].metric("Credits", "—" if price_sum is None else f"{price_sum:.1f} / {BUDGET:.0f}")
    coach = scored["coach"]
    if coach is not None and scored["coach_points"] is not None:
        coach_value = points_per_credit(scored["coach_points"], scored["coach_price"])
        value_text = "" if coach_value is None else f" Points per credit: {coach_value:.2f}."
        st.write(
            f"Coach {coach.coach_name} vs {coach.opponent_name} ({coach.home_away}): "
            f"{scored['coach_points']:.1f} projected points.{value_text}"
        )
        detail = data.coaches[data.coaches["coach_id"] == coach.coach_id]
        if not detail.empty:
            st.dataframe(_styled_coaches(detail, data.coaches), hide_index=True, width="stretch")
    for message in scored["messages"]:
        st.warning(message)
    if not scored["messages"] and len(scored["players"]) == 10 and coach is not None:
        st.success("Roster shape matches the Fantasy Challenge: 4 guards, 4 forwards, 2 centers, and a coach.")


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
    for column, digits in (("price", 1), ("projected", 1), ("points_per_credit", 2), ("counted", 1), ("expected_minutes", 1)):
        view[column] = view[column].map(lambda value, digits=digits: _round(value, digits))
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
        "expected_minutes": "Exp min",
        "price": "Price",
        "projected": "Projected",
        "points_per_credit": "Points per credit",
        "counted": "Counted",
        "move": "Move",
    }
    if "move" in view.columns and not view["move"].notna().any():
        rename.pop("move")
    rename = {key: label for key, label in rename.items() if key in view.columns}
    return view[list(rename)].rename(columns=rename)


def _page_best(data) -> None:
    st.subheader("Best team")
    st.caption(
        "Type the credits you have. The coach and the ten players are chosen inside that number, using published player prices. "
        "Each round uses that opponent, home or away, and win chance. "
        "Out and unconfirmed players are left out. "
        "The bench is players expected to play at least 15 minutes, with one center kept off the starting five. "
        "Credits left after the starters go to the bench player who adds the most points. "
        "Each tip day keeps a player when someone with minutes is available. The other spots are not split in half."
    )
    _show_columns(BEST_COLUMNS + COACH_COLUMNS)
    season_label = st.radio(
        "Season data",
        ["Current season", "Last season"],
        index=0,
        horizontal=True,
        key="best_season",
        help="Current season uses only this season's games. Players with no game yet are left out. "
        "Last season uses only last season's games.",
    )
    season = data.current_season if season_label == "Current season" else data.prior_season
    blended = data
    data = _load_dashboard(_cache_token(), season)[0]
    played = data.projections["projected"].notna().sum()
    st.caption(f"{season_label} ({season}): {int(played)} players have a projection.")
    book = load_book(ROOT)
    names = list(book["teams"])
    team_name = st.selectbox(
        "Saved team",
        names,
        index=names.index(book["active"]),
        key="best_saved_team",
    )
    use_saved = bool(st.session_state.get("best_use_saved"))
    action_col, clear_col = st.columns(2)
    with action_col:
        if st.button(f"Use {team_name}", key="use_saved_team"):
            st.session_state["best_use_saved"] = True
            st.rerun()
    with clear_col:
        if use_saved and st.button("Build a new squad", key="ignore_saved_team"):
            st.session_state["best_use_saved"] = False
            st.rerun()
    days = slate_days(data.projections)
    options = {"Full next round": None}
    for day in days:
        options[day.strftime("%a %d %b")] = day
    budget_col, round_col, coach_col, credit_col = st.columns(4)
    with budget_col:
        squad_budget = st.number_input(
            "Credits",
            min_value=20.0,
            max_value=200.0,
            value=100.0,
            step=0.5,
            key="best_budget",
            help="The credits you have for the whole squad, coach included.",
        )
    with round_col:
        horizon = st.selectbox("Rounds", [1, 2, 3, 4, 5], index=0, key="best_rounds")
    credits = load_credits(ROOT)
    coach_rows = data.coaches.sort_values("projected", ascending=False, na_position="last")
    coach_labels = {
        f"{row.coach_name} ({row.team_name})": str(row.coach_id)
        for row in coach_rows.itertuples(index=False)
    }
    with coach_col:
        coach_label = st.selectbox("Coach", list(coach_labels) or ["No coach"], key="best_coach_pick")
    coach_id = coach_labels.get(coach_label)
    stored_coach_price = (credits.get("coaches") or {}).get(str(coach_id or ""))
    with credit_col:
        coach_price = st.number_input(
            "Coach credits",
            min_value=0.0,
            max_value=40.0,
            value=float(stored_coach_price or 0.0),
            step=0.5,
            key=f"best_coach_credits_{coach_id}",
        )
    if coach_id and float(coach_price) != float(stored_coach_price or 0.0):
        credits.setdefault("coaches", {})[str(coach_id)] = float(coach_price)
        save_credits(ROOT, credits)
    if use_saved:
        change_label = st.radio(
            "Changes",
            ["1", "2", "3", "4", "All"],
            index=1,
            horizontal=True,
            key="best_change_pick",
        )
        changes = 10 if change_label == "All" else int(change_label)
    else:
        changes = 10
    saved = book["teams"][team_name]
    held_ids = [str(entry.get("player_id")) for entry in saved.get("players", []) if entry.get("player_id")] if use_saved else []
    day = None
    if int(horizon) == 1:
        choice = st.selectbox("Slate", list(options), key="best_slate")
        day = options[choice]
    else:
        choice = f"{int(horizon)} rounds"
        st.caption("The day filter applies to one round. A longer window uses every club's next games.")
    if not use_saved:
        st.caption(f"This builds a new squad. Press Use {team_name} to start from that saved team.")
    elif not held_ids:
        st.caption(f"{team_name} has no players, so the squad is still built from scratch.")
    else:
        limit = "any number" if changes >= 10 else f"at most {int(changes)}"
        st.caption(f"Using {team_name}: {len(held_ids)} players, and {limit} can be replaced.")
    projections = data.projections
    if held_ids:
        ids = projections["player_id"].astype(str)
        known = set(ids[projections["projected"].notna()])
        other = blended.projections
        other_ids = other["player_id"].astype(str)
        fill = [
            player_id
            for player_id in held_ids
            if player_id not in known and player_id in set(other_ids[other["projected"].notna()])
        ]
        if fill:
            projections = pd.concat(
                [projections[~ids.isin(fill)], other[other_ids.isin(fill)]],
                ignore_index=True,
            )
            who = ", ".join(other.loc[other_ids.isin(fill), "player_name"].astype(str))
            st.caption(
                f"No {season_label.lower()} games yet for {who}. "
                "Their projection uses both seasons so they can stay in your squad."
            )
    fingerprint = (
        choice,
        int(horizon),
        use_saved,
        team_name,
        int(changes),
        tuple(sorted(held_ids)),
        round(float(squad_budget), 1),
        round(float(coach_price), 1),
        str(coach_id),
        "bench-upgrade",
        season,
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
    cached = st.session_state.get("best_result") or {}
    cached_players = cached.get("players")
    missing_status = cached_players is None or "status_label" not in cached_players.columns
    if st.session_state.get("best_key") != fingerprint or missing_status:
        with st.spinner("Building the best squad..."):
            st.session_state["best_result"] = build_best_team(
                projections,
                data.coaches,
                coach_price=float(coach_price),
                budget=float(squad_budget),
                day=day,
                horizon=int(horizon),
                changes=int(changes),
                held_ids=held_ids,
                coach_id=coach_id,
            )
        st.session_state["best_key"] = fingerprint
    result = st.session_state["best_result"]
    if result["message"]:
        st.warning(result["message"])
        return
    players = _with_player_status(result["players"], projections)
    summary = st.columns(4)
    window = int(result.get("horizon") or 1)
    summary[0].metric("Projected round" if window == 1 else f"Projected {window} rounds", f"{result['total']:.1f}")
    summary[1].metric("Credits", f"{result['price_sum']:.1f} / {float(squad_budget):.1f}")
    player_credits = float(result["price_sum"]) - float(coach_price or 0)
    st.caption(
        f"Players {player_credits:.1f} + coach {float(coach_price):.1f} = {result['price_sum']:.1f} of {float(squad_budget):.1f}."
    )
    if float(coach_price) <= 0:
        st.warning(
            "Enter the coach's current credits. They come out of the Credits field, so a squad built at 0 will not fit once the coach is priced."
        )
    starters = players[players["slot"].isin(["Captain", "Starter"])]
    shape = "-".join(str(int((starters["position_group"] == position).sum())) for position in POSITIONS)
    summary[2].metric("Formation (G-F-C)", shape)
    used = result.get("changes_used")
    summary[3].metric("Changes used", "—" if used is None else str(used))
    if result["coach_name"]:
        venue = result["coach_home_away"] or ""
        opponent = result["coach_opponent"] or "the opponent"
        if window == 1:
            coach_text = (
                f"Coach {result['coach_name']} ({result['coach_team']}) vs {opponent} ({venue}): "
                f"{result['coach_points']:.1f} projected points."
            )
        else:
            coach_text = (
                f"Coach {result['coach_name']} ({result['coach_team']}) over {window} rounds: "
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
    left_out = data.projections[data.projections["availability"] != "available"].copy() if "availability" in data.projections.columns else data.projections.iloc[0:0]
    if day is not None and not left_out.empty and "game_date" in left_out.columns:
        local = pd.to_datetime(left_out["game_date"], utc=True, errors="coerce").dt.tz_convert("Europe/Athens")
        left_out = left_out[local.dt.normalize() == day]
    with st.expander(f"Players left out ({len(left_out)})"):
        if left_out.empty:
            st.caption("No out or unconfirmed players on this slate.")
        else:
            left_out = left_out.sort_values("projected", ascending=False, na_position="last")
            st.dataframe(_styled_board(left_out, data.projections), hide_index=True, width="stretch")
            st.caption("These players are Out or not confirmed, so they are not used in the squad.")
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
                "coach_price": _stored_price(coach_price),
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
    return tuple(path.stat().st_mtime if path.exists() else 0.0 for path in paths)


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
        "Stats come from the public Euroleague feeds. Player credits come from the published Fantasy Challenge list."
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

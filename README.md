# Euroleague Fantasy

Personal dashboard for the EuroLeague Fantasy Challenge. It is local only: no accounts and no public site.

Open [http://localhost:8501](http://localhost:8501).

## Run

```bash
cd ~/euroleague-fantasy
python3 -m pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

Python 3.10 is enough. The first **Refresh data** in the sidebar downloads last season’s box scores and can take a few minutes. Later refreshes only fetch new games, the credit list, and the injury report.

Stop the app with Ctrl+C in that terminal.

## Pages

- **Player board** — every player, with team, position, venue, minutes, and sort filters.
- **Matchup** — one club’s next game and how many fantasy points that defense allows.
- **Best team** — a legal squad for the next round, one tip day, or the next 1–5 rounds. **Use** starts from a named team and spends the change limit. **Copy this squad** writes that lineup into My team.
- **My team** — your own lineup, saved in `data/squad.json`.

Roster rules: 4 guards, 4 forwards, 2 centers, and the credits you type on Best team (100 in Fantasy Challenge), at most 6 players from one club. Starters, the sixth man, and the coach count in full. The bench counts at half. One starter is captain and counts double. Starting shapes are 2-2-1, 1-2-2, 2-1-2, 1-3-1, and 3-1-1 (guards-forwards-centers).

## Columns

Green is the top third of the league, yellow the middle, red the bottom. Volatility is reversed, so a low number is green. Price is not colored.

- **Player** — name on the active roster.
- **Team** — EuroLeague club.
- **Pos** — G guard, F forward, or C center.
- **Status** — Available when the player is confirmed to play. Yellow means it is not confirmed (Expected, Questionable, Game-time, Doubtful, or Uncertain). Out means he will not play. Anyone missing from the injury report is Available. Best team leaves out everyone who is not Available.
- **Note** — the injury comment. Blank when the player is Available.
- **GP** — games behind the averages.
- **Min** — average minutes in those games.
- **Fpts/g** — fantasy points per game. A win is PIR plus 10%. A loss is PIR.
- **Last 5** — average fantasy points over the last five games.
- **Per 36** — fantasy points scaled to 36 minutes.
- **Volatility** — how much the fantasy score swings.
- **Price** — published Fantasy Challenge credits.
- **Points per credit** — Projected divided by Price.
- **Projected** — expected fantasy points for the next game. Expected minutes (60% of the last 5 games, 40% of the season) times PIR per minute, then adjusted for the opponent, home or away, and a 10% win bonus weighted by the win chance. Until eight 2026–27 games are played, last season fills the gap.
- **Floor** / **Ceiling** — low and high outcomes from the last eight games, adjusted only for the opponent.
- **Opponent** — next rival.
- **H/A** — Home or Away.
- **Win %** — chance the club wins the next game.
- **Opp factor** — fantasy points the rival allows to this position, divided by the league average. Above 1 is an easier matchup.
- **Form** — 2025-26, 2026-27, Blend, or Pos. avg.
- **Opponent allows** / **League allows** / **Factor** — the matchup table. Factor is Opponent allows divided by League allows.
- **Slot** — Captain (double), Starter or Sixth (full), or Bench (half).
- **Counted** — Projected times the slot multiplier.
- **Coach price** — typed by you. Coach credits are not on the published player list.

## Coaches

Each page includes the head coach. Coach fantasy points come from the final margin, not from PIR:

- Win by 1–10, or any overtime win: **+10**
- Win by 11–20: **+20**
- Win by 21 or more: **+25**
- Loss by 1–10, or any overtime loss: **−5**
- Loss by 11–20: **−10**
- Loss by 21 or more: **−20**

**Fpts/g** and **Last 5** are those scores. **Avg margin** is the average score difference. **Projected** is the chance-weighted score for the next game and counts in full. **Floor** and **Ceiling** come from the last eight games. **Form** No games means that coach has no EuroLeague results in the cache. Coach colors compare coaches with each other.

## Data

Box scores, schedule, and rosters come from the public Euroleague feeds and are cached in `data/cache/`. Player credits come from the published 2026–27 Fantasy Challenge list and refresh when that cache is older than six hours. Injury status comes from the BasketNews EuroLeague injury report and uses the same six-hour cache.

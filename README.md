# Euroleague Fantasy

Personal dashboard for the EuroLeague Fantasy Challenge. No accounts. Use it on this PC (`localhost`) or on your home Wi‑Fi (the Network URL). It is not meant to be opened from the public internet.

Open [http://localhost:8501](http://localhost:8501).

## Run

Python 3.10 or newer is enough. Use a virtual environment so `streamlit` is on your PATH. Typing `streamlit` from a plain PowerShell window will fail if that environment is not active.

### Windows (PowerShell)

A bare `streamlit` command fails with `The term 'streamlit' is not recognized` unless the project venv is active. Streamlit lives in `.venv`, not on the system PATH.

If `.venv` already exists, from the project folder run:

```powershell
cd F:\euroleaguefantasy
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

First-time setup (creates `.venv` and installs packages):

```powershell
cd F:\euroleaguefantasy
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

You can also activate the venv, then `python -m streamlit` works without the full path:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py --server.port 8501
```

`python -m streamlit` is more reliable on Windows than a bare `streamlit` command. If `Activate.ps1` is blocked, skip activation and keep using `.\.venv\Scripts\python.exe`.

### macOS / Linux

```bash
cd ~/euroleague-fantasy
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py --server.port 8501
```

The first **Refresh data** in the sidebar downloads last season’s box scores and can take a few minutes. Later refreshes only fetch new games, the credit list, and the injury report.

Open [http://localhost:8501](http://localhost:8501). On the same Wi‑Fi you can also use the Network URL (192.168.x).

### Stop

In the terminal where Streamlit is running, press **Ctrl+C**. Wait until the prompt comes back. Closing that terminal also stops the app.

If the window is gone but the site still loads, something is still bound to port 8501. In PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8501 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Restart

Stop the app, then start it again with the same command as **Run** (from the project folder):

```powershell
cd F:\euroleaguefantasy
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

After a restart, open [http://localhost:8501](http://localhost:8501) and hard-refresh the browser (Ctrl+F5). On **Best team**, press **Start best team** again if you still see an old squad.

You do not need to delete `data/cache` to pick up code changes. Sidebar **Refresh data** is only for new box scores, prices, and injuries.

## Pages

- **Player board** — every player, with team, position, venue, minutes, sort, and (when the round spans more than one day) **Turn** (T1/T2/T3) filters. With official Fan ID prices, **Owned %** and a Differentials / template-risk expander (low-owned pickups vs highly owned players missing from My team). The Player column is pinned; any other column can be pinned too from its header menu.
- **Matchup** — one club’s next game and how many fantasy points that defense allows.
- **Best team** — a legal squad for the next round, one tip day, or the next 1–5 rounds. **Changes** picks how many new players come in; the **Mode** toggle next to it is Exact (bring in exactly that many) or Up to (Best team may use fewer if that scores just as well or better). **Start best team** runs from the selected saved team. **Trade one player** suggests same-position upgrades at or below that player’s price with a higher projection. After you save a new lineup on My team, press Start again; the old suggestion is not kept on screen. **Copy this squad** writes that lineup into My team.
- **My team** — your own lineup, saved in `data/squad.json`. Optional **Import from Fantasy Challenge** pulls the official lineup for your Fan ID into the selected saved team (overwrite only when you confirm).

Roster rules: 4 guards, 4 forwards, 2 centers, and the credits you type on Best team (100 in Fantasy Challenge), at most 6 players from one club. Best team spends leftover credits on a same-position upgrade when that does not lose projected points. Starters, the sixth man, and the coach count in full. The bench counts at half. One starter is captain and counts double. Starting shapes are 2-2-1, 1-2-2, 2-1-2, 1-3-1, and 3-1-1 (guards-forwards-centers).

## Columns

Green is the top third of the league, yellow the middle, red the bottom. Volatility is reversed, so a low number is green. Price is not colored.

- **Player** — name on the active roster.
- **Team** — EuroLeague club.
- **Pos** — G, F, or C from the Fantasy Challenge player list (same slots as the official game).
- **Status** — Available when the player is confirmed to play. Yellow means it is not confirmed (Expected, Questionable, Game-time, Doubtful, or Uncertain). Out means he will not play. Anyone missing from the injury report is Available. Best team leaves out everyone who is not Available.
- **Note** — the injury comment. Blank when the player is Available.
- **GP** — games behind the averages.
- **Min** — average minutes in those games.
- **Fpts/g** — fantasy points per game. A win is PIR plus 10%. A loss is PIR.
- **Last 5** — average fantasy points over the last five games.
- **Per 36** — fantasy points scaled to 36 minutes.
- **Shots/g** — average field goal attempts per game. Nudges Projected up to ±10% versus his position's average, shrunk toward no effect in a small sample.
- **Volatility** — how much the fantasy score swings.
- **Price** — published Fantasy Challenge credits.
- **Owned %** — share of Fantasy Challenge managers who own him (from the official Fan ID list). Blank when using the public price list.
- **Points per credit** — Projected divided by Price.
- **Projected** — expected fantasy points for the next game: Fpts/g times that opponent's G/F/C game pie versus the league (one star is the whole pie, not cloned onto every player; a one-game matchup is pulled toward last season), then home or away, a 10% win bonus weighted by win chance, and the Shots/g nudge. After one game this season, Fpts/g is this season only.
- **Floor** / **Ceiling** — low and high outcomes from the last eight games, adjusted for the opponent.
- **Opponent** — next rival.
- **H/A** — Home or Away.
- **Win %** — chance the club wins the next game.
- **Opp factor** — game pie versus the league, pulled toward last season until a few games are in. Above 1 is an easier matchup.
- **Form** — 2026-27 if he has played this season, 2025-26 if not.
- **L3 / L5 / L10 / ALL / League / Factor** — Matchup table. ALL is total G, F, or C fantasy allowed in a game. Factor is that versus the league, shrunk early in the season.
- **Slot** — Captain (double), Starter or Sixth (full), or Bench (half).
- **Counted** — Projected times the slot multiplier.
- **Coach price** — from the official Fantasy Challenge list when credentials are configured.

## Coaches

Each page includes the head coach. Coach fantasy points come from the final margin, not from PIR:

- Win by 1–10, or any overtime win: **+10**
- Win by 11–20: **+20**
- Win by 21 or more: **+25**
- Loss by 1–10, or any overtime loss: **−5**
- Loss by 11–20: **−10**
- Loss by 21 or more: **−20**

**Fpts/g** and **Last 5** are those scores. **Avg margin** is the average score difference. **Projected** is the chance-weighted score for the next game and counts in full. **Floor** and **Ceiling** come from the last eight games. **Form** No games means that coach has no EuroLeague results in the cache. Coach colors compare coaches with each other.

## Official credits (required for live prices)

The official Fantasy Challenge app updates player and coach credits after each round. This dashboard can use those same numbers only after **you** add your own EuroLeague Fan ID on this PC.

1. Copy `data/fantasy_credentials.example` to `data/fantasy_credentials.properties`.
2. Put the email and password you use on [euroleaguebasketball.net](https://www.euroleaguebasketball.net/en/login/) (the same Fan ID as Fantasy Challenge).
3. Save the file. Do not commit it. It is listed in `.gitignore`.
4. Press **Refresh data** in the sidebar.

Each user of this repo must create their own `data/fantasy_credentials.properties`. GitHub never gets that file, and neither does `data/fantasy_session.json` (the local session token).

If the file is missing, Best team falls back to the public givemestats list for **players** only (opening prices). Coach credits and your Fantasy bank need the Fan ID login.

After a successful official refresh, **Best team** prefills coach credits from the Fantasy list, the **Credits** budget from your Fantasy Challenge bank (players + coach value), and **Changes** from your remaining free trades. You can still edit any of those.

## Data

Box scores, schedule, and rosters come from the public Euroleague feeds and are cached in `data/cache/`.

Player credits come from the official Fantasy Challenge list when `data/fantasy_credentials.properties` is filled in, and from the public [givemestats 2026/27 list](https://givemestats.com/euroleague/fantasy-basketball-risers/2026) otherwise. Refresh when that cache is older than six hours, or when you press **Refresh data**. Official prices move after each round, when the transfer window opens.

Injury status comes from the BasketNews EuroLeague injury report and uses the same six-hour cache.

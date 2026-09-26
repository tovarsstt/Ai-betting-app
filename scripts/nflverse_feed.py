"""
nflverse_feed.py — current NFL data for the Judge, from the open nflverse
project on GitHub (reachable where ESPN/NFL.com are not).

  games.csv          every game: scores, closing spread/total/moneylines, QBs, roof
  injuries_<Y>.csv   official weekly injury reports (position, practice, status)
  depth_charts_<Y>   daily depth charts -> who STARTS (so a backup's injury ~ 0)
  roster_weekly_<Y>  daily rosters (IR / reserve status)
  play_by_play_<Y>   EPA/play, pass rate, pace (playstyle)

Everything is cached in data/nflverse/ (refresh with refresh(); tests never
touch the network). Ratings are CURRENT: last season's results are only a
prior (k game-equivalents), halved for teams whose starting QB changed, and
every 2026 game pulls the rating toward this season's reality.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "nflverse"
REL = "https://github.com/nflverse/nflverse-data/releases/download"
URLS = {
    "games.csv": "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
    "injuries_{y}.csv": f"{REL}/injuries/injuries_{{y}}.csv",
    "depth_charts_{y}.csv": f"{REL}/depth_charts/depth_charts_{{y}}.csv",
    "roster_weekly_{y}.csv": f"{REL}/weekly_rosters/roster_weekly_{{y}}.csv",
    "pbp_{y}.csv.gz": f"{REL}/pbp/play_by_play_{{y}}.csv.gz",
}

TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers",
    "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

# nflverse injury-report positions -> winner_judge.NFL_POSITION_PTS keys
POS_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
           "T": "OL", "G": "OL", "C": "OL", "OT": "OL", "OG": "OL", "OL": "OL",
           "DE": "EDGE", "OLB": "EDGE", "EDGE": "EDGE", "DT": "DL", "NT": "DL", "DL": "DL",
           "LB": "LB", "ILB": "LB", "MLB": "LB", "CB": "CB", "DB": "CB", "S": "S",
           "SS": "S", "FS": "S", "K": "K", "P": "K", "LS": "K"}
STATUS_WEIGHT = {"Out": 1.0, "Doubtful": 0.75}        # Questionable = not priced

PRIOR_GAMES = 4.0          # last season's rating is worth this many current games
QB_CHANGE_PRIOR = 0.5      # ...times this when the starting QB changed
RIDGE = 2.0                # shrinkage for the least-squares ratings
MAX_AGE_H = 6.0


# ── Cache / download ──────────────────────────────────────────────────────────
def path(name: str, year: Optional[int] = None) -> Path:
    return DATA / name.format(y=year)


def refresh(season: int, names: tuple = tuple(URLS), max_age_h: float = MAX_AGE_H) -> dict:
    """Download (if older than max_age_h) every feed file. Real app use only."""
    DATA.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in names:
        years = [season - 1, season] if name.startswith("pbp") else [season]
        for y in (years if "{y}" in name else [None]):
            p = path(name, y)
            if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
                out[p.name] = "cached"
                continue
            try:
                urllib.request.urlretrieve(URLS[name].format(y=y), p)
                out[p.name] = "downloaded"
            except Exception as e:                      # noqa: BLE001
                out[p.name] = f"FAILED: {e}"
    return out


def freshness() -> dict:
    return {p.name: time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(p.stat().st_mtime))
            for p in sorted(DATA.glob("*")) if p.is_file()}


def load_games() -> pd.DataFrame:
    return pd.read_csv(path("games.csv"), low_memory=False)


# ── Ratings: prior season + current season, opponent-adjusted ─────────────────
def _solve(g: pd.DataFrame, teams: list[str]) -> tuple[dict, dict, float, float]:
    """Ridge least squares on scores: home_pts = mu + hfa/2 + off_h - def_a,
    away_pts = mu - hfa/2 + off_a - def_h. Returns off, def, mu, hfa."""
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    rows, y = [], []
    for r in g.itertuples():
        for pts, att, dfn, sgn in ((r.home_score, r.home_team, r.away_team, 0.5),
                                   (r.away_score, r.away_team, r.home_team, -0.5)):
            x = np.zeros(2 * n + 2)
            x[idx[att]] = 1.0
            x[n + idx[dfn]] = -1.0
            x[2 * n] = 1.0
            x[2 * n + 1] = sgn if r.location != "Neutral" else 0.0
            rows.append(x)
            y.append(pts)
    X, Y = np.array(rows), np.array(y, dtype=float)
    reg = np.eye(2 * n + 2) * RIDGE
    reg[2 * n, 2 * n] = reg[2 * n + 1, 2 * n + 1] = 0.0          # don't shrink mu / hfa
    beta = np.linalg.solve(X.T @ X + reg, X.T @ Y)
    off = {t: float(beta[idx[t]]) for t in teams}
    dfn = {t: float(beta[n + idx[t]]) for t in teams}
    return off, dfn, float(beta[2 * n]), float(beta[2 * n + 1])


def qb_starters(games: pd.DataFrame, season: int) -> dict:
    """Most frequent starting QB per team in a season (from games.csv)."""
    g = games[(games.season == season) & games.home_score.notna()]
    rows = pd.concat([g[["home_team", "home_qb_name"]].set_axis(["team", "qb"], axis=1),
                      g[["away_team", "away_qb_name"]].set_axis(["team", "qb"], axis=1)])
    return rows.groupby("team").qb.agg(lambda s: s.value_counts().index[0]).to_dict()


def team_ratings(season: int, week: int, games: Optional[pd.DataFrame] = None,
                 current_qb: Optional[dict] = None) -> dict:
    """Ratings for `season` using only games BEFORE `week` (walk-forward safe)."""
    games = load_games() if games is None else games
    played = games[games.home_score.notna() & games.game_type.isin(["REG", "WC", "DIV", "CON", "SB"])]
    prev = played[played.season == season - 1]
    cur = played[(played.season == season) & (played.week < week)]
    teams = sorted(set(played[played.season >= season - 1].home_team)
                   | set(played[played.season >= season - 1].away_team))
    off_p, def_p, mu_p, hfa_p = _solve(prev, teams) if len(prev) else ({t: 0 for t in teams},) * 2 + (22.0, 1.5)
    off_c, def_c, mu_c, hfa_c = (_solve(cur, teams) if len(cur) >= 8 else (off_p, def_p, mu_p, hfa_p))
    n_cur = {t: int(((cur.home_team == t) | (cur.away_team == t)).sum()) for t in teams}
    prev_qb = qb_starters(games, season - 1)
    out = {}
    for t in teams:
        changed = bool(current_qb and prev_qb.get(t) and current_qb.get(t)
                       and current_qb[t] != prev_qb[t])
        k = PRIOR_GAMES * (QB_CHANGE_PRIOR if changed else 1.0)
        n = n_cur[t] if len(cur) >= 8 else 0
        blend = lambda a, b: (k * a + n * b) / (k + n) if (k + n) else a
        o, d = blend(off_p[t], off_c[t]), blend(def_p[t], def_c[t])
        out[t] = {"off": round(o, 2), "def": round(d, 2), "net": round(o + d, 2),
                  "games_this_season": n_cur[t], "prior_weight_games": k,
                  "qb_changed": changed, "prev_qb": prev_qb.get(t),
                  "qb": (current_qb or {}).get(t)}
    # league scoring + home edge: same prior-vs-current blend, by games per team
    avg_n = (2 * len(cur) / max(1, len(teams))) if len(cur) >= 8 else 0.0
    hfa = (PRIOR_GAMES * hfa_p + avg_n * hfa_c) / (PRIOR_GAMES + avg_n)
    mu = (PRIOR_GAMES * mu_p + avg_n * mu_c) / (PRIOR_GAMES + avg_n)
    return {"teams": out, "hfa": round(hfa, 2), "mu": round(mu, 2),
            "season": season, "through_week": week - 1}


def predict(ratings: dict, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
    """(expected home margin, expected total) from the ratings."""
    h, a = ratings["teams"][home], ratings["teams"][away]
    hfa = 0.0 if neutral else ratings["hfa"]
    hp = ratings["mu"] + hfa / 2 + h["off"] - a["def"]
    ap = ratings["mu"] - hfa / 2 + a["off"] - h["def"]
    return hp - ap, hp + ap


# ── Depth chart / injuries ────────────────────────────────────────────────────
def latest_depth(season: int) -> pd.DataFrame:
    d = pd.read_csv(path("depth_charts_{y}.csv", season), low_memory=False)
    last = d.groupby("team").dt.transform("max")
    return d[d.dt == last]


def current_qbs(season: int) -> dict:
    d = latest_depth(season)
    q = d[(d.pos_abb == "QB")].sort_values("pos_rank")
    return q.groupby("team").player_name.apply(lambda s: list(dict.fromkeys(s))).to_dict()


def injury_conditions(season: int, week: int, overrides: Optional[dict] = None) -> tuple[dict, dict]:
    """Official report -> Judge conditions, STARTERS ONLY (depth-chart rank 1).
    overrides: {TEAM: [{"player","position","status","pts"?,"source"}]} for
    confirmed news not yet in the report. Returns (conditions, watchlist)."""
    inj = pd.read_csv(path("injuries_{y}.csv", season))
    inj = inj[inj.week == week]
    d = latest_depth(season)
    starters = set(d[d.pos_rank == 1].gsis_id.dropna())
    src = f"nflverse injuries_{season}.csv week {week} (official NFL injury report)"
    cond: dict = {}
    watch: dict = {}
    for r in inj.itertuples():
        pos = POS_MAP.get(str(r.position).upper())
        w = STATUS_WEIGHT.get(r.report_status)
        if r.gsis_id in starters and pos and w:
            cond.setdefault(r.team, []).append({
                "player": r.full_name, "position": pos, "status": r.report_status, "weight": w,
                "note": f"{r.position} {r.full_name} {r.report_status.upper()} ({r.report_primary_injury})",
                "source": src})
        elif (r.gsis_id in starters and pd.isna(r.report_status)
              and str(r.practice_status).startswith("Did Not Participate")):
            watch.setdefault(r.team, []).append(f"{r.position} {r.full_name}: DNP, no game status yet")
    rank = d.groupby(["team", "player_name"]).pos_rank.min().to_dict()
    for team, items in (overrides or {}).items():
        for o in items:
            if o["player"] in {c["player"] for c in cond.get(team, [])}:
                continue                                           # already in the report
            r = rank.get((team, o["player"]))
            if o.get("pts") is None and r is not None and r > 1:
                continue                                           # backup: not priced
            cond.setdefault(team, []).append({
                "player": o["player"], "position": o["position"], "status": o["status"],
                "weight": STATUS_WEIGHT.get(o["status"], 1.0),
                **({"pts": o["pts"]} if o.get("pts") is not None else {}),
                "note": f"{o['position']} {o['player']} {o['status'].upper()} — {o.get('note', '')}".strip(" —"),
                "source": o["source"]})
            if team in watch:
                watch[team] = [w for w in watch[team] if o["player"] not in w]
    return cond, watch


# ── Playstyle from play-by-play ───────────────────────────────────────────────
def playstyle(season: int, prior_weight: float = 0.35) -> dict:
    cols = ["season", "week", "game_id", "posteam", "defteam", "play_type", "epa", "pass", "rush"]
    frames = []
    for y, w in ((season - 1, prior_weight), (season, 1.0)):
        p = path("pbp_{y}.csv.gz", y)
        if p.exists():
            df = pd.read_csv(p, low_memory=False, usecols=lambda c: c in cols)
            df = df[df.play_type.isin(["pass", "run"]) & df.epa.notna()]
            df["w"] = w
            frames.append(df)
    if not frames:
        return {}
    df = pd.concat(frames)
    out = {}
    for t, g in df.groupby("posteam"):
        d = df[df.defteam == t]
        gp = g.groupby("season").game_id.nunique()
        plays_pg = float(np.average(g.groupby("season").size() / gp,
                                    weights=[g[g.season == s].w.iloc[0] for s in gp.index]))
        out[t] = {"off_epa_play": round(float(np.average(g.epa, weights=g.w)), 3),
                  "def_epa_play": round(float(np.average(d.epa, weights=d.w)), 3),
                  "pass_rate": round(float(np.average(g["pass"], weights=g.w)), 3),
                  "plays_pg": round(plays_pg, 1)}
    return out


def _clean(x):
    """nflverse CSVs have gaps (roof, odds) -> NaN, which is not valid JSON."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


# ── Week slate for the Judge ──────────────────────────────────────────────────
def week_slate(season: int, week: int, overrides: Optional[dict] = None,
               include_played: bool = False) -> dict:
    games = load_games()
    qbs = current_qbs(season)
    cond, watch = injury_conditions(season, week, overrides)
    out_qbs = {t: {c["player"] for c in cs if c["position"] == "QB" and c["weight"] >= 1.0}
               for t, cs in cond.items()}
    qb1, depth_qb1 = {}, {}
    for t, lst in qbs.items():
        healthy = [q for q in lst if q not in out_qbs.get(t, set())]
        qb1[t] = healthy[0] if healthy else (lst[0] if lst else None)
        depth_qb1[t] = lst[0] if lst else None
    # "QB changed" = OFFSEASON change (depth-chart QB1 vs last season's starter).
    # An injured QB is priced once, by the injury condition — never twice.
    ratings = team_ratings(season, week, games, current_qb=depth_qb1)
    style = playstyle(season)
    wk = games[(games.season == season) & (games.week == week)]
    if not include_played:
        wk = wk[wk.home_score.isna()]
    out = []
    for r in wk.itertuples():
        h, a = r.home_team, r.away_team
        neutral = r.location == "Neutral"
        margin, total = predict(ratings, h, a, neutral)
        conds = {side: [{k: v for k, v in c.items() if k != "weight"}
                        | ({"pts_scale": c["weight"]} if c["weight"] != 1.0 else {})
                        for c in cond.get(t, [])]
                 for side, t in (("home", h), ("away", a))}
        out.append({
            "sport": "NFL", "id": f"{a}@{h}", "home": TEAM_NAMES.get(h, h), "away": TEAM_NAMES.get(a, a),
            "kickoff": f"{r.gameday} {r.gametime} ET", "neutral": neutral,
            "moneyline": {"home": r.home_moneyline, "away": r.away_moneyline},
            "spread": {"home_line": -float(r.spread_line),
                       "home_price": r.home_spread_odds if pd.notna(r.home_spread_odds) else -110,
                       "away_price": r.away_spread_odds if pd.notna(r.away_spread_odds) else -110},
            "total": {"points": float(r.total_line),
                      "over_price": r.over_odds if pd.notna(r.over_odds) else -110,
                      "under_price": r.under_odds if pd.notna(r.under_odds) else -110},
            "ratings_margin": round(margin, 2), "ratings_total": round(total, 1),
            "conditions": conds,
            "context": {
                "qb": {"home": qb1.get(h), "away": qb1.get(a)},
                "ratings": {"home": ratings["teams"].get(h), "away": ratings["teams"].get(a)},
                "playstyle": {"home": style.get(h), "away": style.get(a)},
                "rest_days": {"home": r.home_rest, "away": r.away_rest},
                "roof": r.roof, "div_game": bool(r.div_game),
                "injury_watch": {"home": watch.get(h, []), "away": watch.get(a, [])},
            },
        })
    return {"season": season, "week": week, "games": _clean(out), "hfa": ratings["hfa"],
            "freshness": freshness(),
            "lines_source": "nflverse games.csv (consensus lines, updated daily)"}


def load_overrides(season: int) -> dict:
    p = DATA.parent / f"nfl_{season}_injury_overrides.json"
    return json.loads(p.read_text()).get("teams", {}) if p.exists() else {}


def current_week(season: int, games: Optional[pd.DataFrame] = None) -> int:
    """First regular-season week that still has unplayed games."""
    games = load_games() if games is None else games
    g = games[(games.season == season) & (games.game_type == "REG") & games.home_score.isna()]
    return int(g.week.min()) if len(g) else int(games[games.season == season].week.max())


def merge_live_prices(feed_games: list[dict], live_games: list[dict]) -> list[dict]:
    """Overlay fresher Odds API prices (moneyline best price + multi-book
    consensus, spread, total) onto feed games; keep ratings/injuries/context."""
    live = {(g["home"], g["away"]): g for g in live_games}
    out = []
    for g in feed_games:
        l = live.get((g["home"], g["away"]))
        if l:
            g = {**g, **{k: l[k] for k in ("moneyline", "ml_consensus_home", "spread", "total")
                         if l.get(k)}, "lines_source": "The Odds API (live)"}
        out.append(g)
    return out

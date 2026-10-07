#!/usr/bin/env python3
"""
player_availability_nba.py — who plays, and does the closing line already know?

For every NBA game (2024-26) build, from EARLIER games only (no look-ahead), each player's expected minutes and
per-minute production (Hollinger Game Score / min), then for each team the TALENT MISSING tonight:
    talent_out = sum over rotation players (expected minutes >= 15) who did NOT play of  exp_min * (gmsc_per_min - replacement)+
and ask whether the margin / total vs the CLOSING line moves with it. A coefficient of 0 means the closing line (set
after injury news) already prices availability; a non-zero, replicated one is a player-level edge.

Split by season (24-25 fit, 25-26 replicate), Holm-corrected over the family. Also reports the quality of the proxy itself:
how much of the REALISED margin the talent-out differential explains (sanity: it must matter for results even if it is priced).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

KG = Path("/tmp/kg")
DATA = Path(__file__).parent.parent / "data"
REPL = 0.22                                    # replacement-level Game Score per minute


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def split_made(s):
    try:
        a, b = str(s).split("-")
        return float(a), float(b)
    except Exception:
        return 0.0, 0.0


def _box_rows(path) -> list:
    rows = []
    for line in Path(path).open():
        d = json.loads(line)
        for tm in d["teams"]:
            for p in tm["players"]:
                s = p["stats"]
                mins = num(s.get("minutes"))
                fgm, fga = split_made(s.get("fieldGoalsMade-fieldGoalsAttempted"))
                ftm, fta = split_made(s.get("freeThrowsMade-freeThrowsAttempted"))
                gs = (num(s.get("points")) + 0.4 * fgm - 0.7 * fga - 0.4 * (fta - ftm) + 0.7 * num(s.get("offensiveRebounds")) + 0.3 * num(s.get("defensiveRebounds"))
                      + num(s.get("steals")) + 0.7 * num(s.get("assists")) + 0.7 * num(s.get("blocks")) - 0.4 * num(s.get("fouls")) - num(s.get("turnovers")))
                rows.append((d["id"], tm["team"], p["id"], p["name"], mins, gs, bool(p.get("dnp")) or mins == 0, p.get("reason")))
    return rows


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    g = pd.concat([pd.read_excel(f) for f in sorted((KG / "closing_odds").glob("NBA*.xlsx"))], ignore_index=True)
    g = g.dropna(subset=["home_pts", "away_pts", "spread", "total"]).drop_duplicates("game_id")
    g["date"] = pd.to_datetime(g.game_time, utc=True)
    g = g[["game_id", "date", "home_team", "away_team", "home_pts", "away_pts", "spread", "total"]]
    rows = _box_rows(KG / "espn_nba.jsonl")
    hist_ev, hist_box = KG / "espn_nba_hist_events.jsonl", KG / "espn_nba_hist.jsonl"
    if hist_ev.exists() and hist_box.exists():                       # older seasons: ESPN events + closing lines from the 2008-26 file
        ev = pd.DataFrame([json.loads(l) for l in hist_ev.open()])
        ev["date"] = pd.to_datetime(ev.utc, utc=True)
        ev["day"] = (ev.date - pd.Timedelta(hours=8)).dt.strftime("%Y-%m-%d")
        c = pd.read_csv(KG / "nba_odds/nba_2008-2026.csv")
        c = c[c.regular == True].dropna(subset=["spread", "total"]).copy()
        c["day"] = pd.to_datetime(c.date).dt.strftime("%Y-%m-%d")
        c["hl"] = -np.where(c.whos_favored == "home", c.spread, -c.spread)   # home line (negative when home favoured)
        ev["h"], ev["a"] = ev.home.str.lower(), ev.away.str.lower()
        m = ev.merge(c[["day", "home", "away", "hl", "total"]].rename(columns={"home": "h", "away": "a", "hl": "spread"}), on=["day", "h", "a"], how="inner")
        old = pd.DataFrame({"game_id": m.id, "date": m.date, "home_team": m.hn, "away_team": m.an, "home_pts": m.hp, "away_pts": m.ap, "spread": m.spread, "total": m.total})
        g = pd.concat([old, g], ignore_index=True).drop_duplicates("game_id")
        rows += _box_rows(hist_box)
        print(f"history joined: {len(old)} older games with closing lines")
    g = g.sort_values("date").reset_index(drop=True)
    b = pd.DataFrame(rows, columns=["game_id", "team", "pid", "name", "min", "gmsc", "absent", "reason"])
    b = b[b.game_id.isin(g.game_id)]
    return g, b


def build() -> pd.DataFrame:
    g, b = load()
    b = b.merge(g[["game_id", "date"]], on="game_id").sort_values(["pid", "date"]).reset_index(drop=True)
    played = b[~b.absent].copy()
    # past-only trailing expectations over the player's last 15 appearances
    played["exp_min"] = played.groupby("pid")["min"].transform(lambda s: s.shift(1).rolling(15, min_periods=5).mean())
    played["gpm"] = played.groupby("pid").apply(lambda x: (x.gmsc.shift(1).rolling(15, min_periods=5).sum() / x["min"].shift(1).rolling(15, min_periods=5).sum()), include_groups=False).reset_index(level=0, drop=True)
    last = played[["pid", "date", "exp_min", "gpm"]].rename(columns={"date": "d0"}).dropna()
    # roster expectation per team-game: every player who played for the team in the previous 20 days with exp_min>=15 and is NOT in tonight's box
    out = []
    byteam = b.groupby("team")
    games = b.groupby(["game_id", "team"])
    for (gid, team), tonight in games:
        d = tonight.date.iloc[0]
        window = b[(b.team == team) & (b.date < d) & (b.date >= d - pd.Timedelta(days=21)) & (~b.absent)]
        if window.empty:
            continue
        cand = window.groupby("pid").agg(name=("name", "last"))
        last_exp = last[(last.pid.isin(cand.index)) & (last.d0 < d)].sort_values("d0").groupby("pid").tail(1).set_index("pid")
        cand = cand.join(last_exp[["exp_min", "gpm"]], how="inner")
        cand = cand[cand.exp_min >= 15]
        played_ids = set(tonight[~tonight.absent].pid)
        miss = cand[~cand.index.isin(played_ids)]
        val = (miss.exp_min * (miss.gpm - REPL).clip(lower=0)).sum()
        star = ((cand.exp_min * (cand.gpm - REPL).clip(lower=0)).sort_values(ascending=False).head(2).index.difference(played_ids)).size
        out.append((gid, team, float(val), int(star), int(len(miss))))
    t = pd.DataFrame(out, columns=["game_id", "team", "talent_out", "top2_out", "rot_out"])
    h = g[["game_id", "date", "home_team", "away_team", "home_pts", "away_pts", "spread", "total"]].merge(t.rename(columns={"team": "home_team", "talent_out": "to_h", "top2_out": "s_h", "rot_out": "r_h"}), on=["game_id", "home_team"])
    h = h.merge(t.rename(columns={"team": "away_team", "talent_out": "to_a", "top2_out": "s_a", "rot_out": "r_a"}), on=["game_id", "away_team"])
    h["res_margin"] = (h.home_pts - h.away_pts) + h.spread           # >0: home beat its closing line (spread is the home line)
    h["res_total"] = h.home_pts + h.away_pts - h.total
    h["real_margin"] = h.home_pts - h.away_pts
    h["season"] = h.date.dt.year + (h.date.dt.month >= 8).astype(int)
    return h


def holm(ps):
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def run() -> dict:
    h = build()
    h["talent_diff"] = h.to_a - h.to_h                          # positive: away team is missing more -> good for home
    h["top2_diff"] = h.s_a - h.s_h
    h["rot_diff"] = h.r_a - h.r_h
    h["talent_sum"] = h.to_a + h.to_h
    tests = {"margin~talent_diff": ("res_margin", "talent_diff"), "margin~top2_out_diff": ("res_margin", "top2_diff"), "margin~rotation_out_diff": ("res_margin", "rot_diff"),
             "total~talent_sum": ("res_total", "talent_sum"), "REALISED margin~talent_diff (sanity)": ("real_margin", "talent_diff")}
    res, raw = {"n_games": len(h)}, {}
    tr, te = h.season <= 2024, h.season >= 2025
    for name, (y, x) in tests.items():
        a = sm.OLS(h.loc[tr, y], sm.add_constant(h.loc[tr, x])).fit(cov_type="HC1")
        b = sm.OLS(h.loc[te, y], sm.add_constant(h.loc[te, x])).fit(cov_type="HC1")
        c = sm.OLS(h[y], sm.add_constant(h[x])).fit(cov_type="HC1")
        res[name] = {"beta_all": float(c.params[x]), "se_all": float(c.bse[x]), "p_all": float(c.pvalues[x]), "beta_train": float(a.params[x]), "p_train": float(a.pvalues[x]),
                     "beta_test": float(b.params[x]), "p_test": float(b.pvalues[x]), "x_sd": float(h[x].std()), "r2_all": float(c.rsquared)}
        if "sanity" not in name:
            raw[name] = float(a.pvalues[x])
    adj = holm(raw)
    for k, v in adj.items():
        r = res[k]
        r["p_holm_train"] = v
        r["accepted"] = bool(v < 0.05 and np.sign(r["beta_train"]) == np.sign(r["beta_test"]) and r["p_test"] < 0.05)
    res["descr"] = {"mean_talent_out_home": float(h.to_h.mean()), "share_games_with_top2_out": float(((h.s_h > 0) | (h.s_a > 0)).mean())}
    return res


if __name__ == "__main__":
    out = run()
    (DATA / "player_availability_nba.json").write_text(json.dumps(out, indent=1))
    print(f"games {out['n_games']} | share of games where a top-2 rotation player is out: {out['descr']['share_games_with_top2_out']:.1%}")
    for k, v in out.items():
        if k in ("n_games", "descr"):
            continue
        tag = ("ACCEPTED" if v.get("accepted") else "not beyond the line") if "accepted" in v else "sanity"
        print(f" {k:<40} beta {v['beta_all']:+.3f} (p={v['p_all']:.4f}, R2={v['r2_all']:.4f}) | train 22-24 {v['beta_train']:+.3f} p={v['p_train']:.3f} | test 25-26 {v['beta_test']:+.3f} p={v['p_test']:.3f} -> {tag}")

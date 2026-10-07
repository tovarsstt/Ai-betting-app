#!/usr/bin/env python3
"""
qb_effects_nfl.py — the starting quarterback vs the closing line.

Per game: the starter = the passer with the most attempts for each team (ESPN box score). Per QB, from EARLIER games only:
shrunk adjusted yards per attempt  AY/A = (yds + 20 TD - 45 INT) / att  with a prior of league AY/A worth 250 attempts.
Tests (fit 2012-19, replicate 2020-25, Holm over the family), all against the CLOSING line:
  qb_quality_diff    home QB quality - away QB quality (AY/A)             -> margin residual, and REALISED margin as the sanity check
  qb_change_diff     (home QB differs from last game's starter) - (away)  -> margin residual
  backup_diff        starter is not the team's top passer over the last 6 games (injury/benching proxy)
  qb_quality_sum     -> total residual
An effect on the REALISED margin that disappears against the line means the market already prices the quarterback.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

KG = Path("/tmp/kg")
DATA = Path(__file__).parent.parent / "data"
K_PRIOR = 250.0


def starters() -> pd.DataFrame:
    rows = []
    for line in (KG / "espn_nfl_box.jsonl").open():
        d = json.loads(line)
        for tm in d["teams"]:
            best = None
            for p in tm["players"]:
                if p.get("group") != "passing":
                    continue
                s = p["stats"]
                try:
                    att = float(str(s.get("completions/passingAttempts", "0/0")).split("/")[1])
                    yds, td, it = float(s.get("passingYards", 0)), float(s.get("passingTouchdowns", 0)), float(s.get("interceptions", 0))
                except Exception:
                    continue
                if best is None or att > best[2]:
                    best = (p["id"], p["name"], att, yds, td, it)
            if best and best[2] >= 8:
                rows.append((d["id"], tm["team"], *best))
    return pd.DataFrame(rows, columns=["id", "team", "qid", "qname", "att", "yds", "td", "int"])


def games() -> pd.DataFrame:
    ev = pd.DataFrame([json.loads(l) for l in (KG / "espn_nfl_events.jsonl").open()])
    ev["day"] = (pd.to_datetime(ev.utc, utc=True) - pd.Timedelta(hours=8)).dt.strftime("%Y-%m-%d")
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    teams = pd.read_csv(KG / "nfl_spreadspoke/nfl_teams.csv")
    idmap = dict(zip(teams.team_name, teams.team_id))
    d = d[d.spread_favorite.notna() & d.score_home.notna() & (d.team_favorite_id != "PICK") & d.team_favorite_id.notna()].copy()
    hf = d.team_favorite_id == d.team_home.map(idmap)
    d["exp_home"] = np.where(hf, -d.spread_favorite, d.spread_favorite)
    d["ou"] = pd.to_numeric(d.over_under_line, errors="coerce")
    d["day"] = pd.to_datetime(d.schedule_date, format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    d = d.rename(columns={"score_home": "hp", "score_away": "ap"})[["day", "hp", "ap", "exp_home", "ou", "schedule_season"]]
    d[["hp", "ap"]] = d[["hp", "ap"]].astype(int)
    g = ev.merge(d, on=["day", "hp", "ap"], how="inner").drop_duplicates("id")
    # ESPN closing files cover the newest seasons (ids are ESPN event ids)
    for f in sorted((KG / "closing_odds").glob("NFL*.xlsx")):
        c = pd.read_excel(f).dropna(subset=["spread", "total"]).drop_duplicates("game_id")
        c = c.rename(columns={"game_id": "id"})[["id", "spread", "total"]]
        m = ev.merge(c, on="id")
        m["exp_home"], m["ou"] = -m.spread, m.total
        m["schedule_season"] = pd.to_datetime(m.utc, utc=True).dt.year - (pd.to_datetime(m.utc, utc=True).dt.month < 3)
        g = pd.concat([g, m[["id", "utc", "hn", "an", "hp", "ap", "neutral", "day", "exp_home", "ou", "schedule_season"]]]).drop_duplicates("id")
    g["date"] = pd.to_datetime(g.utc, utc=True)
    return g.sort_values("date").reset_index(drop=True)


def build() -> pd.DataFrame:
    g, s = games(), starters()
    lg = (s.yds.sum() + 20 * s.td.sum() - 45 * s["int"].sum()) / s.att.sum()           # league AY/A prior
    hs = s.merge(g[["id", "hn", "an", "date"]], on="id")
    hs["side"] = np.where(hs.team == hs.hn, "h", "a")
    hs = hs.sort_values(["qid", "date"]).reset_index(drop=True)
    hs["val"] = hs.yds + 20 * hs.td - 45 * hs["int"]
    cs_v = hs.groupby("qid").val.cumsum() - hs.val
    cs_a = hs.groupby("qid").att.cumsum() - hs.att
    hs["ayA"] = (cs_v + K_PRIOR * lg) / (cs_a + K_PRIOR)                               # past-only, shrunk
    hs["n_prior"] = hs.groupby("qid").cumcount()
    # team continuity: previous starter and primary passer over the last 6 games
    hs = hs.sort_values(["team", "date"]).reset_index(drop=True)
    hs["prev_q"] = hs.groupby("team").qid.shift(1)
    hs["qb_change"] = ((hs.qid != hs.prev_q) & hs.prev_q.notna()).astype(float)
    # SAME-SEASON primary: the modal starter of this team's earlier games IN THE SAME SEASON (needs >=3). Using last season's games flagged every new
    # franchise QB in weeks 1-3 as a "backup" (fixed 2026-10-07: that mixed offseason QB turnover with injuries/benchings).
    hs["season_key"] = (hs.date.dt.year - (hs.date.dt.month < 3)).astype(int)
    top = []
    for (team, sk), grp in hs.groupby(["team", "season_key"]):
        q = grp.qid.tolist()
        tops = []
        for i in range(len(q)):
            win = q[:i]
            tops.append(max(set(win), key=win.count) if len(win) >= 3 else None)
        top.append(pd.Series(tops, index=grp.index))
    hs["top6"] = pd.concat(top)
    hs["backup"] = ((hs.top6.notna()) & (hs.qid != hs.top6)).astype(float)
    feat = hs[["id", "side", "ayA", "n_prior", "qb_change", "backup", "qname"]]
    h, a = feat[feat.side == "h"].drop(columns="side").add_suffix("_h").rename(columns={"id_h": "id"}), feat[feat.side == "a"].drop(columns="side").add_suffix("_a").rename(columns={"id_a": "id"})
    r = g.merge(h, on="id").merge(a, on="id")
    r["real_margin"] = r.hp - r.ap
    r["res_margin"] = r.real_margin - r.exp_home
    r["res_total"] = r.hp + r.ap - r.ou
    r["qb_quality_diff"] = r.ayA_h - r.ayA_a
    r["qb_quality_sum"] = r.ayA_h + r.ayA_a
    r["qb_change_diff"] = r.qb_change_h - r.qb_change_a
    r["backup_diff"] = r.backup_h - r.backup_a
    r["season"] = r.schedule_season.astype(int)
    r = r[(r.n_prior_h >= 1) & (r.n_prior_a >= 1)]
    return r.reset_index(drop=True)


def holm(ps):
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def run() -> dict:
    r = build()
    tr, te = r.season <= 2019, r.season >= 2020
    tests = {"margin_resid~qb_quality_diff": ("res_margin", "qb_quality_diff"), "margin_resid~qb_change_diff": ("res_margin", "qb_change_diff"),
             "margin_resid~backup_diff": ("res_margin", "backup_diff"), "total_resid~qb_quality_sum": ("res_total", "qb_quality_sum"),
             "REALISED margin~qb_quality_diff (sanity)": ("real_margin", "qb_quality_diff"), "REALISED margin~backup_diff (sanity)": ("real_margin", "backup_diff")}
    res, raw = {"n_games": len(r), "seasons": [int(r.season.min()), int(r.season.max())], "share_games_with_qb_change": float(((r.qb_change_h + r.qb_change_a) > 0).mean()),
                "share_games_with_backup": float(((r.backup_h + r.backup_a) > 0).mean())}, {}
    for name, (y, x) in tests.items():
        a = sm.OLS(r.loc[tr, y], sm.add_constant(r.loc[tr, x])).fit(cov_type="HC1")
        b = sm.OLS(r.loc[te, y], sm.add_constant(r.loc[te, x])).fit(cov_type="HC1")
        c = sm.OLS(r[y], sm.add_constant(r[x])).fit(cov_type="HC1")
        res[name] = {"beta_all": float(c.params[x]), "se_all": float(c.bse[x]), "p_all": float(c.pvalues[x]), "beta_train": float(a.params[x]), "p_train": float(a.pvalues[x]),
                     "beta_test": float(b.params[x]), "p_test": float(b.pvalues[x]), "x_sd": float(r[x].std()), "r2_all": float(c.rsquared)}
        if "sanity" not in name:
            raw[name] = float(a.pvalues[x])
    adj = holm(raw)
    for k, v in adj.items():
        q = res[k]
        q["p_holm_train"] = v
        q["accepted"] = bool(v < 0.05 and np.sign(q["beta_train"]) == np.sign(q["beta_test"]) and q["p_test"] < 0.05)
    # games where a backup starts: ATS split
    for nm, sel in (("home backup (away not)", (r.backup_h == 1) & (r.backup_a == 0)), ("away backup (home not)", (r.backup_a == 1) & (r.backup_h == 0))):
        x = r[sel]
        res[f"ats_{nm}"] = {"n": int(len(x)), "mean_margin_resid": float(x.res_margin.mean()), "se": float(x.res_margin.std() / np.sqrt(max(len(x), 1))), "home_cover_rate": float((x.res_margin > 0).mean())}
    return res


if __name__ == "__main__":
    out = run()
    (DATA / "qb_effects_nfl.json").write_text(json.dumps(out, indent=1))
    print(f"games {out['n_games']} ({out['seasons'][0]}-{out['seasons'][1]}) | games with a QB change {out['share_games_with_qb_change']:.1%} | with a backup/unusual starter {out['share_games_with_backup']:.1%}")
    for k, v in out.items():
        if isinstance(v, dict) and "beta_all" in v:
            tag = ("ACCEPTED" if v.get("accepted") else "not beyond the line") if "accepted" in v else "sanity"
            print(f" {k:<44} beta {v['beta_all']:+.3f} (p={v['p_all']:.4f}, R2={v['r2_all']:.4f}) | train {v['beta_train']:+.3f} p={v['p_train']:.3f} | test {v['beta_test']:+.3f} p={v['p_test']:.3f} -> {tag}")
        elif isinstance(v, dict) and k.startswith("ats_"):
            print(f" {k:<30} n={v['n']} mean margin resid vs line {v['mean_margin_resid']:+.2f} (se {v['se']:.2f}) | home cover rate {v['home_cover_rate']:.1%}")

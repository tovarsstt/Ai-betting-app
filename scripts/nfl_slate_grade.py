"""Grade a past slate run (nfl_slate_box/props) against what really happened.
Games: sim vs market vs 30/70 blend on winner, Brier/logloss, margin and total error, ATS and O/U.  Players: sim mean vs actual (nflverse pbp) by stat, bias and MAE,
anytime-TD calibration.  Usage: python3 scripts/nfl_slate_grade.py --date 20261101 --dir SLATE_DIR [--dir2 OVERRIDE_DIR] --lines data/closing_lines_20261101.json"""
import sys, json, pickle, argparse
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_sim_service as ns

PBP = Path("/tmp/kg/nflverse/pbp_2026.csv.gz")
lgt = lambda p: float(np.log(p / (1 - p)))
sg = lambda z: 1 / (1 + np.exp(-z))


def devig_ml(h, a):
    imp = lambda o: 100 / (o + 100) if o > 0 else -o / (-o + 100)
    return imp(h) / (imp(h) + imp(a))


def finals(date):
    fx = lambda t: ns._ABBR_ALIASES.get(t, t)
    out = {}
    for e in ns._fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date}")["events"]:
        c = e["competitions"][0]["competitors"]
        h = next(x for x in c if x["homeAway"] == "home"); a = next(x for x in c if x["homeAway"] == "away")
        out[f"{fx(a['team']['abbreviation'])}@{fx(h['team']['abbreviation'])}"] = (int(a["score"]), int(h["score"]))
    return out


def actual_players(game_date):
    cols = ["game_id", "game_date", "posteam", "pass_attempt", "rush_attempt", "complete_pass", "passing_yards", "receiving_yards", "rushing_yards", "passer_player_name", "receiver_player_name",
            "rusher_player_name", "rush_touchdown", "pass_touchdown", "interception", "sack", "two_point_attempt"]
    d = pd.read_csv(PBP, usecols=cols, low_memory=False)
    d = d[(d.game_date == game_date) & (d.two_point_attempt != 1) & d.posteam.notna()]
    A = {}
    add = lambda team, key, v: A.__setitem__((team, key), A.get((team, key), 0.0) + float(v))
    for r in d.itertuples():
        t = r.posteam
        if r.pass_attempt == 1 and isinstance(r.passer_player_name, str):
            add(t, f"{r.passer_player_name} att", 1); add(t, f"{r.passer_player_name} comp", r.complete_pass or 0)
            add(t, f"{r.passer_player_name} passY", 0 if pd.isna(r.passing_yards) else r.passing_yards); add(t, f"{r.passer_player_name} passTD", r.pass_touchdown or 0); add(t, f"{r.passer_player_name} INT", r.interception or 0)
        if r.complete_pass == 1 and isinstance(r.receiver_player_name, str):
            add(t, f"{r.receiver_player_name} rec", 1); add(t, f"{r.receiver_player_name} recY", r.receiving_yards or 0)
            if r.pass_touchdown == 1: add(t, f"{r.receiver_player_name} recTD", 1)
        if r.rush_attempt == 1 and r.sack != 1 and isinstance(r.rusher_player_name, str):
            add(t, f"{r.rusher_player_name} car", 1); add(t, f"{r.rusher_player_name} rushY", r.rushing_yards or 0)
            if r.rush_touchdown == 1: add(t, f"{r.rusher_player_name} rushTD", 1)
    return A


def grade_games(games, lines, W_SIM=0.3):
    rows = []
    for k, g in games.items():
        P = g["P"]; H, A = P["H"], P["A"]; M = H - A; T = H + A; ah, hh = g["actual"][0], g["actual"][1]
        L = lines[k]; mk = devig_ml(L["ml"][1], L["ml"][0]) if False else None
        away, home = k.split("@")
        h_ml, a_ml = L["ml"][0], L["ml"][1]          # stored as [home, away]
        mk = devig_ml(h_ml, a_ml); ps = float((M > 0).mean() + .5 * (M == 0).mean()); pb = sg(W_SIM * lgt(ps) + (1 - W_SIM) * lgt(mk)); y = 1.0 if hh > ah else 0.0
        sp, tot = L["spread"], L["total"]
        rows.append(dict(game=k, sim_a=float(A.mean()), sim_h=float(H.mean()), act_a=ah, act_h=hh, p_sim=ps, p_mkt=mk, p_bl=pb, y=y, sim_m=float(M.mean()), mkt_m=-sp, act_m=hh - ah,
                         sim_t=float(T.mean()), mkt_t=tot, act_t=hh + ah, sp=sp, p_cover_home=float(((M + sp) > 0).mean()), cover_home=float((hh - ah + sp) > 0) if (hh - ah + sp) != 0 else np.nan,
                         p_over=float((T > tot).mean()), over=float((hh + ah) > tot) if (hh + ah) != tot else np.nan))
    return pd.DataFrame(rows)


def ll(p, y): p = np.clip(p, 1e-6, 1 - 1e-6); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def grade_players(games, act):
    rows = []
    for k, g in games.items():
        for key, v in g["P"].items():
            if "|" not in key or "Others" in key: continue
            team, rest = key.split("|", 1); st = rest.split(" ")[-1]; name = rest[: -(len(st) + 1)]
            if st not in ("passY", "recY", "rushY", "rec", "car", "comp", "passTD", "INT", "ATD", "att"): continue
            if st == "ATD":
                a = float(act.get((team, f"{name} rushTD"), 0) + act.get((team, f"{name} recTD"), 0) > 0)
            else:
                a = float(act.get((team, f"{name} {st}"), 0.0))
            rows.append(dict(game=k, team=team, name=name, stat=st, sim_mean=float(v.mean()), sim_med=float(np.median(v)), actual=a, p10=float(np.percentile(v, 10)), p90=float(np.percentile(v, 90))))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--date", default="20261101"); ap.add_argument("--dir", required=True); ap.add_argument("--dir2", default=""); ap.add_argument("--lines", required=True)
    a = ap.parse_args()
    games = pickle.load(open(Path(a.dir) / "slate_props.pkl", "rb"))
    if a.dir2: games.update(pickle.load(open(Path(a.dir2) / "slate_props.pkl", "rb")))
    fin = finals(a.date); lines = json.loads(Path(a.lines).read_text())
    games = {k: {**g, "actual": fin[k]} for k, g in games.items() if k in fin}
    G = grade_games(games, lines)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(G.round(2).to_string(index=False))
    y = G.y.values
    print(f"\nGANADOR acertado: sim {int(((G.p_sim > .5) == (G.y == 1)).sum())}/{len(G)} | mercado {int(((G.p_mkt > .5) == (G.y == 1)).sum())}/{len(G)}")
    print(f"LOGLOSS: sim {ll(G.p_sim.values, y):.3f} | mercado {ll(G.p_mkt.values, y):.3f} | 30/70 {ll(G.p_bl.values, y):.3f} | 50% {ll(np.full(len(y), .5), y):.3f}")
    print(f"BRIER: sim {np.mean((G.p_sim - y) ** 2):.3f} | mercado {np.mean((G.p_mkt - y) ** 2):.3f}")
    print(f"MARGEN: MAE sim {np.mean(abs(G.sim_m - G.act_m)):.1f} | MAE mercado {np.mean(abs(G.mkt_m - G.act_m)):.1f} | sesgo sim {np.mean(G.sim_m - G.act_m):+.1f} mercado {np.mean(G.mkt_m - G.act_m):+.1f}")
    print(f"TOTAL: MAE sim {np.mean(abs(G.sim_t - G.act_t)):.1f} | MAE mercado {np.mean(abs(G.mkt_t - G.act_t)):.1f} | sesgo sim {np.mean(G.sim_t - G.act_t):+.1f} mercado {np.mean(G.mkt_t - G.act_t):+.1f}")
    ats = G.dropna(subset=["cover_home"]); ou = G.dropna(subset=["over"])
    print(f"ATS (lado local DK): sim dice cubre si P>50%: acierta {int(((ats.p_cover_home > .5) == (ats.cover_home == 1)).sum())}/{len(ats)} | O/U: sim dice over si P>50%: acierta {int(((ou.p_over > .5) == (ou.over == 1)).sum())}/{len(ou)}")
    act = actual_players(pd.to_datetime(a.date).strftime("%Y-%m-%d"))
    PL = grade_players(games, act); PL.to_pickle("/tmp/slate_players_graded.pkl")
    print("\nJUGADORES (todos los que modelo): sesgo medio (sim - real) y MAE por stat")
    for st, g in PL[PL.stat != "ATD"].groupby("stat"):
        g = g[g.sim_mean >= {"passY": 100, "recY": 15, "rushY": 15, "rec": 1.5, "car": 4, "comp": 5, "passTD": .5, "INT": .3, "att": 5}[st]]
        print(f"  {st:7s} n={len(g):3d} sim medio {g.sim_mean.mean():6.1f} real medio {g.actual.mean():6.1f} sesgo {np.mean(g.sim_mean - g.actual):+6.1f} MAE {np.mean(abs(g.sim_mean - g.actual)):6.1f} corr {np.corrcoef(g.sim_mean, g.actual)[0,1]:.2f} | real dentro p10-p90: {((g.actual>=g.p10)&(g.actual<=g.p90)).mean()*100:.0f}%")
    atd = PL[PL.stat == "ATD"]
    print("\nTD ANYTIME calibracion:")
    for lo, hi in ((0, .1), (.1, .25), (.25, .4), (.4, .55), (.55, 1.01)):
        b = atd[(atd.sim_mean >= lo) & (atd.sim_mean < hi)]
        if len(b): print(f"  sim {lo:.2f}-{min(hi,1):.2f}: n={len(b):3d} sim medio {b.sim_mean.mean()*100:4.0f}% real {b.actual.mean()*100:4.0f}%")
    # persistent log: one line per graded slate so the sim's bias/skill accumulates across weeks instead of resetting every Sunday
    qb = PL[(PL.stat == "passY")]; rb1 = PL[PL.stat == "rushY"].sort_values("sim_mean", ascending=False).groupby(["game", "team"]).head(1)
    rec = {"date": a.date, "n_games": len(G), "winner_sim": int(((G.p_sim > .5) == (G.y == 1)).sum()), "winner_mkt": int(((G.p_mkt > .5) == (G.y == 1)).sum()),
           "logloss_sim": round(ll(G.p_sim.values, y), 4), "logloss_mkt": round(ll(G.p_mkt.values, y), 4), "total_bias_sim": round(float(np.mean(G.sim_t - G.act_t)), 2), "total_bias_mkt": round(float(np.mean(G.mkt_t - G.act_t)), 2),
           "qb_passY_bias": round(float((qb.sim_mean - qb.actual).mean()), 1), "qb_passY_corr": round(float(np.corrcoef(qb.sim_mean, qb.actual)[0, 1]), 2),
           "rb1_rushY_bias": round(float((rb1.sim_mean - rb1.actual).mean()), 1), "rb1_rushY_corr": round(float(np.corrcoef(rb1.sim_mean, rb1.actual)[0, 1]), 2),
           "atd_top25_sim": round(float(atd.sort_values("sim_mean", ascending=False).head(25).sim_mean.mean()), 3), "atd_top25_real": round(float(atd.sort_values("sim_mean", ascending=False).head(25).actual.mean()), 3)}
    with open(HERE.parent / "data" / "slate_grades.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("\nlogged:", rec)

#!/usr/bin/env python3
"""nfl_gameday.py — one entry point for NFL game day (replaces the pile of scratch scripts used on 2026-11-08).

  python3 scripts/nfl_gameday.py health                                   data/model freshness + what to restore
  python3 scripts/nfl_gameday.py inactives [YYYYMMDD]                     write data/inactives_YYYYMMDD.json from ESPN (Out/Doubtful/IR per game)
  python3 scripts/nfl_gameday.py live AWAY@HOME[,AWAY@HOME] [-n 40000]    re-sim the REST of a game from the real ESPN state: lineup layer + in-game injuries
  python3 scripts/nfl_gameday.py board AWAY@HOME --sim FILE.npy --stake data/stake_lines_*.json   price every Stake market: sim / market / 30-70 anchored, EV at the Stake price

The sim engine (nfl_sim_service, nfl_slate_box, nfl_live, lineup_espn) lives in this same scripts/ directory.
What is new vs the pregame slate run: the sim sees OL/DL/CB/RB/TE starters that are out (ESPN depth chart, lineup_espn.py) and anyone hurt DURING the game (drive plays
'X was injured during the play'). The measured effect of each lost starter is small (lineup_espn.py docstring) - the layer closes a blind spot, it is not an edge.
388-game walk-forward (wf_2024|2025.jsonl): the market is the better center (sim adds ~0 once the close is in), so `board` always shows the anchored column next to
the pure sim and ranks by anchored EV.
"""
import os, sys, re, json, time, argparse
from pathlib import Path
for _k in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_k, "1")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "data"
BASE = ROOT                                                  # engine + data live in the same repo/branch now
sys.path.insert(0, str(BASE / "scripts"))
import numpy as np

SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
W_SIM = 0.3                                                  # 30/70 logit blend: best walk-forward weight (nfl_slate_report.py)
ABBR = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"}
PLAYTEXT = {"ARZ": "ARI", "HST": "HOU", "BLT": "BAL", "CLV": "CLE", "JAC": "JAX", "LAR": "LA", "WSH": "WAS"}   # abbreviations ESPN uses inside play text


def dpath(name):
    p = OUT / name
    return p if p.exists() else BASE / "data" / name


def _g(u):
    import urllib.request
    return json.load(urllib.request.urlopen(urllib.request.Request(u), timeout=25))


def _sg(x): return 1 / (1 + np.exp(-x))
def _lg(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def scoreboard(date=None):
    d = _g(f"{SB}/scoreboard" + (f"?dates={date}" if date else ""))
    out = {}
    for e in d["events"]:
        c = e["competitions"][0]
        a = next(x for x in c["competitors"] if x["homeAway"] == "away"); h = next(x for x in c["competitors"] if x["homeAway"] == "home")
        ab = lambda x: ABBR.get(x["team"]["abbreviation"], x["team"]["abbreviation"])
        out[f"{ab(a)}@{ab(h)}"] = {"id": e["id"], "state": e["status"]["type"]["state"], "detail": e["status"]["type"]["shortDetail"], "home": ab(h), "away": ab(a),
                                   "hs": int(h["score"] or 0), "as": int(a["score"] or 0), "home_id": h["team"]["id"], "away_id": a["team"]["id"], "date": e["date"]}
    return out


# ─────────────────────────────── health
def health():
    import pandas as pd
    print("== data / model health", time.strftime("%Y-%m-%d %H:%M"))
    pbp = Path("/tmp/kg/nflverse/pbp_2026.csv.gz")
    if pbp.exists():
        d = pd.read_csv(pbp, usecols=["game_date", "week"], low_memory=False)
        print(f"pbp_2026: through {d.game_date.max()} (week {int(d.week.max())})")
        try:
            fin = [k for k, v in scoreboard().items() if v["state"] == "post"]
            print(f"  ESPN board has {len(fin)} finals today; nflverse publishes the next morning, so props/params built from pbp are ~1 week old on game day")
        except Exception as e:
            print("  ESPN board unreachable:", repr(e)[:60])
    else:
        print("pbp_2026: MISSING (/tmp is volatile) -> restore from the nflverse-data 'pbp' release (needs the user's OK to download)")
    print("nflverse depth/injury files:", "present" if Path("/tmp/kg/nflverse/avail").exists() else "MISSING -> lineup_for falls back to the ESPN depth-chart layer (lineup_espn.py)")
    for f in ("data/nfl_drive_sim_params.pkl", "data/sim_calibration.json", "data/nfl_box_calib_2026_team.csv"):
        p = BASE / f
        print(f"{f}:", f"{(time.time() - p.stat().st_mtime) / 86400:.1f} days old" if p.exists() else "MISSING")
    wf = dpath("wf_2026_live.jsonl")
    print("2026 sim-vs-market ledger:", f"{sum(1 for _ in open(wf))} games" if wf.exists() else "empty")


# ─────────────────────────────── inactives
def inactives(date):
    OUT.mkdir(exist_ok=True); path = OUT / f"inactives_{date}.json"
    cur = json.loads(path.read_text()) if path.exists() else {}
    for k, v in scoreboard(date).items():
        d = _g(f"{SB}/summary?event={v['id']}")
        names = [i["athlete"]["displayName"] for t in d.get("injuries", []) for i in t["injuries"] if i["status"] in ("Out", "Doubtful", "Injured Reserve")]
        if names: cur[k] = sorted(set(cur.get(k, [])) | set(names))
    path.write_text(json.dumps(cur, indent=1)); print("wrote", path, {k: len(v) for k, v in cur.items()})


# ─────────────────────────────── in-game injuries
def ingame_injuries(event_id):
    """[(team_abbr_in_play_text, 'R.Lopez')] for players hurt during THIS game (ESPN drive play text)."""
    d = _g(f"{SB}/summary?event={event_id}"); out = []
    for key in ("previous", "current"):
        dr = d.get("drives", {}).get(key)
        for x in ([dr] if isinstance(dr, dict) else dr or []):
            for p in x.get("plays", []):
                for m in re.finditer(r"\b([A-Z]{2,3})-([A-Z]\.[A-Za-z'\-]+(?: (?:Jr|Sr|II|III|IV)\.?)?) was injured", p.get("text", "")):
                    out.append((m.group(1), m.group(2)))
    return sorted(set(out))


def _resolve(short, names):
    """'R.Lopez' -> full name from a roster list (first initial + last name); None if ambiguous."""
    fi, last = short.split(".", 1)
    last = re.sub(r"\s+(Jr|Sr|II|III|IV)\.?$", "", last).lower()
    hits = [n for n in names if n.split()[0][:1].upper() == fi and last in n.lower()]
    return hits[0] if len(hits) == 1 else None


# ─────────────────────────────── live
def _work(a):
    import nfl_slate_box as sb
    home, away, qh, qa, avail, start, b, per = a
    g = sb._nds.GameSim(sb._par, home, away, qh, qa, eff=sb._par["boots"][b], seed=8881 * 1000 + b, neutral=False, avail=avail)
    out = np.zeros((per, 3 + 2 * len(sb.KEYS)), dtype=np.float32)
    for i in range(per):
        o = g.play_game(start=start); row = [o["score"][0], o["score"][1], o["ot"]]
        for s in (0, 1): row += [o["stat"][s].get(k, 0) for k in sb.KEYS]
        out[i] = row
    return b, out


def live(games, n=40000):
    import multiprocessing as mp
    import nfl_slate_box as sb, nfl_live as NL, nfl_sim_service as ns, lineup_espn as le
    S = NL.states(); board_ = scoreboard(); nb = len(sb._par["boots"]); per = -(-n // nb)
    ip = dpath(f"inactives_{time.strftime('%Y%m%d')}.json"); INACT = json.loads(ip.read_text()) if ip.exists() else {}
    (OUT / "sim_runs").mkdir(parents=True, exist_ok=True)
    for gm in games:
        away, home = gm.split("@"); b = board_[gm]
        if b["state"] != "in":
            print(gm, "not in progress:", b["detail"], f"(score {b['as']}-{b['hs']})"); continue
        st = S[(home, away)]; start = NL.sim_start(st)
        ctx = ns.espn_context(home, away); inj = list(ctx.get("injuries") or [])
        for nm in INACT.get(gm, []):
            inj.append({"team": None, "player": nm, "status": "Out"})
        rosters = {t: [a["fullName"] for grp in _g(f"{SB}/teams/{tid}/roster")["athletes"] for a in grp["items"]] for t, tid in ((home, b["home_id"]), (away, b["away_id"]))}
        for it in inj:                                                  # attach the team to inactives that only have a name
            if it["team"] is None: it["team"] = next((t for t in (home, away) if it["player"] in rosters[t]), None)
        extra = {}
        for ab, short in ingame_injuries(b["id"]):
            tm = PLAYTEXT.get(ab, ab); tm = tm if tm in (home, away) else None
            full = _resolve(short, rosters[tm]) if tm else None
            if full: extra.setdefault(tm, []).append(full)
        av, detail = le.avail_from_espn(home, away, inj, extra)
        qh = ns.choose_qb(sb._par, home, None, (ctx.get("depth_qbs") or {}).get(home), inj); qa = ns.choose_qb(sb._par, away, None, (ctx.get("depth_qbs") or {}).get(away), inj)
        print(gm, "STATE", st["score"], st["detail"], "| lineup", {k: {a: v for a, v in d_.items() if v} for k, d_ in av.items()}, "| hurt in game:", extra or "none")
        with mp.get_context("fork").Pool(min(12, os.cpu_count() or 4)) as p:
            r = sorted(p.map(_work, [(home, away, qh["id"], qa["id"], av, start, k, per) for k in range(nb)]), key=lambda x: x[0])
        res = np.concatenate([x[1] for x in r]).astype(np.float64); np.save(OUT / "sim_runs" / f"live_{away}@{home}.npy", res)
        print(f"  {home} win {(res[:,0]>res[:,1]).mean()*100:.1f}%  mean {home} {res[:,0].mean():.1f} / {away} {res[:,1].mean():.1f}  (n={len(res)}; saved data/sim_runs/live_{away}@{home}.npy)")


# ─────────────────────────────── board (price the Stake markets)
def _dv(a, b): pa, pb = 1 / a, 1 / b; return pa / (pa + pb)


def board(sim_path, stake_path):
    """stake json: {"home":"MIN","away":"BUF","ml":{"home":2.41,"away":1.54},"spread":{"3.5":[home_plus_price, away_minus_price],...},
                   "total":{"44.5":[over,under],...},"team_total":{"home":{"20.5":[over,under]},"away":{"23.5":[over,under]}}}"""
    X = np.load(sim_path); st = json.loads(Path(stake_path).read_text())
    hp, ap = X[:, 0], X[:, 1]; m = ap - hp; T = ap + hp
    rows = []
    def add(name, price, p_sim, pair):
        pm = _dv(price, pair); pa = float(_sg(W_SIM * _lg(p_sim) + (1 - W_SIM) * _lg(pm)))
        rows.append((name, price, float(p_sim), pm, pa, pa * price - 1, p_sim * price - 1))
    if "ml" in st:
        pw = float(((m > 0) + .5 * (m == 0)).mean())
        add(f"{st['away']} ML", st["ml"]["away"], pw, st["ml"]["home"]); add(f"{st['home']} ML", st["ml"]["home"], 1 - pw, st["ml"]["away"])
    for ln, (hpl, amin) in st.get("spread", {}).items():
        l = float(ln); add(f"{st['away']} -{l}", amin, (m > l).mean(), hpl); add(f"{st['home']} +{l}", hpl, (m < l).mean(), amin)
    for ln, (ov, un) in st.get("total", {}).items():
        l = float(ln); add(f"Over {l}", ov, (T > l).mean(), un); add(f"Under {l}", un, (T < l).mean(), ov)
    for side, key, arr in (("home", st["home"], hp), ("away", st["away"], ap)):
        for ln, (ov, un) in st.get("team_total", {}).get(side, {}).items():
            l = float(ln); add(f"{key} over {l}", ov, (arr > l).mean(), un); add(f"{key} under {l}", un, (arr < l).mean(), ov)
    rows.sort(key=lambda r: -r[5])
    print(f"{st['away']} @ {st['home']} | sim n={len(X)}  total mean {T.mean():.1f}  margin({st['away']}) {m.mean():+.1f} | sim weight in the anchor {W_SIM}")
    print(f"{'bet':14s} price | p_sim  p_mkt  p_anch | EV_anch  EV_sim")
    for r in rows: print(f"{r[0]:14s} {r[1]:.2f} | {r[2]*100:5.1f}  {r[3]*100:5.1f}  {r[4]*100:5.1f} | {r[5]*100:+6.1f}%  {r[6]*100:+6.1f}%")
    best = rows[0]
    print(f"\nbest anchored EV: {best[0]} @ {best[1]:.2f} = {best[5]*100:+.1f}%" + ("  -> no value after the vig: pass, or a tiny conviction stake" if best[5] < 0.02 else ""))


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    p = sub.add_parser("inactives"); p.add_argument("date", nargs="?", default=time.strftime("%Y%m%d"))
    p = sub.add_parser("live"); p.add_argument("games"); p.add_argument("-n", type=int, default=40000)
    p = sub.add_parser("board"); p.add_argument("game"); p.add_argument("--sim", required=True); p.add_argument("--stake", required=True)
    a = ap.parse_args()
    if a.cmd == "health": health()
    elif a.cmd == "inactives": inactives(a.date)
    elif a.cmd == "live": live(a.games.split(","), a.n)
    elif a.cmd == "board": board(a.sim, a.stake)


if __name__ == "__main__":
    main()

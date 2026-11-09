"""Simulate every game on an NFL slate drive-by-drive and keep the per-game team box score.

Usage: python3 scripts/nfl_slate_box.py [YYYYMMDD] [--n 40000] [--only BUF,BAL]
Writes one .npy per game (columns = h_pts, a_pts, ot, then KEYS for home, KEYS for away)
plus slate_summary.json in OUT_DIR. Uses ESPN injuries/depth (free) and nflverse availability.
No betting lines are read here.
"""
import sys, json, time, argparse, multiprocessing as mp
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_sim_service as ns
import nfl_roster as nr

KEYS = ["att", "comp", "pyds", "rush", "ryds", "sacks", "ints", "td", "ptd", "fgm", "fga", "fum"]
POOL = 12
_nds, _par = ns._load()


def slate(date: str):
    d = ns._fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date}")
    out = []
    for e in d["events"]:
        c = e["competitions"][0]["competitors"]
        fix = lambda t: ns._ABBR_ALIASES.get(t, t)                 # ESPN LAR/WSH -> nflverse LA/WAS
        home = fix(next(x for x in c if x["homeAway"] == "home")["team"]["abbreviation"])
        away = fix(next(x for x in c if x["homeAway"] == "away")["team"]["abbreviation"])
        out.append({"id": e["id"], "date": e["date"], "home": home, "away": away})
    return out


def lineup_for(home, away, injuries, force_active=None):
    try:
        import nfl_availability as av
        lu = av.current_availability([home, away], injuries, force_active)
        strip = lambda t: {k: v for k, v in (lu.get(t, {}).get("counts") or {}).items() if k != "qb_lost"}
        return {"home": strip(home), "away": strip(away)}, lu
    except Exception as e:
        print("lineup data missing (nflverse):", repr(e)[:100], "-> ESPN depth-chart fallback")
        try:
            import lineup_espn as le
            res, detail = le.avail_from_espn(home, away, injuries or [])
            print("  ESPN lineup layer:", {"home": {k: v for k, v in res["home"].items() if v}, "away": {k: v for k, v in res["away"].items() if v}}, detail, flush=True)
            return res, {home: {"counts": res["home"], "detail": detail[home]}, away: {"counts": res["away"], "detail": detail[away]}}
        except Exception as e2:
            print("lineup fallback failed:", repr(e2)[:100])
            return None, {}


def _work(args):
    home, away, qh, qa, avail, b, per = args
    g = _nds.GameSim(_par, home, away, qh, qa, eff=_par["boots"][b], seed=991 * 1000 + b, neutral=False, avail=avail)
    out = np.zeros((per, 3 + 2 * len(KEYS)), dtype=np.float32)
    for i in range(per):
        o = g.play_game()
        row = [o["score"][0], o["score"][1], o["ot"]]
        for s in (0, 1):
            st = o["stat"][s]
            row += [st.get(k, 0) for k in KEYS]
        out[i] = row
    return b, out


def tilt(X):
    shift = float(json.loads(ns._CAL.read_text()).get("total_shift", 0.0))
    T = X[:, 0] + X[:, 1]
    Tc = T - T.mean()
    lo, hi = -0.5, 0.5
    for _ in range(60):
        lam = (lo + hi) / 2
        w = np.exp(lam * Tc)
        m = float((w * Tc).sum() / w.sum())
        lo, hi = (lam, hi) if m < shift else (lo, lam)
    w = np.exp(lam * Tc)
    w /= w.sum()
    return X[np.random.default_rng(777).choice(len(X), size=len(X), p=w)]


def run_game(g, n, outdir, pool, inactives=None):
    home, away = g["home"], g["away"]
    ctx = ns.espn_context(home, away)
    inj = list(ctx.get("injuries") or [])
    ev = ctx["event"]
    ids = {home: ev["home_espn_id"], away: ev["away_espn_id"]}
    offense, posted, rosters, active_override = {}, {}, {}, []
    for tm in (home, away):                                  # IR / suspended / traded-away players the ESPN injury report omits + official inactives
        ro = nr.roster(ids[tm], tm)
        wire = nr.tx_state(tm)                                # ESPN's roster endpoint lags the wire: IR/waived/traded moves override it
        gone = {k for k, v in wire.items() if v == "out"}
        offense[tm] = sorted(k for k, (n, _) in ro["offense"].items() if nr.full(n) not in gone)
        inj += ro["out"] + [{"team": tm, "player": n, "pos": p, "status": "Injured Reserve"} for k, (n, p) in ro["offense"].items() if nr.full(n) in gone]
        posted[tm], names = nr.inactives(ev["event_id"], ids[tm], ro["pos"])
        rosters[tm] = ro
        inj += [{"team": tm, "player": nm, "pos": ro["pos"].get(nr.sig(nm), ""), "status": "Out"} for nm in names]
    if inactives and f"{away}@{home}" in inactives:       # inactives scraped from the ESPN box-score page (the core API only fills `active` at kickoff)
        for nm in inactives[f"{away}@{home}"]:
            tm = next((t for t in (home, away) if nr.sig(nm) in rosters[t]["pos"]), None)
            if tm:
                inj.append({"team": tm, "player": nm, "pos": rosters[tm]["pos"].get(nr.sig(nm), ""), "status": "Out"})
                offense[tm] = [k for k in offense[tm] if k != nr.sig(nm)]
        posted = {home: True, away: True}
        ina = {nr.sig(x) for x in inactives[f"{away}@{home}"]}
        # the official list overrides the injury report: Out/Doubtful/Questionable players who are NOT inactive are playing
        cleared = [i["player"] for i in inj if str(i.get("status", "")).lower() in ("out", "doubtful", "questionable") and nr.sig(i["player"]) not in ina]
        active_override += cleared
        inj = [i for i in inj if i["player"] not in cleared]
    active_override += list((inactives or {}).get("_force_active", []))
    force = {nr.sig(x) for x in (inactives or {}).get("_force_active", [])}
    if force:                                                   # ESPN's roster lags (e.g. 'designated to return' RBs still in the IR group): the user/news confirm they play
        inj = [i for i in inj if nr.sig(i["player"]) not in force]
        for tm in (home, away):
            offense[tm] = sorted(set(offense[tm]) | {k for k in force if k in rosters[tm]["pos"]})
    qh = ns.choose_qb(_par, home, None, (ctx.get("depth_qbs") or {}).get(home), inj)
    qa = ns.choose_qb(_par, away, None, (ctx.get("depth_qbs") or {}).get(away), inj)
    avail, lu = lineup_for(home, away, inj, active_override)
    nb = len(_par["boots"])
    per = -(-n // nb)
    res = sorted(pool.map(_work, [(home, away, qh["id"], qa["id"], avail, b, per) for b in range(nb)]))
    X = tilt(np.concatenate([r[1] for r in res]))
    np.save(outdir / f"{away}@{home}.npy", X)
    M = X[:, 0] - X[:, 1]
    T = X[:, 0] + X[:, 1]
    return {
        "home": home, "away": away, "date": g["date"], "qb_home": qh.get("name"), "qb_away": qa.get("name"),
        "p_home": float((M > 0).mean() + 0.5 * (M == 0).mean()), "mean_home": float(X[:, 0].mean()),
        "mean_away": float(X[:, 1].mean()), "mean_total": float(T.mean()), "sd_margin": float(M.std()),
        "avail": avail, "injuries_full": inj, "offense": offense, "inactives_posted": posted,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="20261101")
    ap.add_argument("--n", type=int, default=40000)
    ap.add_argument("--only", default="")
    ap.add_argument("--inactives", default="")
    ap.add_argument("--out", default="/private/tmp/claude-501/-Users-josetovar-Documents-APP-AI-BETS/d2188ef8-37ad-4cf1-b93d-e4a6e86121e4/scratchpad/slate")
    a = ap.parse_args()
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    games = slate(a.date)
    inactives = json.loads(Path(a.inactives).read_text()) if a.inactives else None
    if a.only:
        keep = set(a.only.split(","))
        games = [g for g in games if g["home"] in keep or g["away"] in keep]
    sfile = outdir / "slate_summary.json"
    summary = json.loads(sfile.read_text()) if sfile.exists() else []            # resume: keep finished games
    done = {(r["home"], r["away"]) for r in summary}
    games = [g for g in games if (g["home"], g["away"]) not in done]
    with mp.get_context("fork").Pool(POOL) as pool:
        for g in games:
            t = time.time()
            r = run_game(g, a.n, outdir, pool, inactives)
            summary.append(r)
            print(f"{r['away']}@{r['home']} {r['mean_away']:.1f}-{r['mean_home']:.1f} P(home)={r['p_home']:.3f} tot={r['mean_total']:.1f} "
                  f"QB {r['qb_away']}/{r['qb_home']} ({time.time()-t:.0f}s)", flush=True)
            (outdir / "slate_summary.json").write_text(json.dumps(summary, indent=1, default=str))

"""Player-prop distributions for every simulated game of the slate (follows nfl_slate_box.py).

Team box (100% sim) -> players: completions / carries split Dirichlet-multinomial with REAL 2026 play-by-play shares (last 6 team games, recency weighted),
yards by lognormal-weighted yards-per-touch normalised to the team total, TDs by volume-shrunk TD shares. Players Out/Doubtful/IR/Suspended are removed
(their volume is redistributed); Questionable play with P=QUESTIONABLE_PLAY. Team yard/carry factors come from the measured sim-vs-real team box
(shrunk w = n/(n+8)). Props are anchored to nothing here: this is the model view; compare to the book line with stake_props_ev.py logic (90/10 anchor).

Usage: python3 scripts/nfl_slate_props.py [--dir SLATE_DIR]   (reads *.npy + slate_summary.json from nfl_slate_box.py)
"""
import sys, json, argparse, re, pickle, zlib
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PBP = Path("/tmp/kg/nflverse/pbp_2026.csv.gz")
KEYS = ["att", "comp", "pyds", "rush", "ryds", "sacks", "ints", "td", "ptd", "fgm", "fga", "fum"]
OUT_STATUS = {"out", "doubtful", "injured reserve", "suspension", "ir", "pup"}
QUESTIONABLE_PLAY = 0.65
KAPPA_REC, KAPPA_CAR, KAPPA_TD = 22.0, 16.0, 6.0
TD_PRIOR = 8.0          # pseudo-TDs spread by volume share: 6-8 games of TD counts are noisy, so TD shares lean on volume
WINDOW = 6


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def sig(name: str) -> str:
    """first initial + last name (handles 'D.Kincaid' and 'Dalton Kincaid')"""
    parts = re.split(r"[\s.]+", name.strip())
    parts = [p for p in parts if p]
    return (parts[0][0] + norm(parts[-1])).lower() if parts else ""


def load_pbp() -> pd.DataFrame:
    cols = ["game_id", "week", "posteam", "play_type", "complete_pass", "pass_attempt", "rush_attempt", "yards_gained", "receiver_player_name", "rusher_player_name",
            "passer_player_name", "pass_touchdown", "rush_touchdown", "qb_scramble", "sack", "two_point_attempt"]
    d = pd.read_csv(PBP, usecols=cols, low_memory=False)
    return d[(d.two_point_attempt != 1) & d.posteam.notna()]


def team_tables(d: pd.DataFrame, team: str, offense: set | None = None) -> dict:
    t = d[d.posteam == team]
    weeks = sorted(t.week.unique())[-WINDOW:]
    wt = {w: (1.0 if i >= len(weeks) - 3 else 0.6) for i, w in enumerate(weeks)}
    t = t[t.week.isin(weeks)].copy()
    t["w"] = t.week.map(wt)
    rec = t[(t.complete_pass == 1) & t.receiver_player_name.notna()]
    rec_cnt = rec.groupby("receiver_player_name").w.sum()
    rec_y = rec.assign(wy=rec.w * rec.yards_gained).groupby("receiver_player_name").wy.sum()
    car = t[(t.rush_attempt == 1) & (t.sack != 1) & t.rusher_player_name.notna()]
    car_cnt = car.groupby("rusher_player_name").w.sum()
    car_y = car.assign(wy=car.w * car.yards_gained).groupby("rusher_player_name").wy.sum()
    rtd = t[t.rush_touchdown == 1].groupby("rusher_player_name").w.sum()
    ctd = t[t.pass_touchdown == 1].groupby("receiver_player_name").w.sum()
    qb = t[t.pass_attempt == 1].groupby("passer_player_name").w.sum().sort_values(ascending=False)
    if offense is not None:                         # only players on the team's ACTIVE offense today (drops traded / cut / IR)
        keep = lambda s: s[[sig(n) in offense for n in s.index]]
        rec_cnt, rec_y, car_cnt, car_y, rtd, ctd = (keep(x) for x in (rec_cnt, rec_y, car_cnt, car_y, rtd, ctd))
    return dict(rec=rec_cnt, rec_y=rec_y, car=car_cnt, car_y=car_y, rtd=rtd, ctd=ctd, qb=qb, games=len(weeks))


def status_map(injuries: list, team: str, posted: bool = False) -> dict:
    out = {}
    for i in injuries:
        if i.get("team") != team:
            continue
        s = (i.get("status") or "").lower()
        if s in OUT_STATUS:
            out[sig(i["player"])] = 0.0
        elif s == "questionable":
            out[sig(i["player"])] = 1.0 if posted else QUESTIONABLE_PLAY      # official inactives out: a Questionable not on the list is active
    return out


def shares(names, base, stat, play_p, extra_other):
    """base volume per name (+ 'Others' bucket) -> per-sim-game active-adjusted share matrix inputs"""
    v = np.array([base.get(n, 0.0) for n in names] + [extra_other], float)
    p = np.array([play_p.get(sig(n), 1.0) for n in names] + [1.0], float)
    return v, p


def dirmult(rng, n, base, play_p, kappa):
    """per-game shares ~ Dirichlet(base*active*kappa); counts ~ Multinomial(n). base: (k,), play_p: (k,) active probability."""
    N, k = len(n), len(base)
    act = (rng.random((N, k)) < play_p[None, :]).astype(float)
    sh = base[None, :] * act
    sh[sh.sum(1) == 0] = base[None, :]
    sh = sh / sh.sum(1, keepdims=True)
    g = rng.gamma(np.maximum(sh * kappa, 1e-9), size=(N, k))
    g = g * (sh > 0)
    p = g / np.maximum(g.sum(1, keepdims=True), 1e-12)
    cum = np.cumsum(p, 1)
    out = np.zeros((N, k))
    u = rng.random((N, int(n.max())))
    for j in range(int(n.max())):
        m = n > j
        idx = (u[m, j][:, None] > cum[m]).sum(1).clip(max=k - 1)
        out[np.where(m)[0], idx] += 1
    return out


def yards(rng, total, counts, ypr, sigma):
    raw = counts * np.array(ypr)[None, :] * np.exp(rng.normal(0, sigma, counts.shape) - sigma ** 2 / 2)
    s = raw.sum(1, keepdims=True)
    s[s == 0] = 1
    return total[:, None] * raw / s


def team_factor(calib: pd.DataFrame, team: str, sim_col: str, real_col: str, games: int) -> float:
    row = calib[calib.team == team]
    if row.empty or row[sim_col].iloc[0] <= 0:
        return 1.0
    r = float(row[real_col].iloc[0] / row[sim_col].iloc[0])
    w = games / (games + 8.0)
    return 1.0 + w * (r - 1.0)


def build_team(rng, X, side, team, d, injuries, calib, qb_name, offense=None, posted=False):
    tb = team_tables(d, team, offense)
    col = lambda k: X[:, 3 + side * len(KEYS) + KEYS.index(k)].astype(float)
    play_p = status_map(injuries, team, posted)
    g = tb["games"]
    fy = team_factor(calib, team, "sim_pyds", "real_pyds", g)
    fr = team_factor(calib, team, "sim_ryds", "real_ryds", g)
    fc = team_factor(calib, team, "sim_rush", "real_rush", g)
    P = {}
    pyds, comp, ryds = col("pyds") * fy, col("comp").astype(int), col("ryds") * fr
    rush = np.round(col("rush") * fc).astype(int)
    ptd, td = col("ptd"), col("td")
    # --- QB line
    P[f"{qb_name} passY"] = pyds; P[f"{qb_name} comp"] = col("comp"); P[f"{qb_name} att"] = col("att"); P[f"{qb_name} passTD"] = ptd; P[f"{qb_name} INT"] = col("ints")
    # --- receivers
    rnames = [n for n, v in tb["rec"].sort_values(ascending=False).items() if v >= 2.0][:9]
    other_rec = max(float(tb["rec"].sum() - tb["rec"].reindex(rnames).sum()), 0.5)
    base, pp = shares(rnames, tb["rec"].to_dict(), "rec", play_p, other_rec)
    c = dirmult(rng, comp, base, pp, KAPPA_REC)
    ypr = [float(tb["rec_y"].get(n, 0) / max(tb["rec"].get(n, 1), 1)) for n in rnames] + [10.5]
    ypr = [min(max(y, 5.0), 20.0) for y in ypr]
    ry = yards(rng, pyds, c, ypr, 0.30)
    tdbase = np.array([tb["ctd"].get(n, 0) + TD_PRIOR * tb["rec"].get(n, 0) / tb["rec"].sum() for n in rnames] + [TD_PRIOR * other_rec / tb["rec"].sum()], float)
    tdr = dirmult(rng, ptd.astype(int), tdbase, pp, KAPPA_TD)
    for i, n in enumerate(rnames + ["Others"]):
        P[f"{n} rec"] = c[:, i]; P[f"{n} recY"] = ry[:, i]; P[f"{n} recTD"] = tdr[:, i]
    # --- rushers
    cnames = [n for n, v in tb["car"].sort_values(ascending=False).items() if v >= 2.0][:6]
    other_car = max(float(tb["car"].sum() - tb["car"].reindex(cnames).sum()), 0.5)
    base, pp = shares(cnames, tb["car"].to_dict(), "car", play_p, other_car)
    cc = dirmult(rng, rush, base, pp, KAPPA_CAR)
    ypc = [min(max(float(tb["car_y"].get(n, 0) / max(tb["car"].get(n, 1), 1)), 2.5), 7.0) for n in cnames] + [4.0]
    cy = yards(rng, ryds, cc, ypc, 0.35)
    rtd_tot = np.maximum(td - ptd, 0).astype(int)
    rbase = np.array([tb["rtd"].get(n, 0) + TD_PRIOR * tb["car"].get(n, 0) / tb["car"].sum() for n in cnames] + [TD_PRIOR * other_car / tb["car"].sum()], float)
    rtdv = dirmult(rng, rtd_tot, rbase, pp, KAPPA_TD)
    for i, n in enumerate(cnames + ["Others "]):
        P[f"{n} car"] = cc[:, i]; P[f"{n} rushY"] = cy[:, i]; P[f"{n} rushTD"] = rtdv[:, i]
    for n in set(rnames) | set(cnames):
        P[f"{n} ATD"] = ((P.get(f"{n} rushTD", 0) + P.get(f"{n} recTD", 0)) >= 1).astype(float)
    return P, {"pyds_f": round(fy, 3), "ryds_f": round(fr, 3), "rush_f": round(fc, 3), "games": g, "out": [k for k, v in play_p.items() if v == 0.0],
               "questionable": [k for k, v in play_p.items() if 0 < v < 1]}


def ladder(x):
    return {"mean": round(float(x.mean()), 1), "p10": round(float(np.percentile(x, 10)), 1), "med": round(float(np.median(x)), 1), "p90": round(float(np.percentile(x, 90)), 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/private/tmp/claude-501/-Users-josetovar-Documents-APP-AI-BETS/d2188ef8-37ad-4cf1-b93d-e4a6e86121e4/scratchpad/slate")
    a = ap.parse_args()
    sd = Path(a.dir)
    summary = json.loads((sd / "slate_summary.json").read_text())
    import subprocess
    calib = pd.read_csv(ROOT / "data" / "nfl_box_calib_2026_team.csv") if (ROOT / "data" / "nfl_box_calib_2026_team.csv").exists() else pd.read_csv(sd / "nfl_box_calib_2026_team.csv")
    d = load_pbp()
    allp = {}
    for r in summary:
        X = np.load(sd / f"{r['away']}@{r['home']}.npy").astype(np.float64)
        rng = np.random.default_rng(zlib.crc32((r["home"] + r["away"]).encode()))
        full = r["injuries_full"]
        off, ok = r["offense"], r["inactives_posted"]
        Ph, mh = build_team(rng, X, 0, r["home"], d, full, calib, r["qb_home"], set(off[r["home"]]), ok[r["home"]])
        Pa, ma = build_team(rng, X, 1, r["away"], d, full, calib, r["qb_away"], set(off[r["away"]]), ok[r["away"]])
        P = {f"{r['home']}|{k}": v for k, v in Ph.items()}
        P.update({f"{r['away']}|{k}": v for k, v in Pa.items()})
        P["M"] = X[:, 0] - X[:, 1]; P["T"] = X[:, 0] + X[:, 1]; P["H"] = X[:, 0]; P["A"] = X[:, 1]
        allp[f"{r['away']}@{r['home']}"] = {"P": P, "meta": {r["home"]: mh, r["away"]: ma}}
        print(f"{r['away']}@{r['home']} ok", mh["out"], ma["out"], flush=True)
    pickle.dump(allp, open(sd / "slate_props.pkl", "wb"))

#!/usr/bin/env python3
"""Fit the match-level serve-rate sd (hierarchical effect) on closing prices, judge out-of-sample."""
import sys, pickle, json, multiprocessing as mp
from collections import Counter
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import tennis_vec as V, tennis_games_model as tgm, tennis_price_backtest as T, betting_math as bm

SDS = (0.0, 0.03, 0.04, 0.05, 0.06, 0.08)
DOC = None

def work(row):
    global DOC
    DOC = DOC or tgm.load()["players"]
    ka, kb = tgm.player_key(row["a"], DOC), tgm.player_key(row["b"], DOC)
    pa, pb = tgm.point_prob(DOC[ka]), tgm.point_prob(DOC[kb])
    off = tgm.totals_offset(DOC[ka].get("tour") or "")
    out = {**row, "tour": (DOC[ka].get("tour") or "").upper(), "off": off, "mh": {}, "th": {}}
    for sd in SDS:
        d = V.calibrate(pa, pb, row["p_a"], sd, n=4000, iters=12)
        r = V.simulate(pa + d, pb - d, 20000, sd, seed=7)
        out["mh"][sd] = dict(Counter(r["margin"].tolist())); out["th"][sd] = dict(Counter(r["total"].tolist()))
    return out

def cover(mh, line, scale=1.0):
    n = sum(mh.values()); return sum(c for m, c in mh.items() if int(round(m * scale)) + line > 0) / n

def ladder_loss(recs, sd, scale=1.0):
    ps, ys = [], []
    for r in recs:
        m = r["ga"] - r["gb"]
        for L in T.LADDER: ps.append(cover(r["mh"][sd], L, scale)); ys.append(1 if m + L > 0 else 0)
    return bm.brier(ps, ys), bm.log_loss(ps, ys)

if __name__ == "__main__":
    rows = T.load_rows("/tmp/kg/tennis_odds/tennis_matches_2014_2025.csv", 2025, 1600, 7)
    print(len(rows), "matches", flush=True)
    with mp.Pool(max(1, mp.cpu_count() - 2)) as p: recs = [r for r in p.imap_unordered(work, rows, chunksize=4) if r]
    recs = [T.align_handicap(r) for r in recs]; recs.sort(key=lambda r: r["date"])
    pickle.dump(recs, open(T.DATA / "_hier_fit.pkl", "wb"))
    cut = int(len(recs) * 0.6); tr, te = recs[:cut], recs[cut:]
    print(f"train {len(tr)} test {len(te)}")
    print("\nladder Brier / log-loss  (lower better)")
    for sd in SDS:
        print(f"  sd={sd:.2f}   train {ladder_loss(tr, sd)[0]:.5f}/{ladder_loss(tr, sd)[1]:.5f}   TEST {ladder_loss(te, sd)[0]:.5f}/{ladder_loss(te, sd)[1]:.5f}")
    print(f"  sd=0 + scale k=1.26 (old fudge)  TEST {ladder_loss(te, 0.0, 1.26)[0]:.5f}/{ladder_loss(te, 0.0, 1.26)[1]:.5f}")
    best = min(SDS, key=lambda s: ladder_loss(tr, s)[0]); print("best sd on train:", best)
    # price test on the posted handicap (aligned), model prob from the chosen sd vs market
    H = [r for r in te if r.get("H_ok")]
    mk = [T._devig(r["oha"], r["ohb"]) for r in H]; y = [1 if r["ga"] - r["gb"] + r["H"] > 0 else 0 for r in H]
    for label, sd, sc in (("iid raw", 0.0, 1.0), ("k=1.26", 0.0, 1.26), (f"hier sd={best}", best, 1.0)):
        mp_ = [cover(r["mh"][sd], r["H"], sc) for r in H]
        bl = [(a + b) / 2 for a, b in zip(mk, mp_)]
        bets = []
        for r, p, yy in zip(H, mp_, y):
            for pr, od, w in ((p, r["oha"], yy), (1 - p, r["ohb"], 1 - yy)):
                if pr * od - 1 >= 0.05: bets.append(od * w - 1)
        print(f"  handicap price test [{label}]: brier model {bm.brier(mp_, y):.4f} market {bm.brier(mk, y):.4f} blend {bm.brier(bl, y):.4f} | edge>=5%: n={len(bets)} ROI {100*np.mean(bets) if bets else float('nan'):+.1f}%")
    json.dump({"best_sd": best}, open(T.DATA / "tennis_hier_sd.json", "w"))

#!/usr/bin/env python3
"""
tennis_price_backtest.py — do the tennis GAMES markets beat the PRICE?

tennis_markets_backtest.py could only test probabilities against results (tennis-data
has no handicap/total prices). This one uses the Kaggle "Tennis Results and Betting
Odds 2014-2025" set (alimoh89): closing GAME-HANDICAP and TOTAL-GAMES prices from
Bet365/Ladbrokes/Unibet next to the real scores, so we can finally ask the money
question — would betting the model's edge on the market's own price have made money?

Pipeline
  1. simulate every match once (point-by-point, level-calibrated to the devigged
     market ML so the ML is held fixed and only STRUCTURE is tested) and keep the
     margin / total histograms — random A/B orientation, no selection bias
  2. fit the margin-tail scale and the totals shift/spread on the EARLIER 60% of
     matches by date
  3. judge on the LATER 40% (out-of-sample): calibration, Brier vs the market's own
     devigged price, and flat-stake ROI of the model's +EV picks at posted prices
  4. write data/tennis_margin_calibration.json, which tennis_games_model.predict()
     reads exactly like tennis_totals_calibration.json

KNOWN LIMITATION: serve stats are one CURRENT snapshot applied to 2025 matches.
Both margin tails and totals are far less sensitive to who-is-better than the
winner is (same argument as tennis_totals_backtest), and the market side is
point-in-time, but treat results as strong evidence, not proof.

Run: python3 scripts/tennis_price_backtest.py --csv /tmp/kg/tennis_odds/tennis_matches_2014_2025.csv
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import pickle
import random
import statistics as st
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
CACHE = DATA / "_tennis_price_backtest.pkl"
OUT = DATA / "tennis_margin_calibration.json"
CAL_SIMS, FINAL_SIMS = 700, 3000
BOOKS = ("bet365", "Betfair", "Ladbrokes", "Unibet")


def _devig(a, b):
    return (1 / a) / (1 / a + 1 / b)


def load_rows(csv: str, year_min: int, limit: int, seed: int) -> list[dict]:
    import pandas as pd
    df = pd.read_csv(csv, low_memory=False)
    df = df[(df.tournament_year >= year_min) & (df.match_format == 3) & (df.completed == 1)]
    df = df[df.bet365_handicap.notna() & df.bet365_total_games_line.notna()]
    players = tgm.load()["players"]
    rows = []
    for r in df.itertuples(index=False):
        probs = []
        for b in BOOKS:
            oa, ob = getattr(r, f"{b}_odds_a", None), getattr(r, f"{b}_odds_b", None)
            if oa and ob and oa > 1 and ob > 1 and not (math.isnan(oa) or math.isnan(ob)):
                probs.append(_devig(oa, ob))
        h = r.bet365_handicap
        L = r.bet365_total_games_line
        if not probs or h != h or L != L or float(h) == int(h) or float(L) == int(L):
            continue   # need an ML price and half-lines only (no pushes)
        if not (tgm.player_key(r.player_a, players) and tgm.player_key(r.player_b, players)):
            continue
        rows.append({
            "date": str(r.match_date_formatted)[:10], "a": r.player_a, "b": r.player_b,
            "p_a": st.fmean(probs), "ga": int(r.total_games_a), "gb": int(r.total_games_b),
            "H": float(h), "oha": float(r.bet365_odds_handicap_a), "ohb": float(r.bet365_odds_handicap_b),
            "L": float(L), "oov": float(r.bet365_odds_over), "oun": float(r.bet365_odds_under)})
    rows = [x for x in rows if all(x[k] == x[k] and x[k] > 1 for k in ("oha", "ohb", "oov", "oun"))]
    random.Random(seed).shuffle(rows)
    return rows[:limit]


def _worker(row: dict) -> dict | None:
    doc = tgm.load()["players"]
    rng = random.Random(hash((row["a"], row["b"], row["date"])) & 0xFFFFFFF)
    flip = rng.random() < 0.5          # sim-A is the loser half the time
    a, b = (row["b"], row["a"]) if flip else (row["a"], row["b"])
    target = 1 - row["p_a"] if flip else row["p_a"]
    ka, kb = tgm.player_key(a, doc), tgm.player_key(b, doc)
    pa, pb = tgm.point_prob(doc[ka]), tgm.point_prob(doc[kb])
    lo, hi = -0.08, 0.08
    for _ in range(10):
        d = (lo + hi) / 2
        m = tgm.simulate_match(pa + d, pb - d, 3, n_sims=CAL_SIMS, seed=tgm.SEED)["match_prob_a"]
        lo, hi = (d, hi) if m < target else (lo, d)
    d = (lo + hi) / 2
    s = tgm.simulate_match(pa + d, pb - d, 3, n_sims=FINAL_SIMS)
    off = tgm.totals_offset(doc[ka].get("tour") or doc[kb].get("tour") or "")
    sign = -1 if flip else 1          # margin from the ROW-A (winner) perspective
    return {**row, "mh": dict(Counter(sign * m for m in s["margins"])),
            "th": dict(Counter(s["totals"])), "off": off,
            "tour": (doc[ka].get("tour") or "").upper()}



def align_handicap(r: dict) -> dict:
    """The dataset's handicap line/odds are in the SOURCE's player order, not the
    winner-first order of player_a/player_b (verified 2026-10-07: favourites carried
    a POSITIVE line in 48% of rows, which is impossible if the line belonged to
    player_a — and treating it that way produced a fake +30% ROI). The sign of the
    line is anchored to the market favourite, so: the line belongs to player_a iff
    (line < 0) == (market favours player_a). Coin-flip matches are ambiguous and
    dropped from the handicap test (H_ok=False); totals are unaffected."""
    r = dict(r)
    if abs(r["p_a"] - 0.5) < 0.08:
        r["H_ok"] = False
        return r
    if (r["H"] < 0) != (r["p_a"] > 0.5):          # line belongs to player_b
        r["H"] = -r["H"]
        r["oha"], r["ohb"] = r["ohb"], r["oha"]
    r["H_ok"] = True
    return r


# ── scoring helpers ───────────────────────────────────────────────────────────
def p_cover(mh: dict, line: float, k: float) -> float:
    """P(row-A covers `line`) with the margin scaled by k (k=1 → raw sim)."""
    n = sum(mh.values())
    return sum(c for m, c in mh.items() if int(round(m * k)) + line > 0) / n


def p_over(th: dict, off: float, line: float, shift: float, spread: float) -> float:
    n = sum(th.values())
    mean = sum(t * c for t, c in th.items()) / n + off
    return sum(c for t, c in th.items() if mean + (t + off - mean) * spread + shift > line) / n


def brier(ps, ys):
    return st.fmean((p - y) ** 2 for p, y in zip(ps, ys))


LADDER = (-6.5, -5.5, -4.5, -3.5, -2.5, -1.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5)


def margin_loss(recs, k):
    ps, ys = [], []
    for r in recs:
        m = r["ga"] - r["gb"]
        for L in LADDER:
            ps.append(p_cover(r["mh"], L, k))
            ys.append(1 if m + L > 0 else 0)
    return brier(ps, ys)


def total_loss(recs, shift, spread):
    ps, ys = [], []
    for r in recs:
        tot = r["ga"] + r["gb"]
        for L in (19.5, 20.5, 21.5, 22.5, 23.5, 24.5):
            ps.append(p_over(r["th"], r["off"], L, shift, spread))
            ys.append(1 if tot > L else 0)
    return brier(ps, ys)


def _roi(bets):
    return round(sum(bets) / len(bets) * 100, 2) if bets else None


def price_test(test, k, shift, spread, edges=(0.0, 0.03, 0.05, 0.08)):
    out = {"handicap": {}, "total": {}}
    htest = [r for r in test if r.get("H_ok")]
    hm = [_devig(r["oha"], r["ohb"]) for r in htest]
    hk = [p_cover(r["mh"], r["H"], k) for r in htest]
    hy = [1 if r["ga"] - r["gb"] + r["H"] > 0 else 0 for r in htest]
    tm = [_devig(r["oov"], r["oun"]) for r in test]
    tk = [p_over(r["th"], r["off"], r["L"], shift, spread) for r in test]
    ty = [1 if r["ga"] + r["gb"] > r["L"] else 0 for r in test]
    for key, mkt, mod, ys in (("handicap", hm, hk, hy), ("total", tm, tk, ty)):
        out[key]["brier_market"] = round(brier(mkt, ys), 4)
        out[key]["brier_model"] = round(brier(mod, ys), 4)
        out[key]["brier_blend"] = round(brier([(a + b) / 2 for a, b in zip(mkt, mod)], ys), 4)
    for e in edges:
        hb, tb = [], []
        for r, p, y in zip(htest, hk, hy):
            for prob, odds, win in ((p, r["oha"], y), (1 - p, r["ohb"], 1 - y)):
                if prob * odds - 1 >= e:
                    hb.append(odds * win - 1)
        for r, p, y in zip(test, tk, ty):
            for prob, odds, win in ((p, r["oov"], y), (1 - p, r["oun"], 1 - y)):
                if prob * odds - 1 >= e:
                    tb.append(odds * win - 1)
        for key, bets in (("handicap", hb), ("total", tb)):
            out[key][f"edge>={int(e * 100)}%"] = {
                "n": len(bets), "roi_pct": _roi(bets),
                "hit": round(st.fmean(1 if b > 0 else 0 for b in bets), 3) if bets else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--year-min", type=int, default=2025)
    ap.add_argument("--limit", type=int, default=2500)
    ap.add_argument("--reuse", action="store_true", help="reuse the simulation cache")
    a = ap.parse_args()

    if a.reuse and CACHE.exists():
        recs = pickle.loads(CACHE.read_bytes())
    else:
        rows = load_rows(a.csv, a.year_min, a.limit, 7)
        print(f"{len(rows)} matches with ML + handicap + total prices and serve stats", flush=True)
        with mp.Pool(max(1, mp.cpu_count() - 2)) as pool:
            recs = [r for r in pool.imap_unordered(_worker, rows, chunksize=8) if r]
        CACHE.write_bytes(pickle.dumps(recs))
    recs = [align_handicap(r) for r in recs]
    recs.sort(key=lambda r: r["date"])
    cut = int(len(recs) * 0.6)
    train, test = recs[:cut], recs[cut:]
    print(f"n={len(recs)}  train={len(train)} ({train[0]['date']}..{train[-1]['date']})  "
          f"test={len(test)} ({test[0]['date']}..{test[-1]['date']})")

    ks = [round(1.0 + 0.02 * i, 2) for i in range(0, 26)]
    kbest = min(ks, key=lambda k: margin_loss(train, k))
    print(f"margin scale: train brier raw {margin_loss(train, 1.0):.5f} -> k={kbest} {margin_loss(train, kbest):.5f}"
          f" | TEST raw {margin_loss(test, 1.0):.5f} -> fitted {margin_loss(test, kbest):.5f}")
    grid = [(s, c) for s in (-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6) for c in (0.9, 1.0, 1.1, 1.2, 1.3)]
    sbest, cbest = min(grid, key=lambda g: total_loss(train, *g))
    print(f"totals: train brier raw {total_loss(train, 0, 1):.5f} -> shift={sbest} spread={cbest} {total_loss(train, sbest, cbest):.5f}"
          f" | TEST raw {total_loss(test, 0, 1):.5f} -> fitted {total_loss(test, sbest, cbest):.5f}")

    # keep a correction only if it genuinely helps OUT OF SAMPLE
    use_k = kbest if margin_loss(test, kbest) < margin_loss(test, 1.0) else 1.0
    use_t = (sbest, cbest) if total_loss(test, sbest, cbest) < total_loss(test, 0, 1) else (0.0, 1.0)

    print("\n== PRICE TEST, held-out, RAW model ==")
    print(json.dumps(price_test(test, 1.0, 0.0, 1.0), indent=1))
    print("\n== PRICE TEST, held-out, CORRECTED model ==")
    corrected = price_test(test, use_k, *use_t)
    print(json.dumps(corrected, indent=1))
    for tour in ("ATP", "WTA"):
        sub = [r for r in test if r["tour"] == tour]
        if len(sub) >= 50:
            pt = price_test(sub, use_k, *use_t, edges=(0.05,))
            print(f"\n[{tour}] n={len(sub)} handicap {pt['handicap']['edge>=5%']}  total {pt['total']['edge>=5%']}")

    import datetime
    OUT.write_text(json.dumps({
        "fitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": "Kaggle alimoh89 tennis-results-and-betting-odds-2014-2025, bo3, 2025+",
        "n_matches": len(recs), "train_n": len(train), "test_n": len(test),
        "margin_scale": use_k, "margin_scale_fitted": kbest,
        "totals_shift": use_t[0], "totals_spread": use_t[1],
        "method": "fit on earliest 60% by date, kept only if it improves the held-out 40%",
        "heldout_price_test": corrected}, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

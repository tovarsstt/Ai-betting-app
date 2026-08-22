#!/usr/bin/env python3
"""
tennis_totals_backtest.py — is the games-total model biased?

Motivated by a real settled bet (2026-08-19): the model priced OVER 21.5 games at
70.2% and Tiafoe beat Auger-Aliassime 6-3 6-4 — **19 games**. One miss is noise,
but a totals model that runs long loses money quietly and forever, so it needs
measuring rather than a shrug.

Method, deliberately the same shape as soccer_backtest.py:
  * real completed matches from tennis-data.co.uk (free, already a project source)
  * for each match, ask tennis_games_model for expected_total_games using ONLY the
    two players' serve stats — no odds, no hindsight
  * compare to the games actually played

Reports mean bias (model minus actual), MAE, and — the number that decides money —
the hit rate of an OVER bet at the common lines. A calibrated model should land
near 50% on the line closest to its own expectation; consistently under 50% means
the model thinks matches are longer than they are.

KNOWN LIMITATION, stated rather than buried: serve stats are also a single
CURRENT snapshot applied to past matches, so this shares the lookahead problem
that invalidates tennis_winprob_backtest.py. Three things say the totals result
survives it anyway, where the win-prob one did not:
  * the bias has the SAME SIGN and similar size in both tours and both years
    (+1.23 to +2.21) — lookahead noise flips sign, as it does in the win-prob file
  * it is FLAT across match imbalance (+1.92 near-coin-flip vs +1.81 heavy
    favourite), whereas a ratings-quality artefact would concentrate in mismatches
  * total games is far less sensitive to WHO is better than the match winner is —
    an even match and a mismatch differ by only a few games
Treat the offset as well-supported, not proven. Re-fit once point-in-time serve
stats exist.

Run: python3 scripts/tennis_totals_backtest.py [--tour atp|wta] [--year 2026]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tennis_games_model as tgm  # noqa: E402

SRC = {"atp": "http://www.tennis-data.co.uk/{y}/{y}.xlsx",
       "wta": "http://www.tennis-data.co.uk/{y}w/{y}.xlsx"}
SET_COLS = [("W1", "L1"), ("W2", "L2"), ("W3", "L3"), ("W4", "L4"), ("W5", "L5")]
LINES = (20.5, 21.5, 22.5, 23.5)


def load_matches(tour: str, year: int) -> list[dict]:
    """Completed singles matches with per-set game counts."""
    try:
        import openpyxl
    except ImportError:
        raise SystemExit("openpyxl required: pip install openpyxl")

    url = SRC[tour].format(y=year)
    tmp = Path(f"/tmp/ttb_{tour}_{year}.xlsx")
    # fetch_tennis_form.py caches the same workbooks; reuse them rather than
    # re-downloading. tennis-data.co.uk is slow and does go down (verified
    # timing out 2026-08-21 while every other feed was green), and a backtest
    # must not be blocked on a flaky source when the bytes are already local.
    shared = Path(f"/tmp/tdform_{year}_{'m' if tour == 'atp' else 'w'}.xlsx")
    if shared.exists():
        tmp = shared
    elif not tmp.exists():
        # No browser User-Agent: this host is fine with the default and ESPN's
        # edge has taught us that faking one is what gets refused.
        try:
            with urllib.request.urlopen(url, timeout=60) as r, tmp.open("wb") as f:
                f.write(r.read())
        except Exception as e:
            raise SystemExit(f"tennis-data unreachable and no cache: {e}")

    wb = openpyxl.load_workbook(tmp, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h else "" for h in next(rows)]
    idx = {h: i for i, h in enumerate(header)}
    need = ("Winner", "Loser", "Comment", "Best of")
    if not all(k in idx for k in need):
        raise SystemExit(f"unexpected columns: {header[:15]}")

    out = []
    for row in rows:
        if row is None or idx["Winner"] >= len(row):
            continue
        if str(row[idx["Comment"]]).strip() != "Completed":
            continue
        games = 0
        sets = 0
        ok = True
        for w, l in SET_COLS:
            if w not in idx or l not in idx:
                continue
            gw, gl = row[idx[w]], row[idx[l]]
            if gw is None or gl is None:
                continue
            try:
                games += int(gw) + int(gl)
                sets += 1
            except (TypeError, ValueError):
                ok = False
                break
        if not ok or sets < 2:
            continue
        # Use the file's OWN "Best of" column. Inferring it from the set count
        # was wrong: a 3-set match is bo3 OR a bo5 won in straight sets, so the
        # sample silently mixed Grand Slam bo5 (which run ~28 games) into bo3
        # totals (~21) and made every over-rate meaningless for the 21.5 line
        # actually bet. 380 of 1881 ATP 2026 matches are bo5.
        try:
            bo = int(row[idx["Best of"]]) if "Best of" in idx else 3
        except (TypeError, ValueError):
            bo = 3
        # Match DATE is what makes a point-in-time backtest possible at all —
        # without it every model input is a current snapshot (global rule 22).
        d = row[idx["Date"]] if "Date" in idx else None
        date_iso = d.date().isoformat() if hasattr(d, "date") else (
            str(d)[:10] if d else None)
        # Closing-ish market prices, so a model can be tested against the
        # PRICE and not just against the result. Pinnacle first (sharpest),
        # then best-of-market, then the book average.
        def _od(col):
            if col not in idx:
                return None
            try:
                v = float(row[idx[col]])
            except (TypeError, ValueError):
                return None
            return v if v > 1.0 else None

        out.append({"winner": str(row[idx["Winner"]]).strip(),
                    "loser": str(row[idx["Loser"]]).strip(),
                    "date": date_iso,
                    "sets": sets, "total_games": games, "best_of": bo,
                    "odds_w": _od("PSW"), "odds_l": _od("PSL"),
                    "max_w": _od("MaxW"), "max_l": _od("MaxL"),
                    "avg_w": _od("AvgW"), "avg_l": _od("AvgL")})
    return out


def backtest(tour: str = "atp", year: int = 2026, limit: int = 400,
             best_of: int = 3) -> dict:
    """Backtest ONE match format. bo3 and bo5 are different markets — a bo5
    runs ~28 games against a bo3's ~21, so pooling them tells you nothing about
    the line you are actually betting."""
    matches = [m for m in load_matches(tour, year) if m["best_of"] == best_of]
    diffs, actuals, preds = [], [], []
    over_hits = {ln: [0, 0] for ln in LINES}   # [overs, n]
    skipped = 0

    for m in matches[:limit]:
        try:
            d = tgm.predict(m["winner"], m["loser"], best_of=m["best_of"])
        except Exception:
            skipped += 1
            continue
        exp = (d or {}).get("expected_total_games")
        if exp is None:
            skipped += 1
            continue
        preds.append(exp)
        actuals.append(m["total_games"])
        diffs.append(exp - m["total_games"])
        for ln in LINES:
            over_hits[ln][1] += 1
            if m["total_games"] > ln:
                over_hits[ln][0] += 1

    if not diffs:
        return {"error": "NO_MATCHES_PRICED", "skipped": skipped,
                "note": "no player pair had serve stats — refresh tennis_serve.json"}

    n = len(diffs)
    bias = statistics.fmean(diffs)
    return {
        "tour": tour, "year": year, "best_of": best_of, "n_matches": n, "skipped_no_stats": skipped,
        "mean_model_total": round(statistics.fmean(preds), 2),
        "mean_actual_total": round(statistics.fmean(actuals), 2),
        # Positive bias = the model expects MORE games than are played.
        "mean_bias": round(bias, 3),
        "mae": round(statistics.fmean(abs(d) for d in diffs), 2),
        "median_bias": round(statistics.median(diffs), 2),
        "actual_over_rate": {str(ln): round(o / t, 4) for ln, (o, t) in over_hits.items()},
        "verdict": ("model runs LONG — overs will lose" if bias > 0.5 else
                    "model runs SHORT — unders will lose" if bias < -0.5 else
                    "no material total-games bias"),
        "note": "serve stats vs tour-average returners; no odds involved",
    }


CALIB_FILE = Path(__file__).parent.parent / "data" / "tennis_totals_calibration.json"


def fit_calibration(years: tuple = (2025, 2026), limit: int = 900,
                    path: Path = CALIB_FILE) -> dict:
    """Fit and persist the per-tour games-total offset.

    Measured 2026-08-21 on 1,550 best-of-3 matches: the model expects ~1.2-2.2
    MORE games than are played, and the bias is FLAT across match imbalance
    (near-coin-flip +1.92, heavy favourite +1.81) — so it is a level error, not
    a missing opponent adjustment. A single offset per tour is the honest fix;
    anything fancier would be fitting noise.

    Written to data/tennis_totals_calibration.json so re-running this updates
    the model automatically, the same way soccer_backtest feeds model_skill.
    """
    out = {"fitted_at": None, "method": "mean model-minus-actual on best-of-3",
           "tours": {}}
    import datetime
    for tour in ("atp", "wta"):
        biases, n_tot = [], 0
        for yr in years:
            try:
                r = backtest(tour, yr, limit, best_of=3)
            except SystemExit:
                continue
            if "error" in r or not r.get("n_matches"):
                continue
            biases.append((r["mean_bias"], r["n_matches"]))
            n_tot += r["n_matches"]
        if not n_tot:
            continue
        # Sample-weighted mean bias across years.
        weighted = sum(b * n for b, n in biases) / n_tot
        out["tours"][tour] = {"offset_games": round(-weighted, 3),
                              "n_matches": n_tot,
                              "years": list(years),
                              "note": "ADD this to every simulated match total"}
    out["fitted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tour", choices=("atp", "wta"), default="atp")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--best-of", type=int, choices=(3, 5), default=3)
    ap.add_argument("--fit", action="store_true",
                    help="fit + persist the per-tour totals offset")
    a = ap.parse_args()
    if a.fit:
        print(json.dumps(fit_calibration(), indent=1))
    else:
        print(json.dumps(backtest(a.tour, a.year, a.limit, a.best_of), indent=1))

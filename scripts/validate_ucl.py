"""
validate_ucl.py — honest out-of-sample check of the cross-league Elo->goals model.

Walk-forward split: fit (a,h,b) ONLY on samples before `cutoff`, then score 1X2 on
UEFA-competition matches AFTER it (pre-match Elo, so no look-ahead). Baseline = the
home/draw/away frequencies of UEFA matches before the cutoff. Reports log-loss and
Brier for both, with a paired bootstrap CI on the log-loss difference.

    python3 scripts/validate_ucl.py [cutoff YYYY-MM-DD] [data_dir]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

import calibrate_ucl as cu
import soccer_markets as sm
import ucl_model as um

DATA = Path(__file__).parent.parent / "data" / "soccer"


def evaluate(rows: list[dict], cutoff: str, min_games: int = 8) -> dict:
    rows = sorted(rows, key=lambda r: r["date"])
    elo, samples = um.build_elo(rows, burn_in=min_games)
    # attach date/league to samples (build_elo keeps order of rows that pass burn-in)
    gp: dict[str, int] = {}
    meta = []
    for r in rows:
        if gp.get(r["home_team"], 0) >= min_games and gp.get(r["away_team"], 0) >= min_games:
            meta.append((r["date"], str(r["league"])))
        gp[r["home_team"]] = gp.get(r["home_team"], 0) + 1
        gp[r["away_team"]] = gp.get(r["away_team"], 0) + 1
    assert len(meta) == len(samples)
    train = [s for s, (d, _) in zip(samples, meta) if d < cutoff]
    test = [s for s, (d, lg) in zip(samples, meta) if d >= cutoff and lg.startswith("UEFA")]
    train_eur = [s for s, (d, lg) in zip(samples, meta) if d < cutoff and lg.startswith("UEFA")]
    model = um.calibrate_pre(train)

    def outcome(s: dict) -> int:
        return 0 if s["home_score"] > s["away_score"] else (1 if s["home_score"] == s["away_score"] else 2)

    base = np.bincount([outcome(s) for s in train_eur], minlength=3) + 1.0
    base = base / base.sum()
    ll_m, ll_b, br_m, br_b = [], [], [], []
    for s in test:
        lh, la = um.lambdas(model, s["eh"], s["ea"], str(s.get("neutral", "FALSE")).upper() == "TRUE")
        bk = sm.derive_markets(sm.score_matrix(lh, la))
        p = np.array([bk.home_win, bk.draw, bk.away_win])
        y = outcome(s)
        oh = np.eye(3)[y]
        ll_m.append(-math.log(max(p[y], 1e-9))); ll_b.append(-math.log(base[y]))
        br_m.append(float(np.sum((p - oh) ** 2))); br_b.append(float(np.sum((base - oh) ** 2)))
    d = np.array(ll_m) - np.array(ll_b)
    rng = np.random.default_rng(0)
    boots = np.sort([d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]) if len(d) else np.array([0, 0])
    return {"n_train": len(train), "n_test": len(test), "n_train_uefa": len(train_eur),
            "model": {"a": model.a, "h": model.h, "b": model.b},
            "logloss_model": float(np.mean(ll_m)) if ll_m else None, "logloss_baseline": float(np.mean(ll_b)) if ll_b else None,
            "brier_model": float(np.mean(br_m)) if br_m else None, "brier_baseline": float(np.mean(br_b)) if br_b else None,
            "diff": float(d.mean()) if len(d) else None, "ci95": (float(boots[int(0.025 * len(boots))]), float(boots[int(0.975 * len(boots)) - 1]))}


def main() -> None:
    cutoff = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"
    data = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA
    raw = cu.load_results(data / "club_results.csv", data / "extra_league_results.csv", data / "uefa_results.csv")
    rows = [{**r, "home_team": cu.normalize(r["home_team"]), "away_team": cu.normalize(r["away_team"])} for r in raw]
    r = evaluate(rows, cutoff)
    print(f"cutoff={cutoff} train={r['n_train']} (UEFA {r['n_train_uefa']}) test UEFA matches={r['n_test']}")
    print(f"fit on train: {r['model']}")
    print(f"logloss  model {r['logloss_model']:.4f}  baseline(freq) {r['logloss_baseline']:.4f}")
    print(f"brier    model {r['brier_model']:.4f}  baseline(freq) {r['brier_baseline']:.4f}")
    print(f"model - baseline logloss = {r['diff']:+.4f}  95% CI [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}]  (negative = model better)")


if __name__ == "__main__":
    main()

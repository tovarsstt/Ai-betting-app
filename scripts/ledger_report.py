#!/usr/bin/env python3
"""
ledger_report.py — score the app's OWN booked picks (data/pick_ledger.json) on
the two things that separate skill from luck:

  1. CLV  — did the pick beat the CLOSING line? Beating the close is the proven
            long-run predictor; a pick can LOSE but beat the close (good process)
            or WIN but miss it (lucky). This report flags both so the record
            measures process, not just outcomes.
  2. CALIBRATION — when the model says 70%, does it actually win ~70%? Buckets
            settled picks by predicted_prob and compares to real hit rate, per
            sport. Exposes where the model is over/under-confident.

CLV math mirrors src/utils/ledger.ts exactly (single definition of truth).
Pure read of the JSON ledger — no API call. CLI prints; --json emits structured.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

LEDGER = Path(__file__).parent.parent / "data" / "pick_ledger.json"
OVERCONF_PTS = 7.0  # predicted - actual above this => model is overconfident here


def to_decimal(american: float) -> float:
    return american / 100 + 1 if american > 0 else 100 / (-american) + 1


def clv_pct(bet_odds: float, closing_odds: float) -> float:
    """Match ledger.ts clvPct: how much better your price was than the close."""
    return (to_decimal(bet_odds) / to_decimal(closing_odds) - 1) * 100


def load() -> list:
    try:
        data = json.loads(LEDGER.read_text())
        return data if isinstance(data, list) else []
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []


# ── CLV ───────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ClvRow:
    sport: str
    selection: str
    odds: float
    close: float
    clv: float
    result: str
    flag: str  # skill-vs-luck read


def _clv_flag(clv: float, result: str) -> str:
    beat = clv > 0.5
    miss = clv < -0.5
    if result == "W" and miss:
        return "LUCKY (won but market closed shorter — process lagged)"
    if result == "L" and beat:
        return "GOOD PROCESS (beat the close, lost anyway — variance)"
    if beat:
        return "beat close"
    if miss:
        return "missed close"
    return "flat"


def clv_report(ledger: list) -> dict:
    rows = []
    for p in ledger:
        close = p.get("closing_odds")
        if close is None:
            continue
        clv = round(clv_pct(p["odds"], close), 2)
        rows.append(ClvRow(p.get("sport", "?"), p.get("selection", "?"),
                           p["odds"], close, clv, p.get("result", "PENDING"),
                           _clv_flag(clv, p.get("result", "PENDING"))))

    def agg(keyfn) -> dict:
        out: dict[str, list] = {}
        for r in rows:
            out.setdefault(keyfn(r), [])
            out[keyfn(r)].append(r.clv)
        return {k: {"n": len(v), "avg_clv": round(sum(v) / len(v), 2),
                    "beat_rate": round(sum(1 for c in v if c > 0) / len(v) * 100, 1)}
                for k, v in out.items()}

    all_clv = [r.clv for r in rows]
    pending_no_close = sum(1 for p in ledger
                           if p.get("result") == "PENDING" and p.get("closing_odds") is None)
    return {
        "graded": len(rows),
        "pending_awaiting_close": pending_no_close,
        "avg_clv_pct": round(sum(all_clv) / len(all_clv), 2) if all_clv else None,
        "beat_rate_pct": round(sum(1 for c in all_clv if c > 0) / len(all_clv) * 100, 1) if all_clv else None,
        "by_sport": agg(lambda r: r.sport),
        "picks": [r.__dict__ for r in sorted(rows, key=lambda r: r.clv, reverse=True)],
    }


# ── CALIBRATION ─────────────────────────────────────────────────────────────-─
BUCKETS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def _bucket(prob: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= prob < hi:
            return f"{int(lo*100)}-{int(min(hi,1.0)*100)}%"
    return "?"


def calibration_report(ledger: list) -> dict:
    settled = [p for p in ledger if p.get("result") in ("W", "L")
               and isinstance(p.get("predicted_prob"), (int, float))]
    no_prob = sum(1 for p in ledger if p.get("result") in ("W", "L")
                  and not isinstance(p.get("predicted_prob"), (int, float)))
    buckets: dict[str, list] = {}
    for p in settled:
        b = _bucket(float(p["predicted_prob"]))
        buckets.setdefault(b, [])
        buckets[b].append(p)

    rows = []
    for b in sorted(buckets):
        items = buckets[b]
        n = len(items)
        pred = sum(float(p["predicted_prob"]) for p in items) / n * 100
        actual = sum(1 for p in items if p["result"] == "W") / n * 100
        gap = pred - actual
        verdict = ("overconfident" if gap > OVERCONF_PTS else
                   "underconfident" if gap < -OVERCONF_PTS else "calibrated")
        rows.append({"bucket": b, "n": n, "pred_pct": round(pred, 1),
                     "actual_pct": round(actual, 1), "gap": round(gap, 1),
                     "verdict": verdict})
    return {
        "settled_with_prob": len(settled),
        "settled_missing_prob": no_prob,
        "enough_volume": len(settled) >= 30,
        "buckets": rows,
    }


def _print(report: dict) -> None:
    clv, cal = report["clv"], report["calibration"]
    print("== CLV (beating the close = the real edge) ==")
    if not clv["graded"]:
        print(f"  no closing lines stamped yet "
              f"({clv['pending_awaiting_close']} pending await capture — enable ENABLE_CLV_CAPTURE)")
    else:
        print(f"  graded {clv['graded']} | avg CLV {clv['avg_clv_pct']:+.2f}% | "
              f"beat-close {clv['beat_rate_pct']:.0f}%")
        for s, v in sorted(clv["by_sport"].items()):
            print(f"    {s:8} n={v['n']:3} avg {v['avg_clv']:+6.2f}%  beat {v['beat_rate']:.0f}%")
        for r in clv["picks"][:12]:
            print(f"    {r['clv']:+6.2f}%  {r['result']:1}  {r['sport']:7} {r['selection'][:34]:34} {r['flag']}")
    print("\n== CALIBRATION (does 70% really win 70%?) ==")
    if not cal["enough_volume"]:
        print(f"  only {cal['settled_with_prob']} settled picks carry predicted_prob "
              f"(need ~30 for signal; {cal['settled_missing_prob']} settled picks pre-date prob capture)")
    for r in cal["buckets"]:
        print(f"  {r['bucket']:8} n={r['n']:3} | pred {r['pred_pct']:5.1f}% vs actual "
              f"{r['actual_pct']:5.1f}% | gap {r['gap']:+5.1f} → {r['verdict']}")


def main() -> None:
    ledger = load()
    report = {"clv": clv_report(ledger), "calibration": calibration_report(ledger)}
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        _print(report)


if __name__ == "__main__":
    main()

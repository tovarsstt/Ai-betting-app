#!/usr/bin/env python3
"""
slip_linter.py — pre-bet gate that scores a PROPOSED ticket against the user's
OWN settled record before any money goes down.

Why: heuristic rule 11 ("2-3 legs, legs 1.50-5.0, never 5+") is the user's proven
edge, but prose isn't enforced — the linter turns it into a deterministic gate.
The thresholds are NOT invented: they're computed live from data/slips_raw.txt via
analyze_slips, so the gate adapts as fresh history is pasted. A shape the user
actually loses money in gets REJECTED with its real ROI as the reason.

Verdicts:
  ACCEPT  — every leg in a profitable band, ticket shape is a profitable shape.
  TRIM    — fixable: specific legs/legs-over-cap to cut, then it ACCEPTs.
  REJECT  — the ticket's own shape loses money in the record and can't be trimmed.

CLI:  echo '{"legs":[{"decimal":3.2,"selection":"X"},...]}' | python3 scripts/slip_linter.py --json
Pure functions, immutable outputs, no API calls. Never fabricates a number.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyze_slips import parse, odds_band  # reuse the single source of truth

MAX_LEGS = 4          # hard cap (rule 11); 2-3 is the target
TARGET_LEGS = (2, 3)
COMBINED_MIN = 2.5    # combined-decimal bankroll-growth lane
COMBINED_MAX = 8.0


def leg_bucket(n: int) -> str:
    if n == 1:
        return "single"
    if n <= 3:
        return "2-3 legs"
    if n <= 6:
        return "4-6 legs"
    return "7+ legs"


def roi_by(items: list, keyfn) -> dict:
    """ROI% per bucket from settled history. payout>=stake => won."""
    agg: dict[str, list] = {}
    for i in items:
        agg.setdefault(keyfn(i), [0.0, 0.0])  # [staked, returned]
        agg[keyfn(i)][0] += i["stake"]
        agg[keyfn(i)][1] += i["payout"]
    return {k: ((r - s) / s * 100 if s else 0.0) for k, (s, r) in agg.items()}


@dataclass(frozen=True)
class Verdict:
    status: str          # ACCEPT | TRIM | REJECT
    reasons: tuple       # human lines, each citing real ROI
    cut_legs: tuple      # indices of legs to drop (TRIM)
    keep_count: int      # legs remaining after trim


def _history_rois() -> tuple[dict, dict]:
    """(band_roi, shape_roi) from the user's settled slips. Empty if no file."""
    try:
        items = parse()
    except (FileNotFoundError, OSError):
        return {}, {}
    band = roi_by(items, lambda i: odds_band(i["dec"]))

    def legs_of(i):  # analyze_slips already tagged leg count
        return leg_bucket(i["legs"])
    return band, roi_by(items, legs_of)


def lint(legs: list[dict], band_roi: dict | None = None,
         shape_roi: dict | None = None) -> Verdict:
    """Score a ticket. `legs` = [{'decimal': float, 'selection': str}]."""
    if band_roi is None or shape_roi is None:
        band_roi, shape_roi = _history_rois()
    reasons: list[str] = []
    cut: list[int] = []

    # 1. Leg-level: drop any leg sitting in a band the user LOSES in.
    for idx, leg in enumerate(legs):
        dec = float(leg["decimal"])
        band = odds_band(dec)
        roi = band_roi.get(band)
        tag = leg.get("selection", f"leg {idx+1}")
        if roi is not None and roi < 0:
            cut.append(idx)
            reasons.append(f"CUT {tag} @ {dec:.2f} — {band} is {roi:+.0f}% ROI in your record")
        elif roi is None and (dec < 1.50 or dec >= 5.0):
            cut.append(idx)
            reasons.append(f"CUT {tag} @ {dec:.2f} — {band}, outside the 1.50-5.0 edge")

    kept = [l for i, l in enumerate(legs) if i not in cut]
    keep_n = len(kept)

    # 2. Over the hard cap — trim weakest (highest-priced = riskiest) down to 4.
    if keep_n > MAX_LEGS:
        ranked = sorted(range(len(legs)),
                        key=lambda i: float(legs[i]["decimal"]), reverse=True)
        for i in ranked:
            if i in cut:
                continue
            cut.append(i)
            keep_n -= 1
            sh = shape_roi.get("7+ legs", shape_roi.get("4-6 legs"))
            ev = f" ({sh:+.0f}% ROI)" if sh is not None else ""
            reasons.append(f"CUT leg {i+1} — over {MAX_LEGS}-leg cap; long stacks bleed{ev}")
            if keep_n <= MAX_LEGS:
                break

    # 3. Nothing left, or shape itself is a money-loser that trimming can't fix.
    if keep_n == 0:
        return Verdict("REJECT", ("every leg is in a losing band — PASS, force nothing",),
                       tuple(cut), 0)

    shape = leg_bucket(keep_n)
    sroi = shape_roi.get(shape)
    if sroi is not None and sroi < 0 and keep_n == 1:
        # singles bleed in the record; nudge toward the 2-3 lane.
        reasons.append(f"WARN single @ {sroi:+.0f}% ROI — your edge is 2-3 legs, "
                       f"pair this with another value leg")
    elif sroi is not None and sroi < 0:
        return Verdict("REJECT",
                       tuple(reasons + [f"{shape} is {sroi:+.0f}% ROI in your record — reshape to 2-3 legs"]),
                       tuple(cut), keep_n)

    # 4. Combined-odds lane check (warn only — doesn't block).
    combined = 1.0
    for l in kept:
        combined *= float(l["decimal"])
    if keep_n > 1 and not (COMBINED_MIN <= combined <= COMBINED_MAX):
        reasons.append(f"NOTE combined {combined:.2f} outside {COMBINED_MIN}-{COMBINED_MAX} "
                       f"growth lane")

    if keep_n not in TARGET_LEGS and keep_n <= MAX_LEGS and keep_n > 1:
        reasons.append(f"NOTE {keep_n} legs ok, but 2-3 is your +83% lane")

    status = "ACCEPT" if not cut else "TRIM"
    if status == "ACCEPT" and not reasons:
        reasons.append(f"clean — {shape}, all legs in the 1.50-5.0 edge")
    return Verdict(status, tuple(reasons), tuple(cut), keep_n)


def _main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    legs = payload.get("legs", [])
    if not legs:
        raise SystemExit("no legs — pass {\"legs\":[{\"decimal\":..,\"selection\":..}]}")
    v = lint(legs)
    out = {
        "status": v.status,
        "keep_count": v.keep_count,
        "cut_legs": list(v.cut_legs),
        "reasons": list(v.reasons),
    }
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2))
    else:
        print(f"[{v.status}]  keep {v.keep_count} leg(s)")
        for r in v.reasons:
            print(f"  - {r}")


if __name__ == "__main__":
    _main()

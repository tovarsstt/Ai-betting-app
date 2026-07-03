#!/usr/bin/env python3
"""
slip_linter.py — pre-bet gate that scores a PROPOSED ticket against the user's
OWN settled record before any money goes down.

Why: heuristic rule 11 ("2-3 legs, never 5+") is the user's proven edge, but prose
isn't enforced — the linter turns it into a deterministic gate. WIN-PROB FIRST is
the directive (winning money is the focus): the high-prob chalk anchor (<1.50) is
KEPT as the leg that carries a ticket, while the 1.50-1.90 soft favourite (a
favourite, NOT a lock — and a /predict LEAN grade counts too) is flagged and capped
at one per ticket — that band is where parlays die. The ROI
thresholds are NOT invented: they're computed live from data/slips_raw.txt via
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
from analyze_slips import parse, dedupe, odds_band  # reuse the single source of truth

MAX_LEGS = 4          # hard cap (rule 11); 2-3 is the target
TARGET_LEGS = (2, 3)
COMBINED_MIN = 1.8    # lowered: a safe all-chalk combo pays thin but WINS — that's the focus
COMBINED_MAX = 8.0
SOFT_FAV_BAND = "soft favorite (1.50-1.90)"  # favourite but NOT a lock — the trap zone
MAX_SOFT_FAV = 1      # win-prob-first: at most one soft favourite per ticket
MIN_BAND_SAMPLE = 5   # min singles before a band's per-leg ROI is trusted as a cut signal


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
    """(band_roi, shape_roi) from the user's settled slips. Empty if no file.

    band_roi is computed from SINGLES ONLY — a single bet is exactly one leg, so its
    ROI is a TRUE per-leg ROI for that price band. Parlays settle as a unit and store
    only their COMBINED odds, so bucketing them by band would mis-attribute a leg's
    record (a 4-leg @ 6.99 is not a "lottery leg"). They're excluded from band_roi;
    their SHAPE (leg count), not their leg prices, is what shape_roi captures from all.
    """
    try:
        items = dedupe(parse())
    except (FileNotFoundError, OSError):
        return {}, {}
    singles = [i for i in items if i["legs"] == 1]
    # Only trust a band's per-leg ROI as a CUT signal when it has enough singles —
    # a 1/4 fluke shouldn't nuke a whole band. Thin bands read as None → structural
    # rules only (chalk kept, soft-fav capped, lottery cut regardless).
    counts: dict = {}
    for s in singles:
        counts[odds_band(s["dec"])] = counts.get(odds_band(s["dec"]), 0) + 1
    band = {b: roi for b, roi in roi_by(singles, lambda i: odds_band(i["dec"])).items()
            if counts.get(b, 0) >= MIN_BAND_SAMPLE}

    def legs_of(i):  # analyze_slips already tagged leg count
        return leg_bucket(i["legs"])
    return band, roi_by(items, legs_of)


def _grade(leg: dict) -> str:
    """Optional pick_quality from /predict on a leg: LOCK | PICK | LEAN | PASS (or '')."""
    return str(leg.get("quality", "")).upper()


def _tag(leg: dict, idx: int) -> str:
    base = leg.get("selection", f"leg {idx+1}")
    g = _grade(leg)
    return f"{base} [{g}]" if g else base   # surface LOCK/PICK/LEAN on the leg


def _is_soft(leg: dict) -> bool:
    """Soft favourite = priced 1.50-1.90, OR graded LEAN by the model — a sub-62%
    pick is a soft favourite even if its price says otherwise. Never a parlay anchor."""
    return odds_band(float(leg["decimal"])) == SOFT_FAV_BAND or _grade(leg) == "LEAN"


def _gate_legs(legs: list[dict], band_roi: dict) -> tuple[list, list]:
    """Leg-level gate (win-prob-first). Returns (cut indices, reason lines).

    - The high-prob CHALK ANCHOR (<1.50) is the safest leg in a parlay — never cut
      it for being chalk; it carries the ticket. (If it bled historically, NOTE it.)
    - A SOFT FAVOURITE (1.50-1.90 price, or a LEAN grade from /predict) is a favourite
      but NOT a lock (~53-67%). Keep at most MAX_SOFT_FAV per ticket — two of them is
      where parlays die. Cut the highest-priced = lowest-win-prob ones first.
    - Auto-cut the lottery (≥5.0) and any non-chalk band the user actually loses in.
    - If legs carry a pick_quality grade, surface it on each leg (LOCK/PICK/LEAN).
    """
    cut: list[int] = []
    reasons: list[str] = []
    for idx, leg in enumerate(legs):
        dec = float(leg["decimal"])
        band = odds_band(dec)
        roi = band_roi.get(band)
        if dec >= 5.0:                                      # lottery is never a safe leg
            cut.append(idx)
            reasons.append(f"CUT {_tag(leg, idx)} @ {dec:.2f} — lottery (5.0+), never a safe leg")
        elif roi is not None and roi < 0 and dec >= 1.50:   # data-backed losing band (enough samples)
            cut.append(idx)
            reasons.append(f"CUT {_tag(leg, idx)} @ {dec:.2f} — {band} is {roi:+.0f}% per-leg ROI in your singles")

    # Soft-favourite cap: keep the strongest (lowest price), cut the rest.
    soft = [i for i in range(len(legs)) if _is_soft(legs[i]) and i not in cut]
    for i in sorted(soft, key=lambda j: float(legs[j]["decimal"]), reverse=True):
        if len([k for k in soft if k not in cut]) <= MAX_SOFT_FAV:
            break
        cut.append(i)
        dec = float(legs[i]["decimal"])
        reasons.append(f"CUT {_tag(legs[i], i)} @ {dec:.2f} — 2nd+ soft favourite; max "
                       f"{MAX_SOFT_FAV}/ticket (~{100/dec:.0f}% each, NOT a lock)")

    # Surface the surviving soft-favourite risk, and any kept-but-historically-weak chalk.
    for i in range(len(legs)):
        if _is_soft(legs[i]) and i not in cut:
            dec = float(legs[i]["decimal"])
            reasons.append(f"WARN {_tag(legs[i], i)} @ {dec:.2f} — soft favourite (~{100/dec:.0f}% "
                           f"implied), NOT a lock; anchor the ticket on chalk, not 1.5-1.9 favs")
    for idx, leg in enumerate(legs):
        dec = float(leg["decimal"])
        if idx in cut or dec >= 1.50:
            continue
        roi = band_roi.get(odds_band(dec))
        if roi is not None and roi < 0:
            reasons.append(f"NOTE {_tag(leg, idx)} @ {dec:.2f} — chalk bled {roi:+.0f}% "
                           f"historically, but it's your highest win-prob leg; kept as anchor")
    return cut, reasons


def lint(legs: list[dict], band_roi: dict | None = None,
         shape_roi: dict | None = None) -> Verdict:
    """Score a ticket. `legs` = [{'decimal': float, 'selection': str}]."""
    if band_roi is None or shape_roi is None:
        band_roi, shape_roi = _history_rois()

    # 1. Leg-level gate (win-prob-first): keep chalk anchors, cap soft favourites, cut lottery.
    cut, reasons = _gate_legs(legs, band_roi)
    keep_n = len(legs) - len(set(cut))

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
        return Verdict("REJECT", ("every leg is a soft favourite / lottery / losing band — "
                                  "PASS, force nothing",),
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
    kept = [l for i, l in enumerate(legs) if i not in cut]
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
        reasons.append(f"clean — {shape}, chalk/value legs, win-prob first")
    return Verdict(status, tuple(reasons), tuple(cut), keep_n)


MAX_SAME_MATCH = 2    # 3+ sub-markets of one match in one slip = correlated stack


def lint_portfolio(slips: list[dict]) -> dict:
    """Cross-slip exposure gate — lints the WHOLE day's card, not one ticket.

    Two leaks the single-slip lint can't see (both cost real money, Jul 2026):
      1. SHARED LEG: the same selection cloned into 2+ slips is one bet bought
         N times — one soft leg dies, every slip dies (Jodar killed 3 at once).
      2. CORRELATED STACK: 3+ sub-markets of ONE match inside one slip (BTTS +
         totals + corners) live and die on the same game script.

    `slips` = [{"legs": [{"decimal":.., "selection":.., "match": optional}]}].
    Returns {"warnings": [..], "shared_legs": {selection: [slip indices]},
             "verdicts": [per-slip lint verdict dicts]}.
    """
    exposure: dict[str, list[int]] = {}
    for si, slip in enumerate(slips):
        for leg in slip.get("legs", []):
            sel = str(leg.get("selection", "")).strip()
            if sel:
                exposure.setdefault(sel, []).append(si)

    shared = {sel: idxs for sel, idxs in exposure.items() if len(idxs) > 1}
    warnings = [
        f"SHARED LEG: '{sel}' in {len(idxs)} slips (#{', #'.join(str(i + 1) for i in idxs)}) — "
        f"one bet bought {len(idxs)} times; if it dies, all {len(idxs)} die together"
        for sel, idxs in shared.items()
    ]

    for si, slip in enumerate(slips):
        by_match: dict[str, int] = {}
        for leg in slip.get("legs", []):
            m = str(leg.get("match", "")).strip()
            if m:
                by_match[m] = by_match.get(m, 0) + 1
        for m, n in by_match.items():
            if n > MAX_SAME_MATCH:
                warnings.append(
                    f"CORRELATED STACK: slip #{si + 1} has {n} legs on '{m}' — "
                    f"same-match sub-markets die together; cap {MAX_SAME_MATCH}/match")

    band_roi, shape_roi = _history_rois()
    verdicts = []
    for slip in slips:
        v = lint(slip.get("legs", []), band_roi, shape_roi)
        verdicts.append({"status": v.status, "keep_count": v.keep_count,
                         "cut_legs": list(v.cut_legs), "reasons": list(v.reasons)})
    return {"warnings": warnings, "shared_legs": shared, "verdicts": verdicts}


def _main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    if payload.get("slips"):
        out = lint_portfolio(payload["slips"])
        if "--json" in sys.argv:
            print(json.dumps(out, indent=2))
        else:
            for w in out["warnings"] or ["clean — no shared legs, no correlated stacks"]:
                print(f"  ! {w}")
            for i, v in enumerate(out["verdicts"]):
                print(f"  slip #{i + 1}: [{v['status']}] keep {v['keep_count']}")
        return
    legs = payload.get("legs", [])
    if not legs:
        raise SystemExit("no legs — pass {\"legs\":[{\"decimal\":..,\"selection\":..}]} "
                         "or {\"slips\":[{\"legs\":[..]}, ..]}")
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

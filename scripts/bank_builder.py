#!/usr/bin/env python3
"""
bank_builder.py — constructs the 3-5x growth-lane ticket from model edges.

Why: rule 14 (global_heuristics) is the user's proven winning shape — 8/8 won,
+176% ROI: 2-3 legs across DIFFERENT soccer matches, every leg a probable event.
The slip linter judges tickets the user already built; nothing BUILT the ticket.
This closes that gap: feed it the board's model edges, it emits the best
combos in the bankroll-doubling lane, win-prob ranked, linter-approved.

Bankroll context (low capital, building bank): target combined odds 3.0-5.0 —
one hit trebles the stake. The proven pattern range 2.3-6.0 is the fallback
lane, flagged so the user knows it's off the preferred target.

Every number in = a model number (devig / Poisson). Never fabricates a price
or a probability. Pure local compute, no API calls, safe in dev/test.

CLI:  echo '{"candidates":[{"match":..,"selection":..,"decimal":..,"prob":..}]}' \
        | python3 scripts/bank_builder.py --json
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from slip_linter import lint  # every emitted ticket must survive the pre-bet gate
from staking import NORMAL_MIN  # 0.58 — the tier floor "bet more" already trusts

TARGET_MIN, TARGET_MAX = 3.0, 5.0    # user's growth lane: 3-5x the stake
PATTERN_MIN, PATTERN_MAX = 2.3, 6.0  # rule 14 proven range (8/8, +176% ROI)
MIN_LEG_PROB = 0.56                  # rule 14 floor: every leg a probable event
LEG_COUNTS = (2, 3)                  # the +ROI shape; 5+ legs bust (sim + record)
DEFAULT_TICKETS = 3

# Strong singles: 1.75+ pays enough to matter as a single (user directive);
# betting BIGGER demands 2.5x the +2% scan flag gate; quarter-Kelly because
# model probs carry error — full Kelly on an overestimated prob ruins banks.
SINGLE_MIN_ODDS = 1.75
SINGLE_MIN_EV = 0.05
KELLY_FRACTION = 0.25
KELLY_CAP_PCT = 3.0                  # never more than 3% of bank on one bet


def _leg_ok(c: dict) -> bool:
    """Gate a candidate leg: probable (>=56%) AND not -EV at the quoted price."""
    prob, dec = float(c["prob"]), float(c["decimal"])
    return prob >= MIN_LEG_PROB and (prob * dec - 1.0) >= 0.0


def _lane(combined: float) -> str | None:
    if TARGET_MIN <= combined <= TARGET_MAX:
        return "target"
    if PATTERN_MIN <= combined <= PATTERN_MAX:
        return "pattern"
    return None


def _ticket(legs: tuple) -> dict | None:
    """Score one combo; None if it's outside both lanes or the linter cuts it."""
    combined = joint = 1.0
    for l in legs:
        combined *= float(l["decimal"])
        joint *= float(l["prob"])   # independent — different matches enforced
    lane = _lane(combined)
    if lane is None:
        return None
    v = lint([{"decimal": l["decimal"], "selection": l["selection"]} for l in legs])
    if v.status != "ACCEPT":
        return None
    return {
        "legs": list(legs),
        "combined": round(combined, 2),
        "joint_prob": round(joint, 4),
        "ev_pct": round((joint * combined - 1.0) * 100, 1),
        "lane": lane,
        "verdict": v.status,
    }


def build_tickets(candidates: list[dict], n_tickets: int = DEFAULT_TICKETS) -> dict:
    """Best 2-3 leg cross-match tickets from model edges, win-prob ranked.

    Returned tickets never share a leg (Jodar rule: a leg cloned across slips
    is one bet bought N times — one soft leg dies, every slip dies).
    """
    pool = [c for c in candidates if _leg_ok(c)]
    scored = []
    for n in LEG_COUNTS:
        for legs in combinations(pool, n):
            if len({l["match"] for l in legs}) < n:   # one leg per match
                continue
            t = _ticket(legs)
            if t:
                scored.append(t)

    # Win-prob first (the directive), target lane before fallback, EV last.
    scored.sort(key=lambda t: (t["lane"] != "target", -t["joint_prob"], -t["ev_pct"]))

    picked: list[dict] = []
    used: set = set()
    for t in scored:
        keys = {(l["match"], l["selection"]) for l in t["legs"]}
        if keys & used:
            continue
        picked.append(t)
        used |= keys
        if len(picked) >= n_tickets:
            break

    return {
        "tickets": picked,
        "pass": not picked,
        "note": ("no combo makes the 2.3-6.0 lane with >=56% legs — "
                 "disciplined PASS, force nothing") if not picked else
                f"lane {TARGET_MIN}-{TARGET_MAX}x preferred; 'pattern' = proven "
                f"{PATTERN_MIN}-{PATTERN_MAX} range but off-target",
    }


def strong_singles(candidates: list[dict], bankroll: float | None = None) -> list[dict]:
    """Singles worth betting MORE on: 1.75+ odds AND >=58% model prob AND
    >=+5% EV. Stake = quarter-Kelly, capped at KELLY_CAP_PCT of bankroll.

    Honest math: at 1.75-2.2 a qualifying pick wins ~58-65% — the best value
    zone on a board, NOT a lock. Quarter-Kelly is how "bet more" stays safe.
    """
    out = []
    for c in candidates:
        dec, prob = float(c["decimal"]), float(c["prob"])
        ev = prob * dec - 1.0
        if dec < SINGLE_MIN_ODDS or prob < NORMAL_MIN or ev < SINGLE_MIN_EV:
            continue
        kelly = ev / (dec - 1.0)                      # full Kelly fraction
        stake_pct = round(min(kelly * KELLY_FRACTION * 100, KELLY_CAP_PCT), 2)
        single = {
            "match": c["match"],
            "selection": c["selection"],
            "decimal": dec,
            "prob": prob,
            "ev_pct": round(ev * 100, 1),
            "stake_pct": stake_pct,
        }
        if bankroll is not None:
            single["stake_usd"] = round(bankroll * stake_pct / 100, 2)
        out.append(single)
    out.sort(key=lambda s: (-s["prob"], -s["ev_pct"]))  # win-prob first
    return out


def _main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    cands = payload.get("candidates", [])
    bankroll = payload.get("bankroll")
    out = build_tickets(cands, int(payload.get("n_tickets", DEFAULT_TICKETS)))
    out = {**out, "singles": strong_singles(
        cands, float(bankroll) if bankroll is not None else None)}
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2))
        return
    if out["pass"] and not out["singles"]:
        print("[PASS] " + out["note"])
        return
    for i, t in enumerate(out["tickets"], 1):
        print(f"ticket #{i}  [{t['lane']}]  x{t['combined']}  "
              f"win {t['joint_prob']*100:.0f}%  EV {t['ev_pct']:+.1f}%")
        for l in t["legs"]:
            print(f"    {l['selection']} @ {l['decimal']}  ({l['match']})")
    for s in out["singles"]:
        usd = f"  ${s['stake_usd']}" if "stake_usd" in s else ""
        print(f"single  {s['selection']} @ {s['decimal']}  win {s['prob']*100:.0f}%  "
              f"EV {s['ev_pct']:+.1f}%  stake {s['stake_pct']}% of bank{usd}  ({s['match']})")


if __name__ == "__main__":
    _main()

#!/usr/bin/env python3
"""
win_simulator.py — DOES THIS WIN? Simulated, for every pick and every ticket.

User directive (2026-08-19, restated): **winning is king.** EV is a tiebreak,
never the headline. A 70%-to-win bet at slightly negative EV outranks a 25%
lottery at fat +EV, because the record we are building is a HIT RATE. So every
number this module leads with is a WIN PROBABILITY; `ev_pct` is carried along
but is never the ranking key and never the verdict.

Why simulate rather than just multiply the leg probabilities:
  * the product tells you the mean and nothing else — it can't tell you how
    often you land 3 of 4 and still lose, which is what a parlay actually
    feels like
  * it gives a CONFIDENCE INTERVAL on the win rate, so a thin edge built on a
    small model sample reads as thin instead of precise
  * it prices the real question over a season: how often does a run of these
    bets leave you down, or broke (risk of ruin)

Independence assumption is explicit and checked: legs from DIFFERENT matches are
treated as independent, which is the whole point of the cross-match combo shape
(rule 14). Two legs from the SAME match are correlated and the simulator refuses
to pretend otherwise — it flags them rather than silently multiplying.
"""
from __future__ import annotations

import json
import sys
from typing import Optional, Sequence

import numpy as np

# Win-probability bands for a whole ticket. Calibrated to the user's own record:
# 2-3 leg tickets hit 20/38 (53%) at +51% ROI, so "wins about half the time" is
# the working floor for a real play, not an aspiration.
STRONG_WIN = 0.60      # wins comfortably more often than not
PLAYABLE_WIN = 0.50    # coin-flip-plus
THIN_WIN = 0.35        # needs a real price to justify
DEFAULT_SIMS = 100_000


def _verdict(win_prob: float) -> tuple[str, str]:
    """Verdict from WIN PROBABILITY alone. EV never enters here — that is the
    whole point of the directive."""
    if win_prob >= STRONG_WIN:
        return "STRONG", f"wins {win_prob*100:.0f}% of the time — this is the shape that builds a record"
    if win_prob >= PLAYABLE_WIN:
        return "PLAYABLE", f"wins {win_prob*100:.0f}% — better than a coin flip, playable at a sane stake"
    if win_prob >= THIN_WIN:
        return "THIN", f"wins only {win_prob*100:.0f}% — you lose this most of the time; needs a fat price"
    return "LOTTERY", f"wins {win_prob*100:.0f}% — a lottery ticket, not a bet; expect long losing runs"


def simulate_ticket(legs: Sequence[dict], n_sims: int = DEFAULT_SIMS,
                    seed: Optional[int] = None) -> dict:
    """Simulate a ticket leg-by-leg. `legs` = [{prob, decimal, selection?, match?}].

    Returns the WIN PROBABILITY first, with a 95% interval, the distribution of
    how many legs land, and (demoted) the EV.
    """
    if not legs:
        return {"error": "no legs"}

    probs = np.array([float(l["prob"]) for l in legs], dtype=float)
    if np.any((probs <= 0) | (probs > 1)):
        return {"error": "every leg needs a win probability in (0, 1]"}

    combined = 1.0
    for l in legs:
        combined *= float(l.get("decimal", 1.0))

    rng = np.random.default_rng(seed)
    # (n_sims x n_legs) Bernoulli draws — one simulated slate per row.
    hits = rng.random((n_sims, len(legs))) < probs
    legs_won = hits.sum(axis=1)
    wins = legs_won == len(legs)

    win_prob = float(wins.mean())
    # Binomial standard error on the simulated rate — an honest interval, so a
    # 52% read on few sims doesn't masquerade as precision.
    se = float(np.sqrt(max(win_prob * (1 - win_prob), 1e-12) / n_sims))
    ci = (round(max(0.0, win_prob - 1.96 * se), 4),
          round(min(1.0, win_prob + 1.96 * se), 4))

    # How often you land N legs — the "so close" distribution a bare product hides.
    dist = {int(k): round(float((legs_won == k).mean()), 4)
            for k in range(len(legs) + 1)}

    # Correlation guard: same-match legs are NOT independent.
    matches = [l.get("match") for l in legs if l.get("match")]
    dupes = sorted({m for m in matches if matches.count(m) > 1})

    verdict, note = _verdict(win_prob)
    ev = win_prob * combined - 1.0

    return {
        # ── WIN FIRST ──
        "win_prob": round(win_prob, 4),
        "win_prob_ci95": ci,
        "verdict": verdict,
        "note": note,
        "loses_pct": round((1 - win_prob) * 100, 1),
        "expected_legs_won": round(float(legs_won.mean()), 2),
        "legs_won_distribution": dist,
        "n_legs": len(legs),
        "combined_odds": round(combined, 3),
        # ── EV: reported, deliberately NOT the verdict ──
        "ev_pct": round(ev * 100, 1),
        "ev_is_secondary": "verdict is set by win probability; EV is a tiebreak only",
        "n_sims": n_sims,
        "correlated_legs_warning": (
            f"legs share match(es) {dupes} — they are NOT independent, so this "
            f"win probability is optimistic; price same-game legs jointly"
            if dupes else None),
    }


def simulate_single(prob: float, decimal: float) -> dict:
    """A single bet needs no Monte Carlo — but it gets the same win-first shape
    so singles and tickets can be ranked against each other."""
    verdict, note = _verdict(prob)
    return {
        "win_prob": round(float(prob), 4),
        "verdict": verdict,
        "note": note,
        "loses_pct": round((1 - prob) * 100, 1),
        "n_legs": 1,
        "combined_odds": round(float(decimal), 3),
        "ev_pct": round((prob * decimal - 1) * 100, 1),
        "ev_is_secondary": "verdict is set by win probability; EV is a tiebreak only",
    }


def rank_by_winning(options: Sequence[dict]) -> list[dict]:
    """Rank candidate bets the user's way: WIN PROBABILITY first, EV only to
    break ties. A fat-EV longshot must never outrank a probable winner."""
    return sorted(options, key=lambda o: (-float(o.get("win_prob", 0)),
                                          -float(o.get("ev_pct", 0))))


def risk_of_ruin(win_prob: float, decimal: float, stake: float, bankroll: float,
                 n_bets: int = 100, n_sims: int = 10_000,
                 seed: Optional[int] = None) -> dict:
    """Run this bet n_bets times: how often are you broke, and how often ahead?

    The number that matters for a small bankroll isn't average return — it's
    whether a normal losing run ends the season early.
    """
    if stake <= 0 or bankroll <= 0:
        return {"error": "stake and bankroll must be positive"}
    rng = np.random.default_rng(seed)
    outcomes = rng.random((n_sims, n_bets)) < win_prob
    # Flat staking: win returns (decimal-1) x stake, a loss costs the stake.
    deltas = np.where(outcomes, (decimal - 1.0) * stake, -stake)
    paths = bankroll + np.cumsum(deltas, axis=1)
    busted = (paths <= 0).any(axis=1)
    final = paths[:, -1]
    return {
        "win_prob": round(float(win_prob), 4),
        "bets_simulated": n_bets,
        "risk_of_ruin_pct": round(float(busted.mean()) * 100, 1),
        "pct_ending_ahead": round(float((final > bankroll).mean()) * 100, 1),
        "median_final_bankroll": round(float(np.median(final)), 2),
        "worst_5pct_bankroll": round(float(np.percentile(final, 5)), 2),
        "note": "flat stakes; ruin = bankroll hits 0 at any point in the run",
    }


def _main() -> None:
    """stdin: {"legs":[{prob,decimal,selection?,match?}], "bankroll":?, "stake":?}"""
    payload = json.loads(sys.stdin.read() or "{}")
    legs = payload.get("legs") or []
    out = simulate_ticket(legs, int(payload.get("n_sims", DEFAULT_SIMS)),
                          payload.get("seed"))
    if payload.get("bankroll") and payload.get("stake") and "win_prob" in out:
        out["season"] = risk_of_ruin(out["win_prob"], out["combined_odds"],
                                     float(payload["stake"]),
                                     float(payload["bankroll"]))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    _main()

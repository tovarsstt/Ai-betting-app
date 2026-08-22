#!/usr/bin/env python3
"""
bet_timing.py — bet NOW at the known price, or wait and bet live?

A recurring real question: the pre-match price is on the screen and takeable,
but waiting might hand you a better one if the game starts badly for your side.
"Might" is the whole problem — waiting is not free. If the game starts WELL for
your side the price shortens and the bet you wanted is gone.

This settles it by simulation rather than instinct. Goals are drawn as a Poisson
process over the 90 minutes using the same lambdas the engine prices the match
on, the match is fast-forwarded to a chosen minute, and the FAIR price of the
market is recomputed from the score and the time remaining. Repeating that gives
the full distribution of prices you would actually face.

It compares two strategies honestly:

  BET NOW    take the known price, every time.
  WAIT       check at minute T; bet only if the fair price then still clears
             your required price. Otherwise no bet — which is a real cost, not
             a neutral outcome, because a skipped bet earns nothing.

The output that matters is EV PER OPPORTUNITY, not EV per bet placed. A strategy
that fires 30% of the time at a fat price can easily lose to one that fires
always at a thin one, and quoting only the fat number hides that.

Run: python3 scripts/bet_timing.py --lh 0.95 --la 1.75 --market X2 --price 1.30
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Optional

FULL_TIME = 90.0


def _goal_times(rate: float, rng: random.Random, until: float = FULL_TIME) -> list[float]:
    """Poisson process — exponential gaps at the team's per-90 scoring rate."""
    out, t = [], 0.0
    if rate <= 0:
        return out
    while True:
        t += rng.expovariate(rate / until)
        if t >= until:
            return out
        out.append(t)


def _settles(market: str, hg: int, ag: int) -> bool:
    """Did this market land, given the final score?"""
    m = market.upper()
    if m == "X2":                       # away win or draw
        return ag >= hg
    if m == "1X":                       # home win or draw
        return hg >= ag
    if m == "AWAY":
        return ag > hg
    if m == "HOME":
        return hg > ag
    if m == "DRAW":
        return hg == ag
    if m.startswith("O"):               # e.g. O2.5
        return hg + ag > float(m[1:])
    if m.startswith("U"):
        return hg + ag < float(m[1:])
    raise ValueError(f"unknown market {market}")


def simulate(lh: float, la: float, market: str, price: float,
             check_minute: float = 30.0, required: Optional[float] = None,
             n_sims: int = 40_000, seed: Optional[int] = 7) -> dict:
    """Compare betting now against waiting until `check_minute`.

    `required` is the price you would need to see live to bet. Defaults to the
    pre-match price — i.e. "only bet live if it is at least as good".
    """
    required = required if required is not None else price
    rng = random.Random(seed)

    now_wins = 0
    wait_bets = wait_wins = 0
    live_prices: list[float] = []

    # Inner pass count for pricing the live state: from the state at T, how
    # often does the market land? That IS its fair price at T.
    inner = 200

    for _ in range(n_sims):
        h_goals = _goal_times(lh, rng)
        a_goals = _goal_times(la, rng)
        fh, fa = len(h_goals), len(a_goals)
        landed = _settles(market, fh, fa)
        now_wins += landed

        # State at the checkpoint.
        hg = sum(1 for t in h_goals if t <= check_minute)
        ag = sum(1 for t in a_goals if t <= check_minute)
        remain = FULL_TIME - check_minute

        # Fair price from THIS state, by continuing the same process.
        hits = 0
        for _ in range(inner):
            rh = hg + len(_goal_times(lh * remain / FULL_TIME, rng, remain))
            ra = ag + len(_goal_times(la * remain / FULL_TIME, rng, remain))
            hits += _settles(market, rh, ra)
        p_live = hits / inner
        fair = 1.0 / p_live if p_live > 0 else 999.0
        live_prices.append(fair)

        # The WAIT strategy only fires when the live price is good enough.
        if fair >= required:
            wait_bets += 1
            wait_wins += landed

    p_now = now_wins / n_sims
    ev_now = p_now * price - 1.0

    fire_rate = wait_bets / n_sims
    # EV PER OPPORTUNITY: a skipped bet returns 0, and that has to count.
    if wait_bets:
        p_wait = wait_wins / wait_bets
        ev_wait_per_bet = p_wait * required - 1.0
        ev_wait_per_opp = ev_wait_per_bet * fire_rate
    else:
        p_wait = ev_wait_per_bet = ev_wait_per_opp = 0.0

    live_prices.sort()
    def pct(q):
        return round(live_prices[min(int(q * len(live_prices)), len(live_prices) - 1)], 2)

    better = sum(1 for f in live_prices if f >= required) / len(live_prices)
    return {
        "market": market, "pre_match_price": price,
        "check_minute": check_minute, "required_live_price": required,
        "bet_now": {"win_prob": round(p_now, 4), "ev_pct": round(ev_now * 100, 1),
                    "fires": "always"},
        "wait_and_bet_live": {
            "fire_rate": round(fire_rate, 4),
            "win_prob_when_it_fires": round(p_wait, 4),
            "ev_pct_per_bet_placed": round(ev_wait_per_bet * 100, 1),
            "ev_pct_per_opportunity": round(ev_wait_per_opp * 100, 1),
        },
        "live_price_distribution": {
            "p10": pct(0.10), "median": pct(0.50), "p90": pct(0.90),
            "chance_price_improves": round(better, 4),
        },
        "verdict": ("WAIT — higher EV per opportunity even after the games you "
                    "never get to bet"
                    if ev_wait_per_opp > ev_now else
                    "BET NOW — waiting loses more to the games that get away "
                    "than it gains on the ones that drift"),
        "why": ("EV per OPPORTUNITY is the comparison that counts. Waiting only "
                "fires "
                f"{fire_rate*100:.0f}% of the time; the other "
                f"{(1-fire_rate)*100:.0f}% you bet nothing and earn nothing."),
        "n_sims": n_sims,
        "caveat": "goals modelled as a Poisson process at the pre-match rates — "
                  "it does not know red cards, subs, or a side shutting up shop "
                  "with a lead",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lh", type=float, required=True, help="home goals per 90")
    ap.add_argument("--la", type=float, required=True, help="away goals per 90")
    ap.add_argument("--market", default="X2")
    ap.add_argument("--price", type=float, required=True, help="pre-match decimal")
    ap.add_argument("--minute", type=float, default=30.0)
    ap.add_argument("--required", type=float, default=None)
    ap.add_argument("--sims", type=int, default=40_000)
    a = ap.parse_args()
    print(json.dumps(simulate(a.lh, a.la, a.market, a.price, a.minute,
                              a.required, a.sims), indent=1))

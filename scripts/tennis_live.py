"""
tennis_live.py — in-play win probability from the current set score.

The pre-match model (edge_api.py) prices the WHOLE match once, before a ball
is hit. It has no way to update as sets are won — a player up 2 sets to 0 in
a best-of-5 still shows their pre-match number. This fills that gap with the
standard "race to N set-wins" Markov model:

  1. Invert the pre-match match-win probability into a per-SET win probability
     (assumes sets are i.i.d. Bernoulli(p) — a simplification, but the same
     one the betting market itself uses for live set-score pricing).
  2. Given the live score (sets won by each player), recompute the win
     probability as a race to `sets_to_win` using that same per-set p.

No serve/game-level detail (that needs point-by-point data we don't have —
see fetch_tennis_form.py's clutch-model gap). This only answers "given the
match was an X% pre-match and it's now 1 set to 0, what's the live number."
"""
from __future__ import annotations

from functools import lru_cache

from scipy.optimize import brentq


def sets_to_win(best_of: int) -> int:
    """2 for best-of-3 (WTA always, most ATP), 3 for best-of-5 (ATP majors)."""
    if best_of not in (3, 5):
        raise ValueError(f"best_of must be 3 or 5, got {best_of}")
    return 2 if best_of == 3 else 3


@lru_cache(maxsize=4096)
def race_prob(i: int, j: int, p: float) -> float:
    """P(A wins) when A needs `i` more sets, B needs `j` more sets, and A wins
    any given set with probability p (i.i.d.). Standard win-the-race recursion."""
    if i <= 0:
        return 1.0
    if j <= 0:
        return 0.0
    return p * race_prob(i - 1, j, p) + (1 - p) * race_prob(i, j - 1, p)


def implied_set_prob(match_prob: float, best_of: int) -> float:
    """Invert the pre-match MATCH win probability into a per-SET win
    probability. race_prob(N, N, p) is monotonic increasing in p, so this
    has a unique root on (0, 1)."""
    n = sets_to_win(best_of)
    if not 0.0 < match_prob < 1.0:
        raise ValueError(f"match_prob must be in (0,1), got {match_prob}")
    lo, hi = 1e-6, 1 - 1e-6
    f = lambda p: race_prob(n, n, p) - match_prob
    return float(brentq(f, lo, hi, xtol=1e-8))


def live_win_prob(pregame_match_prob: float, sets_won_home: int,
                   sets_won_away: int, best_of: int = 3) -> dict:
    """Recompute match win probability given the live set score.

    Returns the live home win prob plus the intermediate per-set prob so the
    caller can show its work. If the match is already decided by the sets
    given, returns 1.0 / 0.0 (no ambiguity left)."""
    n = sets_to_win(best_of)
    if sets_won_home < 0 or sets_won_away < 0:
        raise ValueError("set counts cannot be negative")
    if sets_won_home > n or sets_won_away > n:
        raise ValueError(f"best_of={best_of} caps a player at {n} set wins")

    p_set = implied_set_prob(pregame_match_prob, best_of)
    needs_home, needs_away = n - sets_won_home, n - sets_won_away
    live_home = race_prob(needs_home, needs_away, p_set)
    return {
        "best_of": best_of,
        "sets_to_win": n,
        "sets_won_home": sets_won_home,
        "sets_won_away": sets_won_away,
        "implied_set_prob_home": round(p_set, 4),
        "pregame_match_prob_home": round(pregame_match_prob, 4),
        "live_match_prob_home": round(live_home, 4),
        "match_decided": live_home in (0.0, 1.0),
    }

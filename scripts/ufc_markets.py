"""
UFC / MMA markets engine — Caveman Locks.

Pure math, no network. Prices every common UFC market from one fight model:

    Moneyline (fighter to win — 2-way, draws ~0.5% ignored)
    Method of victory  — KO/TKO, Submission, Decision (per fighter + grouped)
    Round Over/Under   — 1.5 / 2.5 (and 3.5 / 4.5 for 5-round fights),
                         split at the 2:30 mid-round mark
    Fight goes the distance — Yes / No
    Round betting       — finish probability per round

Honest data policy (mirrors soccer skill): when a fighter's real finish/KO/sub
splits are supplied we use them; otherwise we fall back to documented UFC-wide
EMPIRICAL priors and FLAG it. We never invent fighter-specific stats.

Win probability comes from the devigged moneyline when no independent rating is
provided — same pattern as soccer ("xG unavailable → use devigged implied prob").
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# Shared odds helpers (DRY — defined once in soccer_markets)
from soccer_markets import american_to_decimal, decimal_to_american, fair_odds, ev_pct

# ── Documented UFC-wide empirical priors (fallbacks only, always flagged) ─────
# Modern-era UFC: roughly half of fights end inside the distance; of those
# finishes, KO/TKO outnumber submissions ~62/38. Finishes skew to early rounds.
EMPIRICAL_FINISH_RATE = 0.52   # P(fight ends inside distance) league-wide
EMPIRICAL_KO_SHARE = 0.62      # of finishes, share that are KO/TKO
EMPIRICAL_SUB_SHARE = 0.38     # of finishes, share that are submission
FINISH_ROUND_DECAY = 0.70      # each later round ~0.70x prior round's finish mass


@dataclass(frozen=True)
class Fighter:
    """One fighter. Unknown fields fall back to empirical priors (flagged)."""
    name: str
    win_prob: Optional[float] = None    # independent estimate; else from devig
    finish_rate: Optional[float] = None # P(this fighter finishes when winning)
    ko_share: Optional[float] = None    # of their finishes, share that are KO
    sub_share: Optional[float] = None   # of their finishes, share submission


# ── Moneyline devig (2-way) ───────────────────────────────────────────────────
def devig_2way(odds_a: float, odds_b: float) -> dict:
    raw_a = 1.0 / american_to_decimal(odds_a)
    raw_b = 1.0 / american_to_decimal(odds_b)
    overround = raw_a + raw_b
    if overround <= 0:
        return {"a": 0.5, "b": 0.5, "vig_pct": 0.0}
    return {
        "a": raw_a / overround,
        "b": raw_b / overround,
        "vig_pct": round((overround - 1.0) * 100, 2),
    }


# ── Fight model ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FightBook:
    """All market probabilities for the fight. 'a'/'b' = fighter order in."""
    name_a: str
    name_b: str
    p_a: float
    p_b: float
    # method (per fighter)
    a_ko: float
    a_sub: float
    a_dec: float
    b_ko: float
    b_sub: float
    b_dec: float
    # grouped method
    ko_any: float
    sub_any: float
    decision_any: float   # == goes the distance
    # distance
    goes_distance: float
    not_distance: float
    # per-round finish prob (1-indexed list) and round O/U
    finish_by_round: list[float]
    round_totals: dict[float, dict[str, float]]
    scheduled_rounds: int
    used_empirical: bool


def _split_finish(p_win: float, f: Fighter) -> tuple[float, float, float]:
    """Return (ko, sub, dec) probabilities for a fighter given their win prob."""
    finish_rate = f.finish_rate if f.finish_rate is not None else EMPIRICAL_FINISH_RATE
    ko_share = f.ko_share if f.ko_share is not None else EMPIRICAL_KO_SHARE
    sub_share = f.sub_share if f.sub_share is not None else EMPIRICAL_SUB_SHARE
    # normalize ko/sub shares defensively
    s = ko_share + sub_share
    if s > 0:
        ko_share, sub_share = ko_share / s, sub_share / s
    p_finish = p_win * finish_rate
    return p_finish * ko_share, p_finish * sub_share, p_win * (1.0 - finish_rate)


def _round_finish_distribution(total_finish: float, n_rounds: int) -> list[float]:
    """Spread total finish mass across rounds with geometric early-round decay."""
    weights = [FINISH_ROUND_DECAY**r for r in range(n_rounds)]
    wsum = sum(weights)
    if wsum <= 0:
        return [0.0] * n_rounds
    return [total_finish * (w / wsum) for w in weights]


def build_fight(
    a: Fighter,
    b: Fighter,
    scheduled_rounds: int = 3,
    moneyline: Optional[tuple[float, float]] = None,
) -> FightBook:
    """
    Build the full market board. Win probs come from (priority):
    explicit Fighter.win_prob → devigged moneyline → 50/50.
    """
    used_empirical = (
        a.finish_rate is None or b.finish_rate is None
        or a.ko_share is None or b.ko_share is None
    )

    # ── win probabilities ────────────────────────────────────────────────────
    if a.win_prob is not None and b.win_prob is not None:
        tot = a.win_prob + b.win_prob
        p_a, p_b = (a.win_prob / tot, b.win_prob / tot) if tot > 0 else (0.5, 0.5)
    elif moneyline is not None:
        dv = devig_2way(moneyline[0], moneyline[1])
        p_a, p_b = dv["a"], dv["b"]
    else:
        p_a, p_b = 0.5, 0.5

    # ── method split per fighter ───────────────────────────────────────────────
    a_ko, a_sub, a_dec = _split_finish(p_a, a)
    b_ko, b_sub, b_dec = _split_finish(p_b, b)

    ko_any = a_ko + b_ko
    sub_any = a_sub + b_sub
    decision_any = a_dec + b_dec
    total_finish = ko_any + sub_any
    goes_distance = decision_any

    # ── per-round finish distribution + round O/U (2:30 mid-round split) ───────
    finish_by_round = _round_finish_distribution(total_finish, scheduled_rounds)

    def under_prob(line: float) -> float:
        # line k.5: full finish mass of rounds 1..k + half of round k+1
        k = math.floor(line)
        full = sum(finish_by_round[:k])
        half = 0.5 * finish_by_round[k] if k < len(finish_by_round) else 0.0
        return min(1.0, full + half)

    lines = [1.5, 2.5] + ([3.5, 4.5] if scheduled_rounds == 5 else [])
    round_totals = {
        ln: {"under": round(under_prob(ln), 4), "over": round(1.0 - under_prob(ln), 4)}
        for ln in lines
    }

    return FightBook(
        name_a=a.name, name_b=b.name, p_a=p_a, p_b=p_b,
        a_ko=a_ko, a_sub=a_sub, a_dec=a_dec, b_ko=b_ko, b_sub=b_sub, b_dec=b_dec,
        ko_any=ko_any, sub_any=sub_any, decision_any=decision_any,
        goes_distance=goes_distance, not_distance=total_finish,
        finish_by_round=[round(x, 4) for x in finish_by_round],
        round_totals=round_totals, scheduled_rounds=scheduled_rounds,
        used_empirical=used_empirical,
    )


# ── Recommendation ────────────────────────────────────────────────────────────
# No draw to insure (UFC draws ~0.5%), so the value play is different from
# soccer: heavy favourites are ML-juiced (e.g. -300), so when the model supports
# it we route to a better-paying derivative — Fav by KO, by decision, or the
# round/distance line. Ranking still obeys CLAUDE.md: win-prob first, edge second.
HEAVY_FAV = 0.66       # ML this short pays poorly → look for value derivative
STRONG_FINISHER = 0.55 # fav's finish share of their own wins → lean method/under
MIN_VALUE_EV = 0.02


@dataclass(frozen=True)
class UFCOdds:
    """Optional American book prices. None = unknown (edge not computed)."""
    ml_a: Optional[float] = None
    ml_b: Optional[float] = None
    fav_ko: Optional[float] = None        # favourite wins by KO/TKO
    fav_dec: Optional[float] = None        # favourite wins by decision
    not_distance: Optional[float] = None   # fight does NOT go the distance
    goes_distance: Optional[float] = None  # fight goes the distance


def _pick(market: str, side: str, prob: float, odds: Optional[float], why: str) -> dict:
    out = {
        "market": market, "side": side,
        "model_prob": round(prob, 4), "fair_odds": fair_odds(prob), "rationale": why,
    }
    if odds is not None:
        out["book_odds_american"] = odds
        out["ev_pct"] = round(ev_pct(prob, odds) * 100, 2)
        out["value"] = out["ev_pct"] > 0
    return out


def recommend(book: FightBook, odds: Optional[UFCOdds] = None) -> dict:
    odds = odds or UFCOdds()
    a_is_fav = book.p_a >= book.p_b
    fav = book.name_a if a_is_fav else book.name_b
    dog = book.name_b if a_is_fav else book.name_a
    p_fav = book.p_a if a_is_fav else book.p_b
    fav_ko = book.a_ko if a_is_fav else book.b_ko
    fav_sub = book.a_sub if a_is_fav else book.b_sub
    fav_dec = book.a_dec if a_is_fav else book.b_dec
    o_ml = odds.ml_a if a_is_fav else odds.ml_b

    fav_finish = fav_ko + fav_sub
    finish_share = fav_finish / p_fav if p_fav > 0 else 0.0  # of fav's wins
    ml_pick = _pick(
        "Moneyline", fav, p_fav, o_ml,
        f"{fav} wins {p_fav:.0%} of the model.",
    )

    # ── primary + value alternative ────────────────────────────────────────────
    value_alt = None
    if p_fav >= HEAVY_FAV and finish_share >= STRONG_FINISHER:
        # Heavy fav who finishes → method/under pays more for the same read
        primary = _pick(
            "Fight does NOT go the distance", f"{fav} to finish", book.not_distance,
            odds.not_distance,
            f"{fav} is a {p_fav:.0%} favourite and finishes {finish_share:.0%} of wins "
            f"→ {book.not_distance:.0%} the fight ends inside the distance. "
            f"Better price than a juiced ML.",
        )
        value_alt = ml_pick
    elif p_fav >= HEAVY_FAV:
        # Heavy fav who grinds decisions → 'fav by decision' pays more
        primary = _pick(
            "Method — by Decision", f"{fav} by decision", fav_dec, odds.fav_dec,
            f"{fav} ({p_fav:.0%}) wins by decision {fav_dec/p_fav:.0%} of the time and "
            f"the ML is short — {fav} by decision pays more for the likely path.",
        )
        value_alt = ml_pick
    else:
        primary = ml_pick  # competitive fight — straight ML is cleanest

    # ── method lean (most likely single method overall) ────────────────────────
    methods = [
        (f"{book.name_a} by KO/TKO", book.a_ko), (f"{book.name_a} by Sub", book.a_sub),
        (f"{book.name_a} by Decision", book.a_dec),
        (f"{book.name_b} by KO/TKO", book.b_ko), (f"{book.name_b} by Sub", book.b_sub),
        (f"{book.name_b} by Decision", book.b_dec),
    ]
    m_side, m_prob = max(methods, key=lambda x: x[1])
    method_lean = _pick("Method of Victory", m_side, m_prob, None,
                        f"Most likely single outcome at {m_prob:.0%}.")

    # ── distance lean ────────────────────────────────────────────────────────────
    goes = book.goes_distance >= book.not_distance
    dist_prob = book.goes_distance if goes else book.not_distance
    dist_odds = odds.goes_distance if goes else odds.not_distance
    distance_lean = _pick(
        "Fight goes the distance", "Yes" if goes else "No", dist_prob, dist_odds,
        f"{'Goes the distance' if goes else 'Ends inside the distance'} at {dist_prob:.0%}.",
    )

    # ── best round total (most confident line) ─────────────────────────────────
    best_line, best_side, best_prob = None, None, 0.0
    for ln, v in book.round_totals.items():
        side, prob = ("Under", v["under"]) if v["under"] >= v["over"] else ("Over", v["over"])
        if prob > best_prob:
            best_line, best_side, best_prob = ln, side, prob
    round_total = (
        _pick(f"Total Rounds {best_line}", f"{best_side} {best_line}", best_prob, None,
              f"Most confident round line at {best_prob:.0%}.")
        if best_line is not None else None
    )

    return {
        "favorite": fav, "underdog": dog,
        "fav_win_prob": round(p_fav, 4),
        "primary_pick": primary,
        "value_alternative": value_alt,
        "method_lean": method_lean,
        "distance_lean": distance_lean,
        "round_total_lean": round_total,
        "data_note": (
            "empirical UFC priors used for some finish/method splits — flag to user"
            if book.used_empirical else "fighter-specific finish data used"
        ),
    }

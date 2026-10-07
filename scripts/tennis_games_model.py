#!/usr/bin/env python3
"""
tennis_games_model.py — games totals / game handicap from REAL serve stats.
Reads data/tennis_serve.json (fetch_tennis_serve_stats.py, ATP+WTA).

Why: the user bets tennis games markets (O35.5 games, -3.5 games) but the app
only priced ML. Every number here traces to measured serve stats:
  p_point(server) = 1st% x 1st-win% + (1-1st%) x 2nd-win%      (arithmetic)
  P(hold)         = exact Markov recursion on game score (deuce closed form)
  set / match / games distribution = simulation of the actual scoring rules
    (6 games win-by-2, tiebreak at 6-6 counts as the 13th game)

Honest limitation, stated in every output: serve stats are vs TOUR-AVERAGE
returners — no per-opponent return adjustment exists in the data. Optional
`target_match_prob` (e.g. the ratings model's number) calibrates the LEVEL by
shifting both players' point probs a common delta; the games SHAPE stays from
the measured serve profiles. Unknown player → refusal, never an estimate.
"""
from __future__ import annotations

import json
import math
import random
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "tennis_serve.json"
N_SIMS = 10_000
SEED = 8128            # deterministic runs — same inputs, same card


def load() -> dict | None:
    try:
        return json.loads(DATA.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def player_key(name: str, players: dict) -> str | None:
    """Match 'Sebastian Baez' / 'Baez, Sebastian' / 'Alejandro Davidovich Fokina'
    to serve-stat key 'surname(s)|first-initial' (e.g. 'davidovich fokina|a')."""
    n = _norm(name)
    candidates = []
    if "," in n:                                  # 'Surname(s), First'
        surname, _, first = (x.strip() for x in n.partition(","))
        if surname and first:
            candidates.append(f"{surname}|{first[0]}")
    parts = [p for p in n.replace(",", " ").split() if p]
    if not parts:
        return None
    if len(parts) >= 2:
        candidates += [
            f"{' '.join(parts[1:])}|{parts[0][0]}",   # First Surname(s)
            f"{parts[-1]}|{parts[0][0]}",             # First ... Last-word
            f"{' '.join(parts[:-1])}|{parts[-1][0]}", # Surname(s) First
        ]
    for c in candidates:
        if c in players:
            return c
    # unique-surname fallback: any input token equals the key's full surname part
    for tok in (" ".join(parts[1:]), parts[-1], parts[0]):
        hits = [k for k in players if k.split("|")[0] == tok]
        if len(hits) == 1:
            return hits[0]
    hits = [k for k in players if parts[-1] and parts[-1] in k.split("|")[0]]
    return hits[0] if len(hits) == 1 else None


def point_prob(stats: dict) -> float:
    """Service-point win prob from measured serve splits (pure arithmetic)."""
    fs = float(stats["first_serve_pct"])
    return fs * float(stats["first_serve_win_pct"]) + \
        (1.0 - fs) * float(stats["second_serve_win_pct"])


@lru_cache(maxsize=None)
def hold_prob(p: float) -> float:
    """P(server holds) — exact recursion; from deuce it's p^2/(p^2+q^2)."""
    q = 1.0 - p
    deuce = p * p / (p * p + q * q)

    @lru_cache(maxsize=None)
    def w(a: int, b: int) -> float:
        if a >= 4 and a - b >= 2:
            return 1.0
        if b >= 4 and b - a >= 2:
            return 0.0
        if a >= 3 and b >= 3:
            if a == b:                       # deuce
                return deuce
            if a > b:                        # advantage server
                return p + q * deuce
            return p * deuce                 # advantage returner
        return p * w(a + 1, b) + q * w(a, b + 1)

    return w(0, 0)


def _sim_tiebreak(pa: float, pb: float, rng: random.Random, first: int) -> int:
    """First to 7 win-by-2; serve rotation 1 then 2-2. Returns winner 0=A,1=B."""
    pts = [0, 0]
    server, serves_left = first, 1
    while True:
        p_srv = pa if server == 0 else pb
        winner = server if rng.random() < p_srv else 1 - server
        pts[winner] += 1
        if pts[winner] >= 7 and pts[winner] - pts[1 - winner] >= 2:
            return winner
        serves_left -= 1
        if serves_left == 0:
            server, serves_left = 1 - server, 2


def _sim_set(pa: float, pb: float, rng: random.Random,
             first: int) -> tuple[int, int, int, int]:
    """(winner, games_a, games_b, next_first_server). TB set ends 7-6."""
    ha, hb = hold_prob(round(pa, 4)), hold_prob(round(pb, 4))
    g = [0, 0]
    server = first
    while True:
        p_hold = ha if server == 0 else hb
        winner = server if rng.random() < p_hold else 1 - server
        g[winner] += 1
        server = 1 - server
        if g[winner] >= 6 and g[winner] - g[1 - winner] >= 2:
            return winner, g[0], g[1], server
        if g[0] == 6 and g[1] == 6:
            tb = _sim_tiebreak(pa, pb, rng, server)
            g[tb] += 1
            return tb, g[0], g[1], 1 - server


def _sim_set_from(pa: float, pb: float, rng: random.Random, first: int,
                  ga: int = 0, gb: int = 0) -> tuple[int, int, int, int]:
    """Play out a set from an ARBITRARY game score — the in-play case.

    `_sim_set` always starts 0-0, which is why live pricing could only ever use
    the SET score: a player 4-3 up in the opening set got no credit at all
    because sets were still 0-0. This finishes the set in progress.
    """
    ha, hb = hold_prob(round(pa, 4)), hold_prob(round(pb, 4))
    g = [int(ga), int(gb)]
    server = first
    # Already over (caller handed us a finished set) — report it as-is.
    for w in (0, 1):
        if g[w] >= 6 and g[w] - g[1 - w] >= 2:
            return w, g[0], g[1], server
    while True:
        p_hold = ha if server == 0 else hb
        winner = server if rng.random() < p_hold else 1 - server
        g[winner] += 1
        server = 1 - server
        if g[winner] >= 6 and g[winner] - g[1 - winner] >= 2:
            return winner, g[0], g[1], server
        if g[0] == 6 and g[1] == 6:
            tb = _sim_tiebreak(pa, pb, rng, server)
            g[tb] += 1
            return tb, g[0], g[1], 1 - server


SET_PRIOR_WEIGHT = 2.5     # trust the season serve stats as much as this many sets


def _set_win_prob(pa: float, pb: float, n_sims: int = 2000, seed: int = SEED) -> float:
    """P(A wins a fresh 0-0 set) from season point probs — the per-set PRIOR
    used to Bayesian-shrink toward sets already decided (see
    `_shrink_toward_sets_played`)."""
    rng = random.Random(seed)
    return sum(1 for _ in range(n_sims) if _sim_set(pa, pb, rng, 0)[0] == 0) / n_sims


def _shrink_toward_sets_played(pa: float, pb: float,
                               sets_a: int, sets_b: int) -> tuple[float, float]:
    """Bayesian-shrink point-win probs toward what the SETS ALREADY DECIDED
    imply, so a lopsided score (e.g. 2 sets to 1) moves the model even when
    both players' SEASON point_prob are nearly identical.

    The gap this closes: point_prob() is a season average, so two players can
    carry near-identical serve stats while one is visibly outplaying the
    other today (Shimabukuro 0.667 vs Rinderknech 0.664, 2026-08-30 US Open —
    Rinderknech up 2 sets to 1 with an early break in the 4th, the market at
    ~98%, this model at 76% before this fix). There is no point-by-point live
    feed, so sets already won are the only EXACT in-match evidence available
    beyond the current game score (which `_sim_set_from` already prices
    correctly). Treat `_set_win_prob(pa, pb)` as a Beta-Binomial prior worth
    `SET_PRIOR_WEIGHT` sets of evidence, update it with the sets actually won,
    and translate the shrunk per-set probability back into a common point-prob
    delta (the same bisection `predict()` uses for `target_match_prob_a`).
    More sets played -> more weight on today, less on the season number. At
    0-0 sets this returns pa, pb unchanged.
    """
    n_sets = sets_a + sets_b
    if n_sets == 0:
        return pa, pb
    p_set0 = _set_win_prob(pa, pb)
    target = (p_set0 * SET_PRIOR_WEIGHT + sets_a) / (SET_PRIOR_WEIGHT + n_sets)
    target = min(max(target, 1e-4), 1 - 1e-4)

    lo, hi = -0.08, 0.08
    for _ in range(12):
        delta = (lo + hi) / 2
        p = _set_win_prob(pa + delta, pb - delta)
        if p < target:
            lo = delta
        else:
            hi = delta
    delta = (lo + hi) / 2
    return pa + delta, pb - delta


def live_state_probs(pa: float, pb: float, sets_a: int = 0, sets_b: int = 0,
                     games_a: int = 0, games_b: int = 0, server: int = 0,
                     best_of: int = 3, n_sims: int = 20_000,
                     seed: int = SEED) -> dict:
    """Win probabilities from a LIVE position — sets AND games in the current set.

    Answers the questions a live ticket actually rides on: who wins the match,
    who wins the set in progress, and does each player win at least one set
    (the "gana un set" market). Everything is simulated forward from the real
    score rather than adjusted off a pre-match number.

    Before simulating, `pa`/`pb` are shrunk toward what the sets already
    decided imply (`_shrink_toward_sets_played`) — otherwise a player up
    2 sets to 1 gets simulated at their SEASON level for everything not yet
    decided, blind to the fact they're clearly playing above it today.
    """
    need = best_of // 2 + 1
    if max(sets_a, sets_b) >= need:
        decided = 1.0 if sets_a >= need else 0.0
        return {"match_prob_a": decided, "set_in_progress_prob_a": None,
                "a_wins_a_set": 1.0 if sets_a >= 1 else 0.0,
                "b_wins_a_set": 1.0 if sets_b >= 1 else 0.0,
                "decided": True, "n_sims": 0}

    pa, pb = _shrink_toward_sets_played(pa, pb, sets_a, sets_b)
    rng = random.Random(seed)
    wins_a = cur_set_a = at_least_a = at_least_b = 0
    for _ in range(n_sims):
        sa, sb = sets_a, sets_b
        w, _ga, _gb, nxt = _sim_set_from(pa, pb, rng, server, games_a, games_b)
        if w == 0:
            sa += 1
            cur_set_a += 1
        else:
            sb += 1
        srv = nxt
        while sa < need and sb < need:
            w2, _x, _y, srv = _sim_set(pa, pb, rng, srv)
            if w2 == 0:
                sa += 1
            else:
                sb += 1
        if sa >= need:
            wins_a += 1
        if sa >= 1:
            at_least_a += 1
        if sb >= 1:
            at_least_b += 1
    return {
        "match_prob_a": round(wins_a / n_sims, 4),
        "set_in_progress_prob_a": round(cur_set_a / n_sims, 4),
        "a_wins_a_set": round(at_least_a / n_sims, 4),
        "b_wins_a_set": round(at_least_b / n_sims, 4),
        "from_score": {"sets": [sets_a, sets_b], "games": [games_a, games_b],
                       "serving": "a" if server == 0 else "b"},
        "decided": False, "n_sims": n_sims,
        "note": "simulated forward from the live score using measured hold "
                "probabilities; point score within the current game is ignored",
    }


def simulate_match(pa: float, pb: float, best_of: int = 3,
                   n_sims: int = N_SIMS, seed: int = SEED) -> dict:
    """Distributions of winner, total games, and A-minus-B games margin."""
    rng = random.Random(seed)
    need = best_of // 2 + 1
    wins_a = 0
    set1_a = 0
    totals: list[int] = []
    margins: list[int] = []
    set1_games: list[int] = []
    set_scores: dict[tuple, int] = {}
    for _ in range(n_sims):
        sets = [0, 0]
        games = [0, 0]
        server = rng.randint(0, 1)       # toss unknown pre-match — randomized
        first_set = True
        while max(sets) < need:
            w, ga, gb, server = _sim_set(pa, pb, rng, server)
            sets[w] += 1
            games[0] += ga
            games[1] += gb
            if first_set:
                set1_a += 1 - w
                set1_games.append(ga + gb)
                first_set = False
        totals.append(games[0] + games[1])
        margins.append(games[0] - games[1])
        key = tuple(sets)
        set_scores[key] = set_scores.get(key, 0) + 1
        if sets[0] == need:
            wins_a += 1
    return {"match_prob_a": wins_a / n_sims, "totals": totals, "margins": margins,
            "set1_prob_a": set1_a / n_sims, "set1_games": set1_games,
            "set_scores": set_scores}


def set_handicap(sims: dict, best_of: int = 3) -> dict:
    """SET handicap — a market that is NOT the games handicap and gets confused
    with it constantly (2026-08-19: a real ticket was built on "-1.5 Handicap de
    Set" priced as if it were -1.5 GAMES; the two differ by ~25 points of win
    probability, 58.7% vs 82.2% for the same player).

    In a best-of-3, **-1.5 sets means winning 2-0** — a 2-1 win LOSES the bet
    even though the player won the match. That is the whole trap.
    """
    sc = sims.get("set_scores") or {}
    total = sum(sc.values()) or 1
    need = best_of // 2 + 1
    straight_a = sc.get((need, 0), 0) / total
    straight_b = sc.get((0, need), 0) / total
    match_a = sum(v for k, v in sc.items() if k[0] == need) / total
    return {
        "a_minus_1_5_sets": round(straight_a, 4),
        "b_minus_1_5_sets": round(straight_b, 4),
        # The gap between "wins the match" and "wins the bet".
        "a_wins_match_but_loses_handicap": round(match_a - straight_a, 4),
        "note": (f"-1.5 SETS requires a {need}-0 win; a {need}-{need-1} victory "
                 f"LOSES this bet. Do not confuse with the GAMES handicap."),
    }


CALIB_PATH = DATA.parent / "tennis_totals_calibration.json"
_CALIB: dict | None = None


def totals_offset(tour: str | None) -> float:
    """Measured games-total correction for a tour (0.0 when never fitted).

    The raw simulation runs LONG: across 3,172 best-of-3 matches (ATP+WTA,
    2025-26) it expected 1.7-2.2 MORE games than were played, and the error is
    FLAT across match imbalance — a level bias, not a missing opponent
    adjustment. Fit and refreshed by
    `tennis_totals_backtest.py --fit`; absent file = no correction, never a
    guessed number.
    """
    global _CALIB
    if _CALIB is None:
        try:
            _CALIB = json.loads(CALIB_PATH.read_text())
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            _CALIB = {"tours": {}}
    rec = (_CALIB.get("tours") or {}).get((tour or "").lower())
    return float(rec.get("offset_games", 0.0)) if rec else 0.0


MARGIN_CALIB_PATH = DATA.parent / "tennis_margin_calibration.json"
_MCAL: dict | None = None


def _margin_cal() -> dict:
    global _MCAL
    if _MCAL is None:
        try:
            _MCAL = json.loads(MARGIN_CALIB_PATH.read_text())
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            _MCAL = {}
    return _MCAL


def margin_scale() -> float:
    """Measured widening of the games-margin distribution (1.0 = raw simulation).

    The point-by-point sim treats every point as independent, so it underprices
    lopsided matches: on 365 real matches (tennis_markets_backtest) P(margin >
    3.5/4.5/5.5 games) came out 4-6 pts too LOW, which inflates every underdog
    +handicap cover probability. Fit out-of-sample on closing prices by
    `tennis_price_backtest.py`; absent file = no correction, never a guess.
    """
    return float(_margin_cal().get("margin_scale", 1.0))


def scale_margins(margins: list) -> list:
    k = margin_scale()
    return margins if k == 1.0 else [int(round(m * k)) for m in margins]


def shape_totals(totals: list) -> list:
    """Residual totals correction (shift + spread about the mean), fitted on the
    same held-out price test; identity when never fitted."""
    c = _margin_cal()
    shift, spread = float(c.get("totals_shift", 0.0)), float(c.get("totals_spread", 1.0))
    if shift == 0.0 and spread == 1.0:
        return totals
    mean = sum(totals) / len(totals)
    return [mean + (t - mean) * spread + shift for t in totals]


# ── Engine v2 path (hierarchical day-to-day serve-rate sd + Numba kernel) ─────────────────────────────────────
# Replaces the iid sim + the 1.26 margin multiplier + the +1.7/+2.2-game totals offset for best-of-3 when
# data/engine_v2_calibration.json exists (see docs/ENGINE_V2.md). Falls back to the old path otherwise.
V2_CAL_PATH = DATA.parent / "engine_v2_calibration.json"
try:
    _V2 = json.loads(V2_CAL_PATH.read_text())
except (FileNotFoundError, OSError, json.JSONDecodeError):
    _V2 = {}
try:
    import tennis_vec as _tv
except Exception:                                    # numba/numpy missing -> old path
    _tv = None
V2_ENABLED = bool(_V2 and _tv is not None)


def _v2_sim(pa: float, pb: float, na: float, nb: float, target: float | None, n: int = 40000, seed: int = 11) -> tuple[dict, float]:
    """(sim dict in the old schema, level delta). Per-player sd = sqrt(day_sd^2 + se^2): thin serve samples get fatter tails."""
    day = float(_V2.get("day_sd", 0.05))
    se = lambda p, m: (max(p * (1 - p), 1e-6) / max(m * 60.0, 60.0)) ** 0.5
    sd = ((day ** 2 + se(pa, na) ** 2) ** 0.5, (day ** 2 + se(pb, nb) ** 2) ** 0.5)
    delta = _tv.calibrate(pa, pb, target, sd) if target is not None else 0.0
    sim_fn = getattr(_tv, "simulate_nb", _tv.simulate)
    r = sim_fn(pa + delta, pb - delta, n, sd, seed)
    import collections
    sc = collections.Counter(zip(r["sets"][:, 0].tolist(), r["sets"][:, 1].tolist()))
    return ({"match_prob_a": float((r["winner"] == 0).mean()), "totals": r["total"].tolist(), "margins": r["margin"].tolist(),
             "set1_prob_a": float((r["s1w"] == 0).mean()), "set1_games": r["s1g"].tolist(), "set_scores": dict(sc)}, float(delta))


def predict(player_a: str, player_b: str, games_line: float | None = None,
            handicap_a: float | None = None, best_of: int = 3,
            target_match_prob_a: float | None = None) -> dict:
    doc = load()
    if doc is None:
        return {"error": "NO_DATA",
                "note": "tennis_serve.json missing — run fetch_tennis_serve_stats.py"}
    players = doc.get("players") or {}
    ka, kb = player_key(player_a, players), player_key(player_b, players)
    if not ka or not kb:
        missing = [n for n, k in ((player_a, ka), (player_b, kb)) if not k]
        return {"error": "NO_DATA", "missing_players": missing,
                "note": "no serve stats for player(s) — no data, not estimating"}

    pa, pb = point_prob(players[ka]), point_prob(players[kb])
    tour = (players[ka].get("tour") or players[kb].get("tour") or "")
    v2 = V2_ENABLED and best_of == 3                   # bo5 tails/offsets were never fitted: keep the old path there
    if v2:
        sim, delta = _v2_sim(pa, pb, float(players[ka].get("n", 30)), float(players[kb].get("n", 30)), target_match_prob_a)
        off = float((_V2.get("totals_offset") or {}).get((tour or "ATP").upper(), 0.0))
        totals = [t + off for t in sim["totals"]]
    else:
        delta = 0.0
        if target_match_prob_a is not None:
            # calibrate LEVEL to the ratings model: common shift, bisected on match prob
            lo, hi = -0.08, 0.08
            for _ in range(18):
                delta = (lo + hi) / 2
                mp = simulate_match(pa + delta, pb - delta, best_of,
                                    n_sims=2000, seed=SEED)["match_prob_a"]
                if mp < target_match_prob_a:
                    lo = delta
                else:
                    hi = delta
            delta = (lo + hi) / 2

        sim = simulate_match(pa + delta, pb - delta, best_of)
        # Apply the measured level correction before ANY total is read off the
        # simulation, so expected_total_games and the over/under probabilities move
        # together. Both players' tours agree in practice; take player A's.
        off = totals_offset(tour)
        totals = [t + off for t in sim["totals"]] if off else sim["totals"]
        totals = shape_totals(totals)
    n = len(totals)
    out: dict = {
        "player_a": ka, "player_b": kb, "best_of": best_of,
        "serve_point_prob": {ka: round(pa, 4), kb: round(pb, 4)},
        "hold_prob": {ka: round(hold_prob(round(pa + delta, 4)), 4),
                      kb: round(hold_prob(round(pb - delta, 4)), 4)},
        "match_prob": {ka: round(sim["match_prob_a"], 4),
                       kb: round(1 - sim["match_prob_a"], 4)},
        "expected_total_games": round(sum(totals) / n, 2),
        "totals_calibration": {"tour": tour or None, "offset_games": off,
                               "source": "engine_v2 (hierarchical sd)" if v2 else "tennis_totals_backtest --fit"},
        "engine": "v2" if v2 else "legacy",
        # ── Set 1 ("period") markets — WTA/ATP, from the same game-level sim ──
        "set1": {
            "winner": {ka: round(sim["set1_prob_a"], 4),
                       kb: round(1 - sim["set1_prob_a"], 4)},
            "expected_games": round(sum(sim["set1_games"]) / n, 2),
            "games_over_9_5": round(sum(1 for g in sim["set1_games"] if g > 9.5) / n, 4),
            "games_under_9_5": round(sum(1 for g in sim["set1_games"] if g < 9.5) / n, 4),
        },
        "calibration_delta": round(delta, 4),
        "n_sims": n,
        "note": "serve stats are vs tour-average returners (no per-opponent "
                "return adjustment)" + ("" if target_match_prob_a is None else
                                        "; level calibrated to supplied match prob"),
        "source": f"tennis_serve.json built {doc.get('built')}",
    }
    if games_line is None:
        # no line supplied -> price the half-line nearest the sim's own mean,
        # so every report carries a bettable games market by default
        games_line = int(sum(totals) / n) + 0.5
    over = sum(1 for t in totals if t > games_line)
    push = sum(1 for t in totals if t == games_line)
    out["games_total"] = {"line": games_line,
                          "p_over": round(over / n, 4),
                          "p_under": round((n - over - push) / n, 4),
                          "p_push": round(push / n, 4)}
    if handicap_a is not None:
        margins = sim["margins"] if v2 else scale_margins(sim["margins"])
        cover = sum(1 for m in margins if m + handicap_a > 0)
        push = sum(1 for m in margins if m + handicap_a == 0)
        out["game_handicap"] = {f"{ka} {handicap_a:+g}": round(cover / n, 4),
                                "p_push": round(push / n, 4)}
    # ALWAYS emit the SET handicap, whether or not a games handicap was asked
    # for. A real ticket (2026-08-19) was built on "-1.5 Handicap de Set" priced
    # as if it were -1.5 GAMES — 58.7% vs 82.2% for the same player. The two
    # markets sit next to each other on the book and read almost identically,
    # so the only safe design is to show both, always, and name the difference.
    out["set_handicap"] = set_handicap(sim, best_of)
    # Games handicap across the lines books actually post, so a caller never has
    # to guess a line or reach for the raw margin distribution.
    margins = sim["margins"] if v2 else scale_margins(sim["margins"])
    out["game_handicap_ladder"] = {
        f"{line:+g}": round(sum(1 for m in margins if m + line > 0) / len(margins), 4)
        for line in (-6.5, -5.5, -4.5, -3.5, -2.5, -1.5)
    }
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: tennis_games_model.py <player_a> <player_b> [games_line]")
        raise SystemExit(2)
    line = float(sys.argv[3]) if len(sys.argv) > 3 else None
    print(json.dumps(predict(sys.argv[1], sys.argv[2], line), indent=1,
                     ensure_ascii=False))

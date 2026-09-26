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
        if sets[0] == need:
            wins_a += 1
    return {"match_prob_a": wins_a / n_sims, "totals": totals, "margins": margins,
            "set1_prob_a": set1_a / n_sims, "set1_games": set1_games}


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
    totals = sim["totals"]
    n = len(totals)
    out: dict = {
        "player_a": ka, "player_b": kb, "best_of": best_of,
        "serve_point_prob": {ka: round(pa, 4), kb: round(pb, 4)},
        "hold_prob": {ka: round(hold_prob(round(pa + delta, 4)), 4),
                      kb: round(hold_prob(round(pb - delta, 4)), 4)},
        "match_prob": {ka: round(sim["match_prob_a"], 4),
                       kb: round(1 - sim["match_prob_a"], 4)},
        "expected_total_games": round(sum(totals) / n, 2),
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
        margins = sim["margins"]
        cover = sum(1 for m in margins if m + handicap_a > 0)
        push = sum(1 for m in margins if m + handicap_a == 0)
        out["game_handicap"] = {f"{ka} {handicap_a:+g}": round(cover / n, 4),
                                "p_push": round(push / n, 4)}
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: tennis_games_model.py <player_a> <player_b> [games_line]")
        raise SystemExit(2)
    line = float(sys.argv[3]) if len(sys.argv) > 3 else None
    print(json.dumps(predict(sys.argv[1], sys.argv[2], line), indent=1,
                     ensure_ascii=False))

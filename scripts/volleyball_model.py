#!/usr/bin/env python3
"""
volleyball_model.py — win/set-handicap probabilities from FIVB ratings. Pure math,
no network: reads data/volleyball_ratings.json written by fetch_volleyball_rankings.py.

Every probability traces to the fitted logistic (k_match / k_set were MLE-fitted on
real FIVB results — see that file's meta). Unknown team or missing ratings file →
explicit refusal dict, never an estimate ("no data, not estimating").

Match format is FIVB best-of-5. From the fitted per-set prob p:
  P(3-0)=p^3, P(3-1)=3p^3(1-p), P(3-2)=6p^3(1-p)^2  (and mirrored for the loser)
which prices set handicaps (-1.5 / -2.5) and correct set score, all from data.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "volleyball_ratings.json"

ALIASES = {
    "usa": "USA", "united states": "USA", "turkey": "Türkiye", "turkiye": "Türkiye",
    "iran": "Iran", "czechia": "Czechia", "czech republic": "Czechia",
    "dominican rep": "Dominican Republic", "korea": "South Korea",
}


def load() -> dict | None:
    try:
        return json.loads(DATA.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _team_key(name: str, table: dict) -> str | None:
    if name in table:
        return name
    nl = name.strip().lower()
    alias = ALIASES.get(nl)
    if alias and alias in table:
        return alias
    for t in table:
        if t.lower() == nl:
            return t
    for t in table:                      # substring either way, ≥4 chars to be safe
        if len(nl) >= 4 and (nl in t.lower() or t.lower() in nl):
            return t
    return None


def _logistic(diff: float, k: float) -> float:
    return 1.0 / (1.0 + math.exp(-k * diff))


def best_of_5(p_set: float) -> dict:
    """Set-score distribution for the p_set side in a best-of-5."""
    p, q = p_set, 1.0 - p_set
    return {
        "3-0": p ** 3, "3-1": 3 * p ** 3 * q, "3-2": 6 * p ** 3 * q ** 2,
        "2-3": 6 * q ** 3 * p ** 2, "1-3": 3 * q ** 3 * p, "0-3": q ** 3,
    }


def predict(team_a: str, team_b: str, gender: str = "men") -> dict:
    """Win prob + set markets for team_a vs team_b. Refuses without real ratings."""
    doc = load()
    if doc is None:
        return {"error": "NO_DATA",
                "note": "volleyball_ratings.json missing — run fetch_volleyball_rankings.py"}
    table = doc.get(gender.lower()) or {}
    meta = doc.get("meta") or {}
    ka, kb = _team_key(team_a, table), _team_key(team_b, table)
    if not ka or not kb:
        missing = [n for n, k in ((team_a, ka), (team_b, kb)) if not k]
        return {"error": "NO_DATA", "gender": gender, "missing_teams": missing,
                "note": "team(s) not in FIVB top-50 — no rating, not estimating"}

    diff = float(table[ka]["points"]) - float(table[kb]["points"])
    p_match = _logistic(diff, float(meta["k_match"]))
    p_set = _logistic(diff, float(meta["k_set"]))
    dist = best_of_5(p_set)
    return {
        "gender": gender, "team_a": ka, "team_b": kb,
        "wr_points": {ka: table[ka]["points"], kb: table[kb]["points"]},
        "wr_rank": {ka: table[ka]["rank"], kb: table[kb]["rank"]},
        "match_win_prob": {ka: round(p_match, 4), kb: round(1 - p_match, 4)},
        "set_win_prob": {ka: round(p_set, 4), kb: round(1 - p_set, 4)},
        "set_score_probs": {k: round(v, 4) for k, v in dist.items()},
        "set_handicap": {
            f"{ka} -1.5": round(dist["3-0"] + dist["3-1"], 4),
            f"{kb} +1.5": round(1 - dist["3-0"] - dist["3-1"], 4),
            f"{kb} -1.5": round(dist["0-3"] + dist["1-3"], 4),
            f"{ka} +1.5": round(1 - dist["0-3"] - dist["1-3"], 4),
        },
        "calibration": {
            "k_match": meta.get("k_match"), "k_set": meta.get("k_set"),
            "n_matches_fit": meta.get("n_matches_fit"),
            "favorite_accuracy": meta.get("favorite_accuracy"),
            "source": meta.get("source"), "fetched_at": meta.get("fetched_at"),
        },
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: volleyball_model.py <team_a> <team_b> [men|women]")
        raise SystemExit(2)
    g = sys.argv[3] if len(sys.argv) > 3 else "men"
    print(json.dumps(predict(sys.argv[1], sys.argv[2], g), indent=1, ensure_ascii=False))

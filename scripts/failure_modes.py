#!/usr/bin/env python3
"""
failure_modes.py — the "how it could go wrong" layer for every pick.

Born from a real loss: a UFC parlay where every leg hit except McGregor's
fight, scratched by injury before it started. The model was right about the
fight and wrong about the fight EXISTING. Three risk classes, kept separate
so quantified never mixes with guessed:

  1. match_kill_paths — model-quantified ways a market pick loses, priced
     straight off the same Dixon-Coles matrix as the pick itself.
  2. availability    — data-backed appearance risk for player props
     (appearances / team games, from the real cache — no minutes feed).
  3. unmodelled      — fixed per-sport taxonomy of hazards the model CANNOT
     price (late scratch, referee, VAR...). Flags carry a mitigation, never
     a probability — inventing one would be worse than none.
"""
from __future__ import annotations

# appearance-rate thresholds (share of team games the player appeared in)
AVAIL_LOW_RISK = 0.85
AVAIL_MED_RISK = 0.70


def match_kill_paths(matrix: list[list[float]], market: str) -> dict:
    """Top ways a soccer market pick loses, with probs from the score matrix."""
    p = {"home": 0.0, "draw": 0.0, "away": 0.0}
    goal_tot: dict[int, float] = {}
    btts = 0.0
    for i, row in enumerate(matrix):
        for j, cell in enumerate(row):
            key = "home" if i > j else ("draw" if i == j else "away")
            p[key] += cell
            goal_tot[i + j] = goal_tot.get(i + j, 0.0) + cell
            if i > 0 and j > 0:
                btts += cell

    over = lambda line: sum(v for k, v in goal_tot.items() if k > line)
    kills: list[dict]
    if market == "ml_home":
        pick = p["home"]
        kills = [{"event": "draw", "prob": p["draw"]},
                 {"event": "opponent wins", "prob": p["away"]}]
    elif market == "ml_away":
        pick = p["away"]
        kills = [{"event": "draw", "prob": p["draw"]},
                 {"event": "opponent wins", "prob": p["home"]}]
    elif market == "under_2_5":
        pick = 1 - over(2.5)
        kills = [{"event": "exactly 3 goals", "prob": goal_tot.get(3, 0.0)},
                 {"event": "4+ goals", "prob": over(3.5)}]
    elif market == "over_2_5":
        pick = over(2.5)
        kills = [{"event": "exactly 2 goals", "prob": goal_tot.get(2, 0.0)},
                 {"event": "0-1 goals", "prob": goal_tot.get(0, 0.0) + goal_tot.get(1, 0.0)}]
    elif market == "btts_no":
        pick = 1 - btts
        kills = [{"event": "both teams score", "prob": btts}]
    elif market == "btts_yes":
        pick = btts
        kills = [{"event": "at least one side blanks", "prob": 1 - btts}]
    elif market == "dc_1x":
        pick = p["home"] + p["draw"]
        kills = [{"event": "opponent wins", "prob": p["away"]}]
    elif market == "dc_x2":
        pick = p["away"] + p["draw"]
        kills = [{"event": "opponent wins", "prob": p["home"]}]
    else:
        return {"pick_prob": None, "kill_paths": [],
                "note": f"'{market}' not modelled for kill paths"}

    kills = [{"event": k["event"], "prob": round(k["prob"], 4)}
             for k in sorted(kills, key=lambda x: -x["prob"])]
    return {"pick_prob": round(pick, 4), "kill_paths": kills,
            "basis": "dixon_coles_matrix"}


def availability(appearances: int, team_games: int) -> dict:
    """Appearance risk for a player prop — real cache counts, no estimates."""
    if team_games <= 0:
        return {"appearance_rate": None, "missed": None, "risk": "NO_DATA",
                "note": "no team games in cache — cannot rate availability"}
    rate = appearances / team_games
    risk = ("LOW" if rate >= AVAIL_LOW_RISK
            else "MEDIUM" if rate >= AVAIL_MED_RISK else "HIGH")
    return {"appearance_rate": round(rate, 3),
            "missed": team_games - appearances, "risk": risk,
            "basis": f"{appearances}/{team_games} team games appeared in"}


# Fixed taxonomy — hazards the model cannot price. A flag NEVER carries a
# probability: quantified risk lives in match_kill_paths/availability only.
_GENERIC = [
    {"risk": "Late scratch / withdrawal voids or flips the leg",
     "mitigation": "know the book's void rule BEFORE betting; recheck slate 1h out"},
    {"risk": "Market settles on different window than assumed (90' vs incl. extra time)",
     "mitigation": "read the market name letter by letter — 'incl. prórroga' changes the maths"},
]
_UNMODELLED: dict[str, list[dict]] = {
    "soccer": [
        {"risk": "Benching / late lineup change kills player props",
         "mitigation": "no prop bets before the confirmed XI (T-60min)"},
        {"risk": "Early red card flips every market's game script",
         "mitigation": "none pre-match — accept as residual risk"},
        {"risk": "Referee variance drives card markets more than team behavior",
         "mitigation": "treat card-market edges as half-trust until referee is modelled"},
        {"risk": "VAR overturns goals — first-goal/scorer promos can swing on review",
         "mitigation": "accept — but never stack multiple VAR-sensitive legs"},
        {"risk": "Extra time NOT counted in 90' markets but counted in others",
         "mitigation": "check settlement window per market, per book"},
    ],
    "ufc": [
        {"risk": "Late injury withdrawal — fight scratched or replaced on short notice "
                 "(the McGregor lesson: a perfect parlay dies on a fight that never happens)",
         "mitigation": "check the book's rule: void vs stands-vs-replacement; "
                       "never anchor a parlay on a fight >2 weeks out or on a "
                       "fighter with a pullout history"},
        {"risk": "Missed weight changes finishing dynamics and can void props",
         "mitigation": "recheck after weigh-ins, day before"},
        {"risk": "Short-notice replacement resets the whole fight model",
         "mitigation": "re-run /predict-ufc vs the replacement — old edge is void"},
    ],
    "tennis": [
        {"risk": "Mid-match retirement — books settle differently (1-set rule vs void)",
         "mitigation": "know the book's retirement rule; avoid players with recent injury retirements"},
        {"risk": "Walkover before the match (usually void, kills parlay maths)",
         "mitigation": "don't anchor multi-leg tickets on early-round matches"},
        {"risk": "Schedule tank — small event with a big event <5 days away",
         "mitigation": "fade per house rule; check the calendar before backing favourites"},
    ],
    "nba": [
        {"risk": "Late scratch / rest decision (news can land minutes before tip)",
         "mitigation": "bet props after injury report confirmation only"},
        {"risk": "Blowout benches starters in Q4 — unders/overs on minutes-sensitive props",
         "mitigation": "avoid star props in projected 10+ point spreads"},
    ],
    "nfl": [
        {"risk": "Inactive list surprises 90 min before kickoff",
         "mitigation": "no player props before inactives are posted"},
        {"risk": "Weather (wind kills passing volume and totals)",
         "mitigation": "check forecast for outdoor venues before totals/passing props"},
    ],
}


def unmodelled(sport: str) -> list[dict]:
    """Per-sport hazard flags the model cannot quantify. Generic set always
    applies; sport-specific flags prepend it."""
    return _UNMODELLED.get(sport.lower(), []) + _GENERIC

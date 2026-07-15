#!/usr/bin/env python3
"""
narrative.py — the omens ledger. Verified coincidences in and around the
sport (squad echoes, anthem singers, anniversary years...), curated by hand
with sources, surfaced on every report.

Hard rules, enforced by tests:
  * Every omen carries at least one source and a verified date — an
    unsourced omen never enters the ledger.
  * Omens are a TIE-BREAKER factor only: they may lean a call the model
    already scores as a coin flip; they never move a probability and never
    flip a BET/LEAN/NO_BET verdict. The lean is a count, not a weight.
"""
from __future__ import annotations

import json
from pathlib import Path

LEDGER = Path(__file__).parent.parent / "data" / "narrative_omens.json"


def load_ledger(path: Path = LEDGER) -> dict:
    with open(path) as f:
        return json.load(f)


def omens_for(home: str, away: str, ledger: dict | None = None,
              sport: str | None = None) -> dict:
    """All ledger omens touching either side + a net lean. Works for every
    sport — 'teams' holds team names for team sports, player/fighter names
    for tennis and UFC. Matching is case-insensitive.

    favors == side name  -> +1 for that side
    favors == "opponent" -> +1 for whichever of home/away it plays against
    favors == "none"     -> listed, counts for nobody
    """
    ledger = ledger or load_ledger()
    fold = lambda s: str(s).casefold()
    sides = {fold(home): home, fold(away): away}
    entries, lean = [], {home: 0, away: 0}
    for o in ledger.get("omens", []):
        if sport and o.get("sport") and fold(o["sport"]) != fold(sport):
            continue
        onames = {fold(t) for t in o.get("teams", [])}
        hit = onames & set(sides)
        if not hit:
            continue
        entries.append(o)
        fav = fold(o.get("favors", ""))
        if fav in sides:
            lean[sides[fav]] += 1
        elif fav == "opponent":
            for key, orig in sides.items():
                if key not in hit:
                    lean[orig] += 1
    tilt = ("balanced" if lean[home] == lean[away]
            else home if lean[home] > lean[away] else away)
    return {"entries": entries, "lean": lean, "tilt": tilt,
            "rule": ledger.get("rule", "")}

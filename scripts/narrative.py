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


def omens_for(home: str, away: str, ledger: dict | None = None) -> dict:
    """All ledger omens touching either team + a net lean per side.

    favors == team name  -> +1 for that side
    favors == "opponent" -> +1 for whichever of home/away it plays against
    favors == "none"     -> listed, counts for nobody
    """
    ledger = ledger or load_ledger()
    sides = {home, away}
    entries, lean = [], {home: 0, away: 0}
    for o in ledger.get("omens", []):
        if not sides & set(o.get("teams", [])):
            continue
        entries.append(o)
        fav = o.get("favors")
        if fav in lean:
            lean[fav] += 1
        elif fav == "opponent":
            against = set(o.get("teams", [])) & sides
            for team in sides - against:
                lean[team] += 1
    tilt = ("balanced" if lean[home] == lean[away]
            else home if lean[home] > lean[away] else away)
    return {"entries": entries, "lean": lean, "tilt": tilt,
            "rule": ledger.get("rule", "")}

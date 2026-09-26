#!/usr/bin/env python3
"""
narrative.py — the omens ledger. Two species, both verified and curated by
hand with sources, surfaced on every report:

  * type "coincidence" — echoes and signs (squad numerology, anthem singers,
    anniversary years). May favor a SIDE.
  * type "cultural"    — rivalry/context that historically expresses itself
    in a MARKET (Malvinas-charged England-Argentina -> cards/fouls). Carries
    a market_signal {market, lean} instead of favoring a side.

Hard rules, enforced by tests:
  * Every omen carries at least one source and a verified date — an
    unsourced omen never enters the ledger.
  * Omens are a TIE-BREAKER / ATTENTION factor only: a coincidence may lean
    a call the model already scores as a coin flip; a cultural market_signal
    raises attention on a market the model prices without a referee/context
    feed. Neither ever moves a probability or flips a BET/LEAN/NO_BET
    verdict. The lean is a count, not a weight.
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
    market_signals = [
        {"market": o["market_signal"]["market"],
         "lean": o["market_signal"]["lean"], "omen_id": o["id"]}
        for o in entries
        if o.get("type") == "cultural" and o.get("market_signal")
    ]
    return {"entries": entries, "lean": lean, "tilt": tilt,
            "market_signals": market_signals,
            "rule": ledger.get("rule", "")}

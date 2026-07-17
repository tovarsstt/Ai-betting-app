#!/usr/bin/env python3
"""
cricket_model.py — ICC ratings + fitted win probability for a cricket match.
Pure local read of data/cricket_ratings.json (fetch_cricket_rankings.py).

Probabilities are emitted ONLY for formats whose logistic scale was MLE-fitted
on real results (cricsheet-derived matches CSV — see the fetcher); a format
without a fit gets ratings context and "probability": null with the reason.
Test-format probs are P(win | a result): draws/no-results are excluded from
the fit and their measured rate ships alongside so the number can't be misread.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

DATA = Path(__file__).parent.parent / "data" / "cricket_ratings.json"
FORMATS = ("t20i", "odi", "test")
ALIASES = {"uae": "United Arab Emirates", "usa": "United States", "windies": "West Indies"}


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
    for t in table:
        if len(nl) >= 4 and (nl in t.lower() or t.lower() in nl):
            return t
    return None


def compare(team_a: str, team_b: str, fmt: str = "t20i") -> dict:
    doc = load()
    if doc is None:
        return {"error": "NO_DATA",
                "note": "cricket_ratings.json missing — run fetch_cricket_rankings.py"}
    fmt = fmt.lower()
    if fmt not in FORMATS:
        return {"error": "BAD_FORMAT", "note": f"format must be one of {FORMATS}"}
    table = doc.get(fmt) or {}
    ka, kb = _team_key(team_a, table), _team_key(team_b, table)
    if not ka or not kb:
        missing = [n for n, k in ((team_a, ka), (team_b, kb)) if not k]
        return {"error": "NO_DATA", "format": fmt, "missing_teams": missing,
                "note": "team(s) not in ICC rankings — no data, not estimating"}

    a, b = table[ka], table[kb]
    gap = a["rating"] - b["rating"]
    meta = doc.get("meta") or {}
    out = {
        "format": fmt, "team_a": ka, "team_b": kb,
        "icc_rating": {ka: a["rating"], kb: b["rating"]},
        "icc_rank": {ka: a["rank"], kb: b["rank"]},
        "rating_gap": gap,
        "edge_lean": ka if gap > 0 else (kb if gap < 0 else "even"),
        "probability": None,
        "source": meta.get("source"),
        "icc_table_date": (meta.get("source_dates") or {}).get(fmt),
    }
    fit = (meta.get("fits") or {}).get(fmt)
    if fit:
        p = 1.0 / (1.0 + math.exp(-float(fit["k"]) * gap))
        out["probability"] = {ka: round(p, 4), kb: round(1 - p, 4)}
        out["probability_is"] = "P(win | a result) — draws/no-results excluded"
        out["calibration"] = {**fit, "method": "logistic on ICC rating gap, "
                              "MLE-fitted on real results"}
    else:
        out["why_no_probability"] = ("no results fit for this format — refusing to "
                                     "invent one (house rule: no data, no number)")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: cricket_model.py <team_a> <team_b> [t20i|odi|test]")
        raise SystemExit(2)
    f = sys.argv[3] if len(sys.argv) > 3 else "t20i"
    print(json.dumps(compare(sys.argv[1], sys.argv[2], f), indent=1, ensure_ascii=False))

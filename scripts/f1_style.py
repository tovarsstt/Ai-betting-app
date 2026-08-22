#!/usr/bin/env python3
"""
f1_style.py — measured F1 context: reliability, circuits, and teammate form.

Soccer got style and referees, tennis got surface and nerve, the period sports
got pace. F1's niche stats are different again, and two of them decide most F1
bets outright:

  RELIABILITY   a driver's DNF rate. In no other sport does the favourite fail
                to finish at all this often, and a DNF voids a podium, points or
                head-to-head bet regardless of pace. This is THE F1 kill path
                (rule 27) and it is countable, so it is counted.
  CIRCUIT       positions gained or lost from the grid, per circuit. Overtaking
                difficulty is a property of the track, not an opinion: on some
                circuits the grid IS the result, which makes qualifying the real
                market and any "he'll come through the field" bet a losing one.
                Also the circuit's own DNF rate — street tracks bite.
  GRID CONVERT  how often a driver converts a front-row or top-5 start into a
                win/podium, and their average positions gained.
  TEAMMATE H2H  the fairest comparison in the sport, because it is the only one
                that holds the car constant — and a listed betting market.

Counted from `data/f1_results.json` (jolpica, the free Ergast successor).

Description, not prediction. Nothing here invents a win probability.

Run: python3 scripts/f1_style.py --driver verstappen
     python3 scripts/f1_style.py --circuit monaco
     python3 scripts/f1_style.py --teammates red_bull
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent.parent / "data"
RESULTS = DATA / "f1_results.json"
MIN_RACES = 8
MIN_CIRCUIT = 3
_CACHE: Optional[list] = None


def load() -> list[dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        _CACHE = json.loads(RESULTS.read_text()).get("results", [])
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        _CACHE = []
    return _CACHE


def resolve_driver(name: str, rows: Optional[list[dict]] = None) -> Optional[str]:
    """Map what a person types to the driverId the feed uses.

    Ids are not always the surname — Verstappen is `max_verstappen`, so a plain
    surname lookup silently returns nothing. Name resolution has failed quietly
    in this project before; it refuses ambiguity instead of guessing.
    """
    rows = rows if rows is not None else load()
    q = name.strip().lower().replace(" ", "_")
    ids = {r["driver"] for r in rows}
    if q in ids:
        return q
    surname = q.split("_")[-1]
    hits = {i for i in ids if i == surname or i.endswith("_" + surname)}
    if len(hits) == 1:
        return hits.pop()
    # Fall back to the family name carried on each row.
    named = {r["driver"] for r in rows
             if (r.get("driver_name") or "").lower() == name.strip().lower()}
    if len(named) == 1:
        return named.pop()
    return None                      # unknown, or two drivers share the surname


def driver(name: str, rows: Optional[list[dict]] = None) -> Optional[dict]:
    rows = rows if rows is not None else load()
    did = resolve_driver(name, rows)
    if not did:
        return None
    rs = [r for r in rows if r["driver"] == did]
    if len(rs) < MIN_RACES:
        return None
    fin = [r for r in rs if r["finished"]]
    # Grid 0 means a pit-lane start; it is not a grid slot and would poison the
    # positions-gained average.
    moved = [r["grid"] - r["position"] for r in fin if r["grid"] > 0 and r["position"] > 0]
    front = [r for r in rs if 0 < r["grid"] <= 5]
    return {
        "driver": did,
        "queried_as": name,
        "races": len(rs),
        "seasons": sorted({r["year"] for r in rs}),
        "reliability": {
            "dnf_rate": round(1 - len(fin) / len(rs), 3),
            "dnfs": len(rs) - len(fin),
            "note": "a DNF voids a podium/points/H2H bet no matter the pace — "
                    "the F1 kill path, counted not assumed",
        },
        "race_craft": {
            "avg_positions_gained": round(statistics.fmean(moved), 2) if moved else None,
            "n": len(moved),
            "note": "grid minus finish, finishers only; pit-lane starts excluded",
        },
        "results": {
            "wins": sum(1 for r in rs if r["position"] == 1),
            "podiums": sum(1 for r in rs if 0 < r["position"] <= 3),
            "points_finishes": sum(1 for r in rs if r["points"] > 0),
            "avg_finish": round(statistics.fmean([r["position"] for r in fin]), 2) if fin else None,
            "avg_grid": round(statistics.fmean([r["grid"] for r in rs if r["grid"] > 0]), 2),
        },
        "from_top5_grid": ({"n": len(front),
                            "win_pct": round(sum(1 for r in front if r["position"] == 1) / len(front), 3),
                            "podium_pct": round(sum(1 for r in front if 0 < r["position"] <= 3) / len(front), 3)}
                           if len(front) >= MIN_CIRCUIT else
                           {"n": len(front), "win_pct": None,
                            "note": "too few top-5 starts to read"}),
        "source": "counted from f1_results.json — description, not prediction",
    }


def circuit(cid: str, rows: Optional[list[dict]] = None) -> Optional[dict]:
    """Is this a track where you can actually overtake, or is the grid the race?"""
    rows = rows if rows is not None else load()
    rs = [r for r in rows if r["circuit"] == cid]
    races = {(r["year"], r["round"]) for r in rs}
    if len(races) < MIN_CIRCUIT:
        return None
    fin = [r for r in rs if r["finished"] and r["grid"] > 0 and r["position"] > 0]
    moves = [abs(r["grid"] - r["position"]) for r in fin]
    gained = [r["grid"] - r["position"] for r in fin]
    # Did the winner start on the front row? On a track that cannot be passed
    # on, almost always.
    winners = [r for r in rs if r["position"] == 1 and r["grid"] > 0]
    return {
        "circuit": cid,
        "races": len(races),
        "overtaking": {
            "avg_places_changed": round(statistics.fmean(moves), 2) if moves else None,
            "avg_places_gained_by_finishers": round(statistics.fmean(gained), 2) if gained else None,
            "winner_avg_grid": round(statistics.fmean([r["grid"] for r in winners]), 2) if winners else None,
            "winner_from_front_row_pct": (round(sum(1 for r in winners if r["grid"] <= 2) / len(winners), 3)
                                          if winners else None),
            "note": "low places-changed + winner starting P1/P2 = qualifying IS "
                    "the market here, and 'he'll charge through' is a losing bet",
        },
        "attrition": {
            "dnf_rate": round(sum(1 for r in rs if not r["finished"]) / len(rs), 3),
            "note": "cars that failed to finish, all drivers, at this circuit",
        },
        "source": "counted from f1_results.json",
    }


def teammates(constructor: str, rows: Optional[list[dict]] = None) -> Optional[dict]:
    """The only comparison in F1 that holds the car constant — and a real market."""
    rows = rows if rows is not None else load()
    rs = [r for r in rows if r["constructor"] == constructor]
    if not rs:
        return None
    by_race: dict = defaultdict(list)
    for r in rs:
        by_race[(r["year"], r["round"])].append(r)
    h2h: dict = defaultdict(lambda: {"races": 0, "beat": 0})
    for pair in by_race.values():
        if len(pair) != 2:
            continue
        a, b = pair
        # Only comparable when both saw the flag; a blown engine is not a
        # verdict on the driver.
        if not (a["finished"] and b["finished"]):
            continue
        for x, y in ((a, b), (b, a)):
            h2h[x["driver"]]["races"] += 1
            h2h[x["driver"]]["beat"] += x["position"] < y["position"]
    out = {d: {**v, "beat_pct": round(v["beat"] / v["races"], 3)}
           for d, v in h2h.items() if v["races"] >= MIN_CIRCUIT}
    if not out:
        return None
    return {"constructor": constructor, "head_to_head": out,
            "note": "both cars finishing only — a blown engine is not a driver verdict",
            "source": "counted from f1_results.json"}


def context(drivers: list[str], cid: Optional[str] = None) -> dict:
    rows = load()
    out = {"drivers": {d: driver(d, rows) for d in drivers},
           "circuit": circuit(cid, rows) if cid else None,
           "source": "f1_results.json — every figure counted"}
    missing = [d for d, v in out["drivers"].items() if not v]
    if missing:
        out["note"] = (f"no measured profile for {', '.join(missing)} — fewer "
                       f"than {MIN_RACES} races on file")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver")
    ap.add_argument("--circuit")
    ap.add_argument("--teammates")
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    if a.driver:
        print(json.dumps(driver(a.driver), indent=1))
    elif a.circuit:
        print(json.dumps(circuit(a.circuit), indent=1))
    elif a.teammates:
        print(json.dumps(teammates(a.teammates), indent=1))
    elif a.table:
        rows = load()
        cs = sorted({r["circuit"] for r in rows})
        tbl = [c for c in (circuit(x, rows) for x in cs) if c]
        tbl.sort(key=lambda c: c["overtaking"]["avg_places_changed"] or 0)
        for c in tbl:
            o = c["overtaking"]
            print(f"{c['circuit']:<22} changed {o['avg_places_changed']:>5}  "
                  f"winner avg grid {o['winner_avg_grid']:>4}  "
                  f"DNF {c['attrition']['dnf_rate']:.1%}")
    else:
        ap.error("give --driver, --circuit, --teammates or --table")

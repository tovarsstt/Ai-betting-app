#!/usr/bin/env python3
"""
fetch_f1_results.py — race results archive from jolpica (the Ergast successor).

Free, no key. Ergast itself now 403s; jolpica serves the same schema.
Each row keeps the two things F1 prices actually turn on: where a car STARTED
versus where it FINISHED (overtaking difficulty is a circuit property, not a
driver opinion), and WHY it stopped when it did not finish.

Run: python3 scripts/fetch_f1_results.py --seasons 2024 2025 2026
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
OUT = DATA / "f1_results.json"
BASE = "https://api.jolpi.ca/ergast/f1"
TIMEOUT = 25
PAGE = 100


def _get(url: str, tries: int = 3) -> dict:
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))       # jolpica rate-limits; back off
    return {}


def season(year: int) -> list[dict]:
    rows, offset = [], 0
    while True:
        d = _get(f"{BASE}/{year}/results.json?limit={PAGE}&offset={offset}")
        md = d.get("MRData", {})
        races = md.get("RaceTable", {}).get("Races", [])
        for r in races:
            for res in r.get("Results", []):
                st = res.get("status", "")
                rows.append({
                    "year": year,
                    "round": int(r.get("round", 0)),
                    "race": r.get("raceName"),
                    "circuit": (r.get("Circuit") or {}).get("circuitId"),
                    "date": r.get("date"),
                    "driver": (res.get("Driver") or {}).get("driverId"),
                    "driver_name": ((res.get("Driver") or {}).get("familyName") or ""),
                    "constructor": (res.get("Constructor") or {}).get("constructorId"),
                    "grid": int(res.get("grid") or 0),
                    "position": int(res.get("position") or 0),
                    "points": float(res.get("points") or 0),
                    "status": st,
                    # jolpica normalises status text and writes "Lapped" where
                    # classic Ergast wrote "+1 Lap". A lapped car SAW THE FLAG —
                    # counting it as a DNF tripled the measured attrition rate.
                    # Disqualified is kept out of "finished" deliberately: for a
                    # bet it dies the same way a retirement does.
                    "finished": st in ("Finished", "Lapped") or st.startswith("+"),
                    "dnf_kind": ("none" if st in ("Finished", "Lapped") or st.startswith("+")
                                 else "dns" if st == "Did not start"
                                 else "dsq" if st == "Disqualified" else "retired"),
                    "laps": int(res.get("laps") or 0),
                })
        total = int(md.get("total") or 0)
        offset += PAGE
        if offset >= total or not races:
            break
        time.sleep(0.4)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", default=[2024, 2025, 2026])
    a = ap.parse_args()
    try:
        doc = json.loads(OUT.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        doc = {"results": []}
    keep = [r for r in doc.get("results", []) if r["year"] not in a.seasons]
    fresh: list[dict] = []
    for y in a.seasons:
        got = season(y)
        print(f"  {y}: {len(got)} car-results")
        fresh.extend(got)
    doc = {"results": keep + fresh,
           "seasons": sorted({r["year"] for r in keep + fresh}),
           "source": "jolpica (Ergast successor), free, no key"}
    OUT.write_text(json.dumps(doc))
    print(f"wrote {len(doc['results'])} rows -> {OUT}")

#!/usr/bin/env python3
"""
fetch_cricket_rankings.py — official ICC team ratings (T20I / ODI / Test) parsed
from Wikipedia's ICC rankings pages (the tables mirror the ICC's own published
table, with a "Source: ICC ... <date>" stamp we carry into meta).

Why: user bets international cricket (England ML won Jul 16) but the app had no
data. This gives every match REAL rating context (rule 13 profiles) AND — since
2026-07-17 — a win-probability mapping FITTED on real results: a cricsheet-derived
matches CSV (10k+ internationals, mirrored on GitHub) supplies (rating diff,
outcome) pairs per format; the logistic scale is MLE-fitted per format, with
franchise teams auto-excluded (both sides must be in the ICC table) and
ties/no-results dropped. Test-match probs are P(win | a result) — the measured
draw rate is stored alongside so nobody misreads them. If the results CSV is
unreachable the fit is skipped and cricket_model falls back to context-only
refusal — never an invented constant.

Caveat carried in meta: CURRENT ICC ratings are applied to matches inside a
recent window (ratings treated as quasi-static over it).

Writes data/cricket_ratings.json:
  {"meta": {..., "fits": {fmt: {k, n, favorite_accuracy, window_since,
   draw_or_nr_rate}}}, "t20i": {team: {rating, points, matches, rank}}, ...}

Run: python3 scripts/fetch_cricket_rankings.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "cricket_ratings.json"
PAGES = {
    "t20i": "https://en.wikipedia.org/wiki/ICC_Men%27s_T20I_Team_Rankings",
    "odi": "https://en.wikipedia.org/wiki/ICC_Men%27s_ODI_Team_Rankings",
    "test": "https://en.wikipedia.org/wiki/ICC_Men%27s_Test_Team_Rankings",
}
# cricsheet-derived internationals summary (one row per match, winner included),
# mirrored on GitHub — raw.githubusercontent stays reachable when cricsheet.org
# and espncricinfo are TLS-blocked (the "always find a workaround" lesson).
RESULTS_CSV = ("https://raw.githubusercontent.com/yash-006/"
               "Cricsheet-Match-Data-Analysis/HEAD/data/processed/matches.csv")
# per-format fit window: current ratings treated as quasi-static inside it;
# T20I plays enough for 12 months, ODI/Test need longer to reach sample.
FIT_WINDOWS = {"T20": ("t20i", "2025-01-01"), "ODI": ("odi", "2023-07-01"),
               "Test": ("test", "2023-01-01")}
MIN_FIT_MATCHES = 100
UA = {"User-Agent": "Mozilla/5.0"}


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _strip(cell: str) -> str:
    return re.sub(r"<[^>]+>|\n", "", cell).strip()


def parse_rankings_table(html: str) -> tuple[dict, str]:
    """(teams, source_stamp) from the first wikitable shaped
    [Team, Matches, Points, Rating]. Rank = row order (the page sorts by rating)."""
    tables = re.findall(r'<table class="wikitable[^"]*"(.*?)</table>', html, re.S)
    for t in tables:
        heads = [_strip(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
        if len(heads) < 4 or heads[0] != "Team" or heads[3] != "Rating":
            continue
        # stamp looks like: Source: [https://... ICC ... Rankings], 11 July 2026
        stamp_m = re.search(r"Source:.*?(\d{1,2} \w+ \d{4})", t, re.S)
        stamp = stamp_m.group(1) if stamp_m else ""
        teams: dict = {}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
            cells = [_strip(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            if len(cells) < 4 or not cells[0] or cells[0] == "Team":
                continue
            try:
                teams[cells[0]] = {
                    "matches": int(cells[1].replace(",", "")),
                    "points": int(cells[2].replace(",", "")),
                    "rating": int(cells[3].replace(",", "")),
                    "rank": len(teams) + 1,
                }
            except ValueError:
                continue
        if len(teams) >= 10:
            return teams, stamp
    return {}, ""


def fit_logistic_scale(pairs: list, k_lo=0.001, k_hi=0.10, steps=198) -> float:
    """MLE grid fit for k in P = 1/(1+exp(-k*diff)) — same method the volleyball
    model uses (one-parameter concave likelihood, grid is enough)."""
    import math
    best_k, best_ll = k_lo, -math.inf
    for i in range(steps + 1):
        k = k_lo + (k_hi - k_lo) * i / steps
        ll = 0.0
        for diff, won in pairs:
            p = min(max(1.0 / (1.0 + math.exp(-k * diff)), 1e-9), 1 - 1e-9)
            ll += math.log(p) if won else math.log(1.0 - p)
        if ll > best_ll:
            best_k, best_ll = k, ll
    return best_k


def fit_formats(csv_text: str, doc: dict) -> dict:
    """Per-format {k, n, favorite_accuracy, window_since, draw_or_nr_rate} from
    real results. Both teams must be in the ICC table (drops franchise sides);
    ties/no-results counted into draw_or_nr_rate, excluded from the fit."""
    import csv as _csv
    import io
    rows = list(_csv.DictReader(io.StringIO(csv_text)))
    fits: dict = {}
    for mtype, (fmt, since) in FIT_WINDOWS.items():
        table = doc.get(fmt) or {}
        pairs, undecided, total = [], 0, 0
        for r in rows:
            if r.get("match_type") != mtype or (r.get("match_date") or "") < since:
                continue
            t1, t2, w = r.get("team1"), r.get("team2"), r.get("winner")
            if t1 not in table or t2 not in table:
                continue
            total += 1
            if w not in (t1, t2):
                undecided += 1
                continue
            diff = table[t1]["rating"] - table[t2]["rating"]
            pairs.append((diff, 1 if w == t1 else 0))
        if len(pairs) < MIN_FIT_MATCHES:
            continue
        acc = sum(1 for d, won in pairs if (d > 0) == (won == 1)) / len(pairs)
        fits[fmt] = {
            "k": round(fit_logistic_scale(pairs), 4),
            "n": len(pairs),
            "favorite_accuracy": round(acc, 4),
            "window_since": since,
            "draw_or_nr_rate": round(undecided / total, 4) if total else 0.0,
        }
    return fits


def main() -> int:
    doc: dict = {"meta": {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ICC official ratings via Wikipedia rankings pages",
        "source_dates": {},
        "method": "ICC ratings + per-format logistic win-prob, scale MLE-fitted on "
                  "real results (cricsheet-derived matches CSV); current ratings "
                  "treated as quasi-static over each fit window",
    }}
    for fmt, url in PAGES.items():
        teams, stamp = parse_rankings_table(fetch_html(url))
        if not teams:
            print(f"{fmt}: no rankings table parsed — aborting, keeping old file",
                  file=sys.stderr)
            return 1
        doc[fmt] = teams
        doc["meta"]["source_dates"][fmt] = stamp

    # win-prob fit from real results — skipped (not faked) if CSV unreachable
    try:
        req = urllib.request.Request(RESULTS_CSV, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            csv_text = r.read().decode("utf-8", errors="replace")
        doc["meta"]["fits"] = fit_formats(csv_text, doc)
        doc["meta"]["results_source"] = RESULTS_CSV
    except Exception as e:                                    # noqa: BLE001
        doc["meta"]["fits"] = {}
        doc["meta"]["fit_note"] = f"results CSV unreachable ({e}) — context-only mode"

    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    fits = doc["meta"]["fits"]
    print(f"wrote {OUT.name}: " + ", ".join(
        f"{fmt} {len(doc[fmt])} teams"
        + (f" [k={fits[fmt]['k']} n={fits[fmt]['n']} acc={fits[fmt]['favorite_accuracy']:.0%}]"
           if fmt in fits else " [no fit]")
        for fmt in PAGES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

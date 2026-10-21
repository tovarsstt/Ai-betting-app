"""
calibrate_ucl.py — build ONE cross-league Elo from real results and fit Elo -> goals.

Why not ClubElo: api.clubelo.com returned 502 even from GitHub runners. Instead we
use data we CAN get: big-5 + extra-league domestic results (football-data.co.uk) and
UEFA competition results (ESPN). The UEFA matches are the only bridge between leagues,
so clubs with no UEFA/domestic link to the rest are reported, not guessed.

Inputs (data/soccer/): club_results.csv, extra_league_results.csv, uefa_results.csv
Outputs: elo_ratings.json  {club(normalized): elo}   ucl_elo_goal_model.json {a,h,b,...}

Limits: league strength is learned only from the few UEFA matches (K=40), so cross-league
gaps are noisy early in a season. Elo uses pre-match ratings (no look-ahead).
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import ucl_model as um

DATA = Path(__file__).parent.parent / "data" / "soccer"

# spelling variants -> football-data spelling (normalized). Extend from the `unlinked` report.
ALIASES = {
    "manchester city": "man city", "manchester united": "man united",
    "atletico madrid": "ath madrid", "atletico de madrid": "ath madrid",
    "paris saint germain": "paris sg", "paris saint-germain": "paris sg",
    "borussia dortmund": "dortmund", "bayer leverkusen": "leverkusen", "bayer 04 leverkusen": "leverkusen",
    "eintracht frankfurt": "ein frankfurt", "borussia monchengladbach": "m'gladbach",
    "tottenham hotspur": "tottenham", "newcastle united": "newcastle", "wolverhampton wanderers": "wolves",
    "west ham united": "west ham", "nottingham forest": "nott'm forest", "brighton hove albion": "brighton",
    "athletic club": "ath bilbao", "athletic bilbao": "ath bilbao", "real sociedad": "sociedad",
    "real betis": "betis", "celta vigo": "celta", "rayo vallecano": "vallecano",
    "inter milan": "inter", "internazionale": "inter", "milan": "milan", "roma": "roma",
    "sporting cp": "sp lisbon", "sporting lisbon": "sp lisbon", "sporting": "sp lisbon",
    "olympique marseille": "marseille", "olympique de marseille": "marseille", "olympique lyonnais": "lyon",
    "vfb stuttgart": "stuttgart", "sc braga": "sp braga", "braga": "sp braga", "psv": "psv eindhoven",
    "red bull salzburg": "salzburg", "club brugge": "club brugge", "union saint gilloise": "st. gilloise",
    "royal antwerp": "antwerp", "fenerbahce": "fenerbahce", "galatasaray": "galatasaray",
    "ajax amsterdam": "ajax", "feyenoord rotterdam": "feyenoord", "as monaco": "monaco",
    "lille": "lille", "ac milan": "milan", "as roma": "roma", "ssc napoli": "napoli",
}


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9'. ]", " ", s)
    s = re.sub(r"\b(fc|cf|afc|sc|ac|sv|fk|if|bk|ssc|as)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def load_results(*paths: Path) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if p.exists():
            with p.open() as f:
                rows.extend(csv.DictReader(f))
    return rows


def run(result_paths: list[Path], out_dir: Path = DATA) -> dict:
    raw = load_results(*result_paths)
    rows = [{**r, "home_team": normalize(r["home_team"]), "away_team": normalize(r["away_team"])} for r in raw]
    elo, samples = um.build_elo(rows)
    model = um.calibrate_pre(samples)
    dom = Counter(); eur = Counter()
    for r in rows:
        tgt = eur if str(r["league"]).startswith("UEFA") else dom
        tgt[r["home_team"]] += 1; tgt[r["away_team"]] += 1
    # a UEFA club with no domestic matches has no link into the rating network
    unlinked = sorted(c for c in eur if dom[c] == 0)
    res = {"a": model.a, "h": model.h, "b": model.b, "calibrated": model.calibrated,
           "n_matches": model.n_matches, "n_results_read": len(raw), "n_clubs": len(elo),
           "n_uefa_matches": sum(1 for r in rows if str(r["league"]).startswith("UEFA")),
           "uefa_clubs_without_domestic_data": unlinked}
    (out_dir / "ucl_elo_goal_model.json").write_text(json.dumps(res, indent=2))
    games = Counter()
    for r in rows:
        games[r["home_team"]] += 1; games[r["away_team"]] += 1
    (out_dir / "club_games.json").write_text(json.dumps(dict(games)))
    (out_dir / "elo_ratings.json").write_text(json.dumps({k: round(v, 1) for k, v in sorted(elo.items(), key=lambda kv: -kv[1])}, indent=1))
    return res


def main() -> None:
    res = run([DATA / "club_results.csv", DATA / "extra_league_results.csv", DATA / "uefa_results.csv"])
    print(json.dumps({k: v for k, v in res.items() if k != "uefa_clubs_without_domestic_data"}, indent=2))
    ul = res["uefa_clubs_without_domestic_data"]
    print(f"UEFA clubs with NO domestic data ({len(ul)}): {ul}")
    elo = json.loads((DATA / "elo_ratings.json").read_text())
    print("Top 15 Elo:", list(elo.items())[:15])


if __name__ == "__main__":
    main()

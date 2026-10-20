"""
calibrate_ucl.py — fit the Elo->goals model on real fetched results.

Inputs (all produced by fetch_europe_data.py / fetch_club_results.py):
  data/soccer/clubelo.csv, club_results.csv (big-5), extra_league_results.csv
Output: data/soccer/ucl_elo_goal_model.json  {a,h,b,calibrated,n_matches,unmatched_clubs}

Known limitation: uses the CURRENT ClubElo snapshot for past matches (mild
look-ahead). Name matching: ClubElo vs football-data spell clubs differently;
`normalize` + ALIASES bridge the common cases and every unmatched club is
LISTED in the output (matches with an unmatched club are dropped, never guessed).
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

import ucl_model as um

DATA = Path(__file__).parent.parent / "data" / "soccer"
OUT = DATA / "ucl_elo_goal_model.json"

# football-data spelling -> ClubElo spelling (only pairs I am confident about; extend from the unmatched list)
ALIASES = {
    "man city": "man city", "man united": "man united", "ath madrid": "atletico", "ath bilbao": "athletic",
    "sociedad": "real sociedad", "betis": "betis", "celta": "celta", "vallecano": "rayo vallecano",
    "espanol": "espanyol", "nott'm forest": "forest", "paris sg": "paris sg", "st etienne": "st etienne",
    "m'gladbach": "gladbach", "ein frankfurt": "frankfurt", "leverkusen": "leverkusen",
    "inter": "inter", "milan": "milan", "sp lisbon": "sporting", "sp braga": "braga",
    "porto": "porto", "benfica": "benfica", "psv eindhoven": "psv", "feyenoord": "feyenoord",
}


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    s = re.sub(r"\b(fc|cf|afc|sc|ac|as|sv|fk|if|bk)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def load_elo(path: Path) -> dict[str, float]:
    with path.open() as f:
        return {normalize(r["Club"]): float(r["elo"]) for r in csv.DictReader(f) if r.get("elo")}


def load_results(*paths: Path) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        if p.exists():
            with p.open() as f:
                rows.extend(csv.DictReader(f))
    return rows


def run(elo_path: Path, result_paths: list[Path], out: Path = OUT) -> dict:
    elo = load_elo(elo_path)
    rows = load_results(*result_paths)
    norm_rows, unmatched = [], set()
    for r in rows:
        h, a = normalize(r["home_team"]), normalize(r["away_team"])
        for raw, n in ((r["home_team"], h), (r["away_team"], a)):
            if n not in elo:
                unmatched.add(raw)
        norm_rows.append({**r, "home_team": h, "away_team": a})
    m = um.calibrate(norm_rows, elo)
    res = {"a": m.a, "h": m.h, "b": m.b, "calibrated": m.calibrated, "n_matches": m.n_matches,
           "n_results_read": len(rows), "unmatched_clubs": sorted(unmatched)}
    out.write_text(json.dumps(res, indent=2))
    return res


def main() -> None:
    if not (DATA / "clubelo.csv").exists():
        raise SystemExit("clubelo.csv missing — run fetch_europe_data.py clubelo first")
    res = run(DATA / "clubelo.csv", [DATA / "club_results.csv", DATA / "extra_league_results.csv"])
    print(json.dumps({k: v for k, v in res.items() if k != "unmatched_clubs"}, indent=2))
    print(f"unmatched clubs ({len(res['unmatched_clubs'])}): {res['unmatched_clubs'][:25]}")


if __name__ == "__main__":
    main()

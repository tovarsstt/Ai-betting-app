"""
fetch_club_results.py — download + cache REAL club-league match results for
the soccer Poisson regression + eigenvector ratings fit.

The existing international ratings (fetch_international_results.py) only
cover national teams — a small slice of what's actually wagerable outside a
World Cup window. This does the same job for the big-5 domestic leagues:

Source: football-data.co.uk (same publisher as tennis-data.co.uk, already
used by fetch_tennis_form.py/fetch_tennis_surface.py — plain HTTP, free, no
API key, verified reachable). One CSV per league per season.

Run manually (like fetch_international_results.py) — NOT called from the
live API path, and NEVER during tests (tests read the cached CSV, never
network).

    python3 scripts/fetch_club_results.py
"""
from __future__ import annotations

import csv
import datetime
import io
import urllib.request
from pathlib import Path

CACHE = Path(__file__).parent.parent / "data" / "soccer" / "club_results.csv"

# Big-5 European domestic top flights — highest wagered volume outside a
# World Cup window. Codes are football-data.co.uk's own division codes.
LEAGUES = {
    "E0":  "Premier League",
    "SP1": "La Liga",
    "I1":  "Serie A",
    "D1":  "Bundesliga",
    "F1":  "Ligue 1",
}


def _season_codes(today: datetime.date | None = None, n: int = 3) -> list[str]:
    """football-data.co.uk season codes like '2526' for 2025-26. Season starts
    in July/August; before that month, the "current" season is still last
    year's code. Returns the `n` most recent (current first)."""
    today = today or datetime.date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return [f"{(start_year - i) % 100:02d}{(start_year - i + 1) % 100:02d}" for i in range(n)]


def fetch(div: str, season: str, timeout: int = 20) -> str:
    """Network call — only invoked by main()/CLI, never at import time or in tests."""
    url = f"https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "caveman-locks/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def _reformat_row(row: dict, league: str) -> dict | None:
    """football-data.co.uk -> the same row shape poisson_regression.fit() /
    eigen_ratings.fit() already consume for international results."""
    date_raw = row.get("Date")
    home, away = row.get("HomeTeam"), row.get("AwayTeam")
    hg, ag = row.get("FTHG"), row.get("FTAG")
    if not date_raw or not home or not away or hg in (None, "") or ag in (None, ""):
        return None
    d = None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            d = datetime.datetime.strptime(date_raw, fmt).date()
            break
        except ValueError:
            continue
    if d is None:
        return None
    try:
        home_score, away_score = int(float(hg)), int(float(ag))
    except (TypeError, ValueError):
        return None
    return {
        "date": d.isoformat(), "home_team": home.strip(), "away_team": away.strip(),
        "home_score": home_score, "away_score": away_score,
        "neutral": "FALSE",  # domestic league fixtures are never neutral-venue
        "league": league,
    }


def load_league_season(div: str, season: str) -> list[dict]:
    text = fetch(div, season)
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        r = _reformat_row(row, LEAGUES[div])
        if r:
            out.append(r)
    return out


def save_cache(rows: list[dict], path: Path = CACHE) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["date", "home_team", "away_team", "home_score", "away_score", "neutral", "league"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def load_cached(path: Path = CACHE) -> list[dict]:
    """Read the cached CSV — this is what the rating fitters actually use."""
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    all_rows: list[dict] = []
    for div, league in LEAGUES.items():
        for season in _season_codes():
            try:
                rows = load_league_season(div, season)
                all_rows.extend(rows)
                print(f"  {league} {season}: {len(rows)} matches")
            except Exception as e:
                print(f"  {league} {season}: skip ({e})")
    n = save_cache(all_rows)
    print(f"Cached {n} matches across {len(LEAGUES)} leagues -> {CACHE}")


if __name__ == "__main__":
    main()

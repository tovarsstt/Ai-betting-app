"""
fetch_europe_data.py — cross-league + NBA data for UCL / NBA models.

Closes two gaps found in the audit:
  1. club_ratings.json is fit PER LEAGUE (big-5), so PSG-Barcelona or any
     Porto/PSV/Slavia/Sabah tie can't be priced on one scale. ClubElo gives a
     single, cross-league club rating (all of Europe); football-data.co.uk adds
     NL/PT/TR/BE/GR/SCO domestic results.
  2. data/nba_historical.csv ends 2025-06. ESPN's public scoreboard JSON fills
     2025-26 onwards.

Sources are free and UNOFFICIAL/undocumented where noted (ClubElo API,
ESPN scoreboard). Parsers are pure and tested with fixtures; only the fetch_*
functions touch the network. Run manually — NEVER during tests:

    python3 scripts/fetch_europe_data.py clubelo
    python3 scripts/fetch_europe_data.py extra-leagues
    python3 scripts/fetch_europe_data.py nba 2025-10-21 2026-06-30
"""
from __future__ import annotations

import csv
import datetime
import io
import sys
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"
CLUBELO_CSV = DATA / "soccer" / "clubelo.csv"
EXTRA_RESULTS_CSV = DATA / "soccer" / "extra_league_results.csv"
NBA_GAMES_CSV = DATA / "nba_games_2526.csv"

# football-data.co.uk main-format codes (same URL scheme fetch_club_results uses)
EXTRA_LEAGUES = {
    "N1": "Eredivisie", "P1": "Primeira Liga", "T1": "Super Lig",
    "B1": "Belgian Pro League", "G1": "Super League Greece", "SC0": "Scottish Premiership",
}
UA = {"User-Agent": "caveman-locks/1.0"}


def _get(url: str, timeout: int = 20) -> str:
    """Only network call in this module."""
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig", errors="replace")


# ── ClubElo ────────────────────────────────────────────────────────────────────
def parse_clubelo_csv(text: str) -> dict[str, dict]:
    """ClubElo snapshot CSV (Rank,Club,Country,Level,Elo,From,To) -> {club: {...}}.
    Skips rows with a non-numeric Elo; never invents one."""
    out: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            elo = float(row["Elo"])
        except (KeyError, TypeError, ValueError):
            continue
        club = (row.get("Club") or "").strip()
        if club:
            out[club] = {"elo": elo, "country": (row.get("Country") or "").strip(),
                         "level": row.get("Level"), "as_of": row.get("To") or row.get("From")}
    return out


def fetch_clubelo(day: datetime.date | None = None) -> dict[str, dict]:
    day = day or datetime.date.today()
    return parse_clubelo_csv(_get(f"http://api.clubelo.com/{day.isoformat()}"))


# ── football-data.co.uk extra leagues ──────────────────────────────────────────
def season_code(today: datetime.date | None = None) -> str:
    today = today or datetime.date.today()
    y = today.year if today.month >= 7 else today.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


def fetch_extra_leagues(season: str | None = None) -> list[dict]:
    from fetch_club_results import _reformat_row
    season = season or season_code()
    rows: list[dict] = []
    for div, name in EXTRA_LEAGUES.items():
        try:
            text = _get(f"https://www.football-data.co.uk/mmz4281/{season}/{div}.csv")
        except Exception as e:  # one league failing must not kill the rest
            print(f"  {name}: skip ({e})")
            continue
        for row in csv.DictReader(io.StringIO(text)):
            r = _reformat_row(row, name)
            if r:
                rows.append(r)
        print(f"  {name}: {sum(1 for r in rows if r['league'] == name)} matches")
    return rows


# ── ESPN scoreboard (NBA games) ────────────────────────────────────────────────
def season_start_year(d: datetime.date) -> int:
    """NBA season label = year it starts (2025-26 -> 2025). Season starts ~Oct."""
    return d.year if d.month >= 9 else d.year - 1


def parse_espn_scoreboard(data: dict) -> list[dict]:
    """ESPN scoreboard JSON -> FINISHED games only, in nba_historical.csv shape.
    In-progress / scheduled / malformed events are dropped, never guessed."""
    out = []
    for ev in data.get("events", []) or []:
        try:
            comp = ev["competitions"][0]
            if not ev["status"]["type"].get("completed"):
                continue
            by_side = {c["homeAway"]: c for c in comp["competitors"]}
            h, a = by_side["home"], by_side["away"]
            hs, as_ = int(float(h["score"])), int(float(a["score"]))
            d = datetime.datetime.strptime(ev["date"][:10], "%Y-%m-%d").date()
            # ESPN dates are UTC; late tip-offs belong to the previous US day.
            if int(ev["date"][11:13]) < 8:
                d -= datetime.timedelta(days=1)
            out.append({"game_id": ev["id"], "date": d.isoformat(),
                        "home_team": h["team"]["displayName"], "away_team": a["team"]["displayName"],
                        "home_score": hs, "away_score": as_, "season": season_start_year(d)})
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def fetch_nba_range(start: datetime.date, end: datetime.date, pause: float = 0.4) -> list[dict]:
    games: dict[str, dict] = {}
    d = start
    while d <= end:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d:%Y%m%d}"
        try:
            import json
            for g in parse_espn_scoreboard(json.loads(_get(url))):
                games[g["game_id"]] = g
        except Exception as e:
            print(f"  {d}: skip ({e})")
        d += datetime.timedelta(days=1)
        time.sleep(pause)
    return sorted(games.values(), key=lambda g: g["date"])


def write_csv(rows: list[dict], path: Path, fields: list[str]) -> int:
    """Never clobber an existing cache with an empty result (all fetches failed)."""
    if not rows:
        print(f"  no rows fetched -> {path.name} left untouched")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "clubelo":
        data = fetch_clubelo()
        n = write_csv([{"Club": k, **v} for k, v in data.items()], CLUBELO_CSV,
                      ["Club", "elo", "country", "level", "as_of"])
        print(f"ClubElo: {n} clubs -> {CLUBELO_CSV}")
    elif cmd == "extra-leagues":
        rows = fetch_extra_leagues()
        n = write_csv(rows, EXTRA_RESULTS_CSV,
                      ["date", "home_team", "away_team", "home_score", "away_score", "neutral", "league"])
        print(f"Extra leagues: {n} matches -> {EXTRA_RESULTS_CSV}")
    elif cmd == "nba":
        s, e = (datetime.date.fromisoformat(a) for a in argv[2:4])
        rows = fetch_nba_range(s, e)
        n = write_csv(rows, NBA_GAMES_CSV,
                      ["game_id", "date", "home_team", "away_team", "home_score", "away_score", "season"])
        print(f"NBA: {n} finished games -> {NBA_GAMES_CSV}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)

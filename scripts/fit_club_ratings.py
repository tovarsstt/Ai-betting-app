"""
fit_club_ratings.py — real, data-driven CLUB-league ratings, fit PER LEAGUE.

The international ratings (fit_soccer_ratings.py) only cover national teams —
a small slice of what's actually wagerable outside a World Cup window. This
reuses the exact same fitters (poisson_regression.py / eigen_ratings.py are
sport-agnostic: they just need date/home_team/away_team/scores rows) on the
big-5 domestic leagues (fetch_club_results.py).

Fit PER LEAGUE, not pooled: domestic leagues never play each other, so a
joint fit across all five would leave each league's attack/defense scale
anchored only by ridge shrinkage, not by any real cross-league match data —
the numbers would look sane within a league and be meaningless between them.
Every real prediction is within one league anyway (Barcelona vs Real Madrid
are both La Liga), so per-league fits are both simpler and more correct.

Run manually (like fit_soccer_ratings.py):

    python3 scripts/fetch_club_results.py   # refresh the data (weekly is plenty)
    python3 scripts/fit_club_ratings.py     # refit + write club_ratings.json

Then restart edge_api.py to pick up the new ratings.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import eigen_ratings as er
import poisson_regression as pr
from fetch_club_results import CACHE, LEAGUES, load_cached

OUT = Path(__file__).parent.parent / "data" / "soccer" / "club_ratings.json"


def _by_league(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r.get("league", "?")].append(r)
    return out


def build(as_of: date | None = None) -> dict:
    rows = load_cached()
    if not rows:
        raise SystemExit(
            f"No cached data at {CACHE} — run fetch_club_results.py first."
        )
    grouped = _by_league(rows)

    leagues = {}
    for league, league_rows in grouped.items():
        poisson = pr.fit(league_rows, as_of=as_of)
        eigen = er.fit(league_rows, as_of=as_of)

        teams = {}
        for team in sorted(set(poisson.teams) | set(eigen.ratings)):
            p = poisson.teams.get(team, {})
            teams[team] = {
                "attack": p.get("attack"),
                "defense": p.get("defense"),
                "n_matches": p.get("n_matches"),
                "eigen_rating": eigen.ratings.get(team),
            }
        leagues[league] = {
            "n_matches_poisson": poisson.n_matches,
            "n_matches_eigen": eigen.n_matches,
            "n_teams": len(teams),
            "mu": poisson.mu,
            "home_advantage": poisson.home_advantage,
            "teams": teams,
        }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "football-data.co.uk",
        "method": "PoissonRidgeMLE(time_decay_halflife=730d) + KeenerEigenvector(power_iteration), fit per-league",
        "leagues": leagues,
    }


def main() -> None:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    total_teams = sum(l["n_teams"] for l in result["leagues"].values())
    print(f"Fit {len(result['leagues'])} leagues, {total_teams} teams total -> {OUT}")
    for league, l in result["leagues"].items():
        print(f"  {league}: {l['n_teams']} teams, {l['n_matches_poisson']} matches")


if __name__ == "__main__":
    main()

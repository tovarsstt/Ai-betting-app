"""
fit_soccer_ratings.py — orchestrates the real, data-driven national-team
rating fit and writes it where edge_api.py loads it from at startup.

Replaces the old fallback (a static {"attack": 1.4, "defense": 1.2} default
used for every unrated team — see get_ratings() in edge_api.py) with:
    - Poisson regression attack/defense (poisson_regression.py)
    - Keener eigenvector strength rating (eigen_ratings.py)
both fit from real match results (fetch_international_results.py). Only
used when the caller has no market odds to calibrate against — full 1X2
odds still beat any model per soccer_markets.py's documented priority.

Run manually, like train_all_sports.py:

    python3 scripts/fetch_international_results.py   # refresh the data (weekly is plenty)
    python3 scripts/fit_soccer_ratings.py             # refit + write international_ratings.json

Then restart edge_api.py to pick up the new ratings.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import eigen_ratings as er
import poisson_regression as pr
from fetch_international_results import CACHE, load_cached

OUT = Path(__file__).parent.parent / "data" / "soccer" / "international_ratings.json"


def build(as_of: date | None = None) -> dict:
    rows = load_cached()
    if not rows:
        raise SystemExit(
            f"No cached data at {CACHE} — run fetch_international_results.py first."
        )
    poisson = pr.fit(rows, as_of=as_of)
    eigen = er.fit(rows, as_of=as_of)

    teams = {}
    for team in sorted(set(poisson.teams) | set(eigen.ratings)):
        p = poisson.teams.get(team, {})
        teams[team] = {
            "attack": p.get("attack"),
            "defense": p.get("defense"),
            "n_matches": p.get("n_matches"),
            "eigen_rating": eigen.ratings.get(team),
        }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "martj42/international_results",
        "n_matches_poisson": poisson.n_matches,
        "n_matches_eigen": eigen.n_matches,
        "n_teams": len(teams),
        "mu": poisson.mu,
        "home_advantage": poisson.home_advantage,
        "method": "PoissonRidgeMLE(time_decay_halflife=730d) + KeenerEigenvector(power_iteration)",
        "teams": teams,
    }


def main() -> None:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(f"Fit {result['n_teams']} teams from {result['n_matches_poisson']} matches -> {OUT}")


if __name__ == "__main__":
    main()

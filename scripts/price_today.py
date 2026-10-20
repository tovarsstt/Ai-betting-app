"""
price_today.py — price today's UCL ties from the calibrated cross-league Elo.
Output order per match: P(win) first (home/draw/away), then totals. No odds are
fetched here, so there is NO EV — pass real odds to ucl_model.price_match to get it.

    python3 scripts/price_today.py 2026-10-20
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import calibrate_ucl as cu
import fetch_europe_data as fe
import ucl_model as um

DATA = Path(__file__).parent.parent / "data" / "soccer"


def price_fixtures(fixtures: list[dict], elo: dict[str, float], model: um.EloGoalModel) -> list[dict]:
    out = []
    for f in fixtures:
        r = um.price_match(cu.normalize(f["home"]), cu.normalize(f["away"]), elo, model)
        out.append({"match": f"{f['home']} vs {f['away']}", "kickoff": f["kickoff"], **r})
    return out


def main() -> None:
    day = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    elo = json.loads((DATA / "elo_ratings.json").read_text())
    m = json.loads((DATA / "ucl_elo_goal_model.json").read_text())
    model = um.EloGoalModel(a=m["a"], h=m["h"], b=m["b"], calibrated=m["calibrated"], n_matches=m["n_matches"])
    fixtures = fe.fetch_fixtures(day)
    print(f"{day}: {len(fixtures)} UCL fixtures | model calibrated={model.calibrated} on {model.n_matches} matches")
    for r in price_fixtures(fixtures, elo, model):
        if "error" in r:
            print(f"- {r['match']}: SKIPPED — {r['error']}")
            continue
        p = r["p_win"]
        print(f"- {r['match']}: P(home)={p['home']*100:.1f}% P(draw)={p['draw']*100:.1f}% P(away)={p['away']*100:.1f}% "
              f"| xG {r['lambda_home']:.2f}-{r['lambda_away']:.2f} | O2.5 {r['over_2_5']*100:.0f}% BTTS {r['btts']*100:.0f}% | no odds -> no EV")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
lmb_model.py — LMB moneyline + totals from real team run rates. Pure math, no
network: reads data/lmb_ratings.json (fetch_lmb_standings.py).

Headline ML number = log5 on Pythagorean win% (exponent fitted to THIS league),
with the league's own measured home-field advantage folded in log5-style.
Totals/run-line come from a Poisson score matrix on matchup-adjusted run rates
(rs_pg vs opponent ra_pg over league environment — the standard runs-matchup
adjustment). Poisson slightly thins baseball's run tails (real runs are a touch
over-dispersed); noted in the output so nobody reads totals as sharper than
they are. Unknown team → refusal, never an estimate.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from poisson_model import score_matrix, win_draw_loss

DATA = Path(__file__).parent.parent / "data" / "lmb_ratings.json"
MAX_RUNS = 25       # baseball needs a wider matrix than soccer's default 10


def load() -> dict | None:
    try:
        return json.loads(DATA.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _team_key(name: str, teams: dict) -> str | None:
    if name in teams:
        return name
    nl = name.strip().lower()
    for t in teams:
        if t.lower() == nl:
            return t
    for t in teams:                      # "Dorados" -> "Dorados de Chihuahua"
        if len(nl) >= 4 and (nl in t.lower() or t.lower() in nl):
            return t
    return None


def _log5(pa: float, pb: float) -> float:
    """Bill James log5: P(A beats B) from each side's win prob vs average."""
    num = pa * (1 - pb)
    den = num + pb * (1 - pa)
    return num / den if den > 0 else 0.5


def predict(home: str, away: str) -> dict:
    doc = load()
    if doc is None:
        return {"error": "NO_DATA",
                "note": "lmb_ratings.json missing — run fetch_lmb_standings.py"}
    teams, meta = doc["teams"], doc["meta"]
    hk, ak = _team_key(home, teams), _team_key(away, teams)
    if not hk or not ak:
        missing = [n for n, k in ((home, hk), (away, ak)) if not k]
        return {"error": "NO_DATA", "missing_teams": missing,
                "note": "team(s) not in LMB standings — no data, not estimating"}

    h, a = teams[hk], teams[ak]
    x = float(meta["pyth_exponent"])
    pyth_h = h["rs"] ** x / (h["rs"] ** x + h["ra"] ** x)
    pyth_a = a["rs"] ** x / (a["rs"] ** x + a["ra"] ** x)
    p_neutral = _log5(pyth_h, pyth_a)
    hfa = meta.get("home_win_pct")
    p_home = _log5(p_neutral, 1 - float(hfa)) if hfa else p_neutral

    # Matchup-adjusted expected runs for totals / run line (incl-extras approx:
    # ML above is the headline; the matrix's tie mass is split by run-rate ratio).
    rpg = float(meta["league_rpg"])
    lh = h["rs_pg"] * a["ra_pg"] / rpg
    la = a["rs_pg"] * h["ra_pg"] / rpg
    matrix = score_matrix(lh, la, max_count=MAX_RUNS)
    hw, tie, aw = win_draw_loss(matrix)
    tie_to_home = lh / (lh + la)
    poisson_ml_home = hw + tie * tie_to_home

    return {
        "home": hk, "away": ak,
        "records": {hk: f"{h['w']}-{h['l']}", ak: f"{a['w']}-{a['l']}"},
        "run_rates": {hk: {"rs_pg": h["rs_pg"], "ra_pg": h["ra_pg"]},
                      ak: {"rs_pg": a["rs_pg"], "ra_pg": a["ra_pg"]}},
        "ml_prob": {hk: round(p_home, 4), ak: round(1 - p_home, 4)},
        "ml_prob_poisson_check": {hk: round(poisson_ml_home, 4)},
        "expected_runs": {hk: round(lh, 2), ak: round(la, 2),
                          "total": round(lh + la, 2)},
        "calibration": {
            "pyth_exponent": meta["pyth_exponent"], "league_rpg": meta["league_rpg"],
            "home_win_pct": meta.get("home_win_pct"), "source": meta["source"],
            "fetched_at": meta["fetched_at"],
            "note": "team-level rates only — NO starting-pitcher adjustment, so a "
                    "big market disagreement usually means the market knows the "
                    "pitchers; Poisson thins run tails slightly, ML is the headline",
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: lmb_model.py <home_team> <away_team>")
        raise SystemExit(2)
    print(json.dumps(predict(sys.argv[1], sys.argv[2]), indent=1, ensure_ascii=False))

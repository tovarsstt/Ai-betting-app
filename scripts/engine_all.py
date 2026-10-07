#!/usr/bin/env python3
"""
engine_all.py — one entry point, one niche per sport.

REGISTRY says, per sport, exactly what the engine knows and how it knows it:
  family      the score distribution fitted on that sport's own closing lines (sport_math.py)
  validated   context effects that replicated out of sample (and their size)
  priced      variables tested and found ALREADY IN THE PRICE (with the 95% CI of what the data can rule out)
  untested    niche variables for which no outcome data exists yet (and what would unlock them) -> applied as 0

analyze_game() prices every market of one game from (total, de-vigged ML or p_home), applies ONLY validated
context, blends with the market's own de-vigged price when both sides are quoted, and sizes the stake with
uncertainty-aware Kelly.   CLI:
    python3 scripts/engine_all.py registry
    python3 scripts/engine_all.py nfl   --total 45.5 --p-home 0.62 --line -3.5 --total-line 45.5 --wind 22 --cover-odds 1.91,1.91 --over-odds 1.91,1.91
    python3 scripts/engine_all.py mlb   --total 8.5  --p-home 0.58 --line -1.5 --total-line 8.5
    python3 scripts/engine_all.py tennis --a "Li, Ann" --b "Svitolina, Elina" --ml 3.75,1.29
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import betting_math as bm  # noqa: E402
import sport_math as sm  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
WIND = json.loads((DATA / "heuristic_coefficients.json").read_text()).get("wind_scoring", {}) if (DATA / "heuristic_coefficients.json").exists() else {}
CTX = json.loads((DATA / "sport_context_coefficients.json").read_text()) if (DATA / "sport_context_coefficients.json").exists() else {}


def _ci(sport: str, block: str, key: str) -> Optional[list]:
    return CTX.get(sport, {}).get(block, {}).get(key, {}).get("ci95")


REGISTRY: Dict[str, dict] = {
    "tennis": {
        "family": "point-by-point Bernoulli -> exact hold -> sets/match, hierarchical day serve-rate sd 0.05 (+per-player se), level-anchored to power-devigged ML (engine_v2)",
        "validated": {"days_since_last_match": "-0.018 logit/day", "games_last_7_days": "+0.0075 logit/10 games", "altitude>=500m": "+0.46 total games"},
        "priced": {"back_to_back_day": "CI -0.011..+0.043 logit", "long_previous_match": "did not replicate", "birthday": "underpowered, CI -0.16..+0.35 logit"},
        "untested": {"pressure/personal goals": "no outcome data", "weather on serve": "no weather-matched tennis results"},
    },
    "soccer": {
        "family": "Poisson anchored to closing total + home prob; diagonal-inflated Poisson reproduces the market draw exactly (plain Poisson: draws 23.1% vs 25.05% actual); Dixon-Coles tau rejected (0-0 7.7% vs 5.9%)",
        "validated": {},
        "priced": {"rest_diff": f"AH resid CI {_ci('soccer','asian_handicap_resid','rest_diff')}", "short_rest_home": f"AH CI {_ci('soccer','asian_handicap_resid','home_short_rest')} (did not replicate)",
                   "referee_tendency": f"total-goals CI {_ci('soccer','total_goals_resid','ref_prior_total_resid')}"},
        "untested": {"lineups/injuries/xG": "no free per-match source wired", "weather": "no matched weather"},
    },
    "nfl": {
        "family": "empirical key-number residual pmf (3,6,7,10,14) around the implied margin; sigma_margin 13.29, sigma_total 13.42",
        "validated": {"wind>=15mph -> Under": "scoring multiplier exp(-wind_scoring*sigmoid(0.25*(mph-15))); Under 57.9% train n=618 / 68.5% test n=73 (realised wind, forecasts are noisier)"},
        "priced": {"starting QB quality (3,461 games 2012-25)": "explains realised margin (+4.45 pts per AY/A unit, R2 7.5%) but the line prices ~90% of it (residual +0.46, p=0.056, test +0.17 p=0.6)", "short_week": f"CI {_ci('nfl','spread_resid','home_short_week')}", "bye": f"CI {_ci('nfl','spread_resid','home_bye')}", "divisional": "not replicated", "thursday": "not replicated", "dome": "not replicated"},
        "watch": {"backup / unusual starting QB (967 games)": "opponent of the backup team covered 54.5% in 2012-19 (ROI +4.1%) but 51.4% in 2020-25 (ROI -2.0%): the effect DECAYED, market adapted — NOT validated", "heavy favourite (|line|>=7) vs a backup QB": "55.7% (n=334, subset mined after the fact) — hypothesis only"},
        "untested": {"live injury news timing": "needs timestamped reports (Linemate wired in the app, not backtested)", "coaching/travel": "no data"},
    },
    "nba": {
        "family": "Normal margin sigma 11.77 (falls 0.12/pt of spread; Student-t nu=18.5), Normal total sigma 17.47, corr(margin,total) -0.01; win prob from the SPREAD beats the de-vigged ML (log-loss 0.6103 vs 0.6118)",
        "validated": {},
        "priced": {"player availability (talent out, 6,251 games, 5 seasons)": "explains realised margin (beta 0.29/unit, R2 4.7%) but the closing line already prices ~91% of it (residual beta +0.025, p=0.09)", "back_to_back": f"ATS CI {_ci('nba','ats_resid','road_b2b')}", "denver/utah altitude": f"ATS CI {_ci('nba','ats_resid','denver_home')} (Utah significant on train only)", "3-in-4": "not replicated"},
        "watch": {"talent missing -> totals": "+0.053 pts per unit of missing talent (p=0.002 on 2022-24, same sign but p=0.22 on 2025-26): the market may over-lower totals for absences — NOT validated", "rotation players out -> margin": "+0.21 pts per extra rotation player out (p=0.014, did not replicate on the train seasons) — NOT validated"},
        "untested": {"pre-close injury news timing": "needs timestamped injury reports; closing lines already contain what was known at tip"},
    },
    "nhl": {
        "family": "Poisson (no over-dispersion once anchored: NB r->600, bivariate 0)",
        "validated": {},
        "priced": {"back_to_back (totals)": "t=0.3, held-out MSE gain ~0"},
        "untested": {"starting goalie": "no historical goalie-level line data", "shootout/OT scoring convention": "ESPN scores include the shootout goal"},
    },
    "mlb": {
        "family": "negative binomial, shape r=3 — runs are heavily over-dispersed (+0.41 nats/game vs Poisson held-out)",
        "validated": {},
        "priced": {},
        "untested": {"starting pitcher/bullpen": "ESPN closing file has no pitcher ids", "park/wind/temperature": "no matched weather in the closing data"},
    },
}


def _blend(model: float, odds: Optional[Tuple[float, float]]) -> Tuple[float, Optional[float]]:
    if not odds:
        return model, None
    mk = float(bm.devig_power(list(odds))[0])
    return (model + mk) / 2, mk


def analyze_game(sport: str, total: float, p_home: float, line: Optional[float] = None, total_line: Optional[float] = None,
                 p_draw: Optional[float] = None, wind_mph: Optional[float] = None, cover_odds: Optional[Tuple[float, float]] = None,
                 over_odds: Optional[Tuple[float, float]] = None, bankroll: float = 60.0) -> dict:
    sport = sport.lower()
    notes, tot = [], float(total)
    if sport == "nfl" and wind_mph is not None and WIND.get("status") == "calibrated":
        sig = float(1 / (1 + np.exp(-0.25 * (float(wind_mph) - 15.0))))
        mult = float(np.exp(-WIND["value"] * sig))
        tot = total * mult
        notes.append(f"wind {wind_mph} mph -> scoring x{mult:.3f} (validated Under rule): total {total} -> {tot:.1f}")
    r = sm.price_game(sport, tot, p_home, line=line, total_line=total_line, p_draw=p_draw)
    out = {"sport": sport, "family": REGISTRY[sport]["family"].split(";")[0], "inputs": {"total": total, "p_home": p_home}, "model": r, "context": notes, "bets": []}
    from engine_v2 import kelly_stake
    for key, odds, labels in (("cover", cover_odds, ("home", "away")), ("over", over_odds, ("over", "under"))):
        if key in r and odds:
            p_model = r[key]
            p_final, mk = _blend(p_model, odds)
            for side, pm, pf, od in ((labels[0], p_model, p_final, odds[0]), (labels[1], 1 - p_model, 1 - p_final, odds[1])):
                ev = pf * od - 1
                k = kelly_stake(pf, pm, (mk if side == labels[0] else (1 - mk)) if mk is not None else None, od, bankroll)
                out["bets"].append({"market": key, "side": side, "odds": od, "p_model": round(pm, 4), "p_market": None if mk is None else round(mk if side == labels[0] else 1 - mk, 4),
                                    "p_final": round(pf, 4), "ev_pct": round(100 * ev, 2), "kelly_stake_usd": k["stake_usd"], "kelly_f_star": round(k["f_star"], 4)})
    return out


def registry_text() -> str:
    lines = []
    for sp, r in REGISTRY.items():
        lines.append(f"\n=== {sp.upper()} ===\n  family   : {r['family']}")
        for sec in ("validated", "priced", "watch", "untested"):
            for k, v in r.get(sec, {}).items():
                lines.append(f"  {sec:<9}: {k} — {v}")
            if not r.get(sec) and sec != "watch":
                lines.append(f"  {sec:<9}: (none)")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sport")
    ap.add_argument("--total", type=float)
    ap.add_argument("--p-home", type=float)
    ap.add_argument("--line", type=float)
    ap.add_argument("--total-line", type=float)
    ap.add_argument("--p-draw", type=float)
    ap.add_argument("--wind", type=float)
    ap.add_argument("--cover-odds")
    ap.add_argument("--over-odds")
    ap.add_argument("--bankroll", type=float, default=60.0)
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--ml")
    a = ap.parse_args()
    if a.sport == "registry":
        print(registry_text())
    elif a.sport == "tennis":
        import engine_v2 as E
        ml = tuple(float(x) for x in a.ml.split(","))
        S = E.simulate_match(a.a, a.b, ml, n=200_000)
        r = S["rows"]
        print(json.dumps({"P(A wins)": float((r[:, 0] == 0).mean()), "exp_total_games": float(r[:, 5].mean() + r[:, 6].mean() + S["off"]), "serve_sd": S["sd"]}, indent=1))
    else:
        pr = lambda s: tuple(float(x) for x in s.split(",")) if s else None
        print(json.dumps(analyze_game(a.sport, a.total, a.p_home, a.line, a.total_line, a.p_draw, a.wind, pr(a.cover_odds), pr(a.over_odds), a.bankroll), indent=1, default=float))

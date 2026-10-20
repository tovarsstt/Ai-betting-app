"""
validate_halftime.py — fit and check the halftime-refund model on REAL half-by-half NBA scores (ESPN linescores).

Steps (no look-ahead: m for each game comes from a walk-forward Elo, i.e. only earlier games):
  1. empirical: f = share of team-games leading by 16+ at half; r = share leading by 16+ AND not winning (the refund
     event); q = r/f. Poisson/Wilson CI on r (events are rare — the CI is wide and is printed).
  2. model: pick h1_var_share so the model's P(lead>=16 at half) matches f; pick rho so the model's mean P(refund)
     matches r. Writes data/nba_halftime_params.json (fitted=True, n, events).
  3. report model-vs-empirical, and what the promo is worth per bet (mean P(refund) -> EV points).

    python3 scripts/validate_halftime.py [data/nba_halves.csv]
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

import betting_math as bm
import nba_halftime as nh
import nba_stack as ns

DATA = Path(__file__).parent.parent / "data"


def load(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            if r.get("h1_home") in (None, ""):
                continue
            rows.append({"date": date.fromisoformat(r["date"]), "home": r["home_team"], "away": r["away_team"],
                         "hs": int(r["home_score"]), "as": int(r["away_score"]), "season": int(r["season"]),
                         "h1h": int(r["h1_home"]), "h1a": int(r["h1_away"])})
    return sorted(rows, key=lambda g: g["date"])


def walk_forward_margins(games: list[dict]) -> list[float]:
    """Expected home margin before each game from Elo only (no look-ahead)."""
    st, ms = ns.State(), []
    for g in games:
        if g["season"] != st.season:
            st.new_season(g["season"], 0 if st.season < 0 else g["season"] - st.season)
        f = st.features(g["home"], g["away"], g["date"])
        ms.append((f["elo_diff"] + ns.HOME_ELO) / 28.0)
        st.update(g["home"], g["away"], g["hs"], g["as"], g["date"])
    return ms


def empirical(games: list[dict]) -> dict:
    lead = ref = 0
    n_tg = 2 * len(games)
    for g in games:
        m1, m = g["h1h"] - g["h1a"], g["hs"] - g["as"]
        if m1 >= nh.LEAD:
            lead += 1; ref += m <= 0
        if -m1 >= nh.LEAD:
            lead += 1; ref += (-m) <= 0
    lo, hi = bm.wilson(int(ref), n_tg)
    return {"team_games": n_tg, "lead16": lead, "refund_events": int(ref), "f": lead / n_tg, "r": ref / n_tg,
            "q": (ref / lead) if lead else None, "r_ci95": (lo, hi)}


def model_rates(ms: list[float], params: dict) -> tuple[float, float]:
    """Mean over team-games of P(lead>=16 at half) and P(refund)."""
    sig, share = params["sigma"], params["h1_var_share"]
    s1 = sig * np.sqrt(share)
    f = np.mean([norm.sf(nh.LEAD - 0.5, loc=m / 2, scale=s1) + norm.sf(nh.LEAD - 0.5, loc=-m / 2, scale=s1) for m in ms]) / 2
    r = np.mean([nh.refund_prob(m, params) + nh.refund_prob(-m, params) for m in ms]) / 2
    return float(f), float(r)


def fit(games: list[dict], ms: list[float], emp: dict) -> dict:
    base = dict(nh.DEFAULTS)
    sig = float(np.std([g["hs"] - g["as"] - m for g, m in zip(games, ms)]))     # game margin sd around the Elo expectation
    base["sigma"] = sig
    def f_gap(share):
        return model_rates(ms[::7], {**base, "h1_var_share": share})[0] - emp["f"]
    share = brentq(f_gap, 0.25, 0.9) if f_gap(0.25) * f_gap(0.9) < 0 else base["h1_var_share"]
    base["h1_var_share"] = float(share)
    def r_gap(rho):
        return model_rates(ms[::7], {**base, "rho": rho})[1] - emp["r"]
    rho = brentq(r_gap, -0.9, 0.5) if r_gap(-0.9) * r_gap(0.5) < 0 else (-0.9 if r_gap(-0.9) < 0 else 0.5)
    base["rho"] = float(rho)
    base.update({"fitted": True, "n_games": len(games), "refund_events": emp["refund_events"]})
    return base


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "nba_halves.csv"
    games = load(path)
    if len(games) < 500:
        raise SystemExit(f"only {len(games)} games with half scores — need >= 500 to fit")
    ms = walk_forward_margins(games)
    emp = empirical(games)
    print(f"{len(games)} games ({games[0]['date']}..{games[-1]['date']}), {emp['team_games']} team-games")
    print(f"EMPIRICAL: lead 16+ at half in {emp['f']*100:.2f}% of team-games; refund event (led 16+ and did NOT win) "
          f"{emp['refund_events']} times = {emp['r']*100:.3f}% of team-games (Wilson95 {emp['r_ci95'][0]*100:.3f}-{emp['r_ci95'][1]*100:.3f}%)"
          f"; blown-lead rate q = {emp['q']*100:.1f}% of 16+ leads")
    d = nh.DEFAULTS
    f0, r0 = model_rates(ms[::7], d)
    print(f"DEFAULT independent-increments model: lead16 {f0*100:.2f}% | refund {r0*100:.3f}%  (assumption, before fitting)")
    params = fit(games, ms, emp)
    f1, r1 = model_rates(ms[::7], params)
    print(f"FITTED: sigma {params['sigma']:.2f}, h1 variance share {params['h1_var_share']:.3f}, rho(H1,H2 | m) {params['rho']:+.3f}"
          f"  -> model lead16 {f1*100:.2f}% | refund {r1*100:.3f}%")
    (DATA / "nba_halftime_params.json").write_text(json.dumps(params, indent=1))
    print(f"PROMO VALUE: average P(refund) = {r1*100:.2f}% of stake => about +{r1*100:.2f} EV points per qualifying bet "
          f"(range from the CI on events: {emp['r_ci95'][0]*100:.2f} to {emp['r_ci95'][1]*100:.2f} points)")


if __name__ == "__main__":
    main()

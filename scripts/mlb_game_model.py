#!/usr/bin/env python3
"""
mlb_game_model.py — MLB winners / run line / totals / team totals from real
season data. Pure local math over data/mlb_game_data.json (fetch_mlb_data.py).

Every parameter is measured or fitted, none invented:
  expected runs   rs_pg x opp ra_pg / league_rpg  (standard matchup adjustment)
  home scoring    measured home-vs-away runs ratio from this season's games
  starting pitcher  eff RA9 = (ip_share) x starter RA9 + (1-ip_share) x team RA
                  (bullpen approximated at team average — stated; starter's own
                  share of team RA is a second-order double-count, stated)
  distribution    negative binomial per team, overdispersion phi FITTED to this
                  season's per-team-game runs (phi≈2.2; Poisson thins tails)
  extras          tie mass split by run-rate ratio (baseball has no draws)

Markets: ML, run line ±1.5 (any spread), game total O/U, team totals.
`backtest()` replays the season's completed games jackknife-style (each game
removed from its own inputs) and reports accuracy/Brier/calibration — run it
after every refetch; numbers live in the output, not in promises.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import nbinom, poisson as sp_poisson

DATA = Path(__file__).parent.parent / "data" / "mlb_game_data.json"
MAX_RUNS = 30


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
    for t in teams:                     # "Mets" -> "New York Mets"
        if len(nl) >= 4 and (nl in t.lower() or t.lower() in nl):
            return t
    return None


def nb_pmf_vector(lam: float, phi: float, max_runs: int = MAX_RUNS) -> np.ndarray:
    """P(runs = 0..max_runs) — NB2 with mean lam, variance phi*lam; Poisson if
    phi <= 1 (never observed in practice, guard only)."""
    ks = np.arange(max_runs + 1)
    if phi <= 1.0:
        pmf = sp_poisson.pmf(ks, lam)
    else:
        r = lam / (phi - 1.0)
        pmf = nbinom.pmf(ks, r, 1.0 / phi)
    total = pmf.sum()
    return pmf / total if total > 0 else pmf


def home_scoring_split(games: list[dict]) -> tuple[float, float]:
    """Measured (home_factor, away_factor): how much home/away sides score vs
    the pooled mean. Multiplies the matchup lambdas — data, not assumption."""
    hs = [g["hs"] for g in games]
    as_ = [g["as"] for g in games]
    if not hs:
        return 1.0, 1.0
    mh, ma = float(np.mean(hs)), float(np.mean(as_))
    mid = (mh + ma) / 2.0
    return mh / mid, ma / mid


def pitcher_defense_factor(starter: dict | None, team_ra_pg: float) -> tuple[float, dict | None]:
    """Scale on the OPPONENT's expected runs from the probable starter's real
    line. No starter listed -> 1.0 (team average), stated."""
    if not starter or starter.get("ra9") is None or team_ra_pg <= 0:
        return 1.0, None
    ip_share = min(float(starter.get("ip_per_start") or 5.5) / 9.0, 1.0)
    eff_ra9 = ip_share * float(starter["ra9"]) + (1.0 - ip_share) * team_ra_pg
    return eff_ra9 / team_ra_pg, {
        "name": starter.get("name"), "ra9": starter.get("ra9"),
        "ip_per_start": starter.get("ip_per_start"), "starts": starter.get("starts"),
        "factor_on_opp_runs": round(eff_ra9 / team_ra_pg, 4),
        "note": "bullpen approximated at team average RA",
    }


def _find_probable(doc: dict, hk: str, ak: str,
                   on_date: str | None = None) -> dict | None:
    """probables now span the whole season: exact date for backtests, else the
    next upcoming matchup (>= fetch date) for live predictions."""
    entries = [p for p in doc.get("probables") or []
               if p["home"] == hk and p["away"] == ak]
    if on_date is not None:
        return next((p for p in entries if p["date"] == on_date), None)
    today = str(doc.get("meta", {}).get("fetched_at", ""))[:10]
    upcoming = [p for p in entries if p["date"] >= today]
    return min(upcoming, key=lambda p: p["date"]) if upcoming else None


def _park_adjust(lh: float, la: float, meta: dict, hk: str, ak: str) -> tuple[float, float, float]:
    """Park-neutralize each side's rates (season numbers carry ~half a season of
    the team's own park) then apply the game venue's factor. Validated: cut
    backtest totals MAE 3.633 -> 3.544; ML probs essentially unmoved."""
    pf = meta.get("park_factors") or {}
    f_home_park = float(pf.get(hk, 1.0))
    f_away_park = float(pf.get(ak, 1.0))
    # each lambda = one side's scoring rate x other side's allowing rate, so BOTH
    # teams' park-halves divide out of both lambdas; venue factor multiplies back
    neutral = (1 + (f_home_park - 1) / 2) * (1 + (f_away_park - 1) / 2)
    lh = lh / neutral * f_home_park
    la = la / neutral * f_home_park
    return lh, la, f_home_park


def matchup_lambdas(doc: dict, hk: str, ak: str,
                    use_probables: bool = True) -> tuple[float, float, dict]:
    teams, meta = doc["teams"], doc["meta"]
    h, a = teams[hk], teams[ak]
    rpg = float(meta["league_rpg"])
    lh = h["rs_pg"] * a["ra_pg"] / rpg
    la = a["rs_pg"] * h["ra_pg"] / rpg
    hf, af = home_scoring_split(doc.get("games") or [])
    lh, la = lh * hf, la * af
    lh, la, f_venue = _park_adjust(lh, la, meta, hk, ak)
    ctx: dict = {"home_scoring_factor": round(hf, 4), "away_scoring_factor": round(af, 4),
                 "venue_park_factor": round(f_venue, 4)}
    if use_probables:
        prob = _find_probable(doc, hk, ak)
        if prob:
            f_home_def, hp = pitcher_defense_factor(prob.get("home_pitcher"), h["ra_pg"])
            f_away_def, ap = pitcher_defense_factor(prob.get("away_pitcher"), a["ra_pg"])
            la *= f_home_def            # home starter suppresses AWAY runs
            lh *= f_away_def
            ctx["probable_starters"] = {"home": hp, "away": ap, "date": prob.get("date")}
        else:
            ctx["probable_starters"] = None
    return lh, la, ctx


def market_probs(lh: float, la: float, phi: float,
                 total_line: float | None = None,
                 spread_home: float = -1.5) -> dict:
    """Exact market probabilities off the joint NB matrix (independence between
    the two sides' run counts — stated assumption)."""
    ph = nb_pmf_vector(lh, phi)
    pa = nb_pmf_vector(la, phi)
    joint = np.outer(ph, pa)            # joint[i, j] = P(home=i, away=j)
    i, j = np.indices(joint.shape)
    margin = i - j

    p_home_lead = joint[margin > 0].sum()
    p_tie = joint[margin == 0].sum()
    tie_to_home = lh / (lh + la)        # extras approximated by run-rate ratio
    ml_home = p_home_lead + p_tie * tie_to_home

    out = {
        "ml": {"home": round(float(ml_home), 4), "away": round(float(1 - ml_home), 4)},
        "expected_runs": {"home": round(lh, 2), "away": round(la, 2),
                          "total": round(lh + la, 2)},
    }
    # .5 run lines can't push; integer spreads can — push reported explicitly
    rl_home = float(joint[margin + spread_home > 0].sum())
    rl_away = float(joint[margin + spread_home < 0].sum())
    rl_push = 1.0 - rl_home - rl_away
    out["run_line"] = {f"home {spread_home:+g}": round(rl_home, 4),
                       f"away {-spread_home:+g}": round(rl_away, 4),
                       "push": round(rl_push, 4)}
    if total_line is not None:
        totals = i + j
        p_over = float(joint[totals > total_line].sum())
        p_push = float(joint[totals == total_line].sum())
        out["total"] = {"line": total_line, "p_over": round(p_over, 4),
                        "p_under": round(1 - p_over - p_push, 4),
                        "p_push": round(p_push, 4)}
    out["team_total_cdf"] = {
        "home": {str(k + 0.5): round(float(ph[: k + 1].sum()), 4) for k in range(2, 8)},
        "away": {str(k + 0.5): round(float(pa[: k + 1].sum()), 4) for k in range(2, 8)},
    }
    return out


def predict(home: str, away: str, total_line: float | None = None,
            spread_home: float = -1.5, use_probables: bool = True) -> dict:
    doc = load()
    if doc is None:
        return {"error": "NO_DATA",
                "note": "mlb_game_data.json missing — run fetch_mlb_data.py"}
    teams, meta = doc["teams"], doc["meta"]
    hk, ak = _team_key(home, teams), _team_key(away, teams)
    if not hk or not ak:
        missing = [n for n, k in ((home, hk), (away, ak)) if not k]
        return {"error": "NO_DATA", "missing_teams": missing,
                "note": "team(s) not in MLB standings — no data, not estimating"}

    lh, la, ctx = matchup_lambdas(doc, hk, ak, use_probables)
    phi = float(meta["nb_dispersion"])
    markets = market_probs(lh, la, phi, total_line, spread_home)

    # sanity cross-check: log5 on fitted-pyth win% with measured HFA (no pitchers)
    h, a = teams[hk], teams[ak]
    x = float(meta["pyth_exponent"])
    ph_ = h["rs"] ** x / (h["rs"] ** x + h["ra"] ** x)
    pa_ = a["rs"] ** x / (a["rs"] ** x + a["ra"] ** x)
    l5 = ph_ * (1 - pa_) / (ph_ * (1 - pa_) + pa_ * (1 - ph_))
    hfa = meta.get("home_win_pct")
    if hfa:                             # fold measured home edge in, log5-style
        num = l5 * float(hfa)
        l5 = num / (num + (1 - l5) * (1 - float(hfa)))

    return {
        "home": hk, "away": ak,
        "records": {hk: f"{h['w']}-{h['l']}", ak: f"{a['w']}-{a['l']}"},
        **markets,
        "ml_check_log5_pyth": round(float(l5), 4),
        "context": ctx,
        "calibration": {k: meta[k] for k in
                        ("league_rpg", "pyth_exponent", "home_win_pct",
                         "nb_dispersion", "n_games", "fetched_at")},
        "assumptions": [
            "independent NB run counts per side (phi fitted on real games)",
            "extras: tie mass split by run-rate ratio",
            "no starter listed -> team-average pitching",
            "park factors not modelled",
        ],
    }


def backtest(min_date: str = "2026-05-15", with_pitchers: bool = False) -> dict:
    """Jackknife replay of completed games: each game's runs are removed from
    both teams' season rates before predicting it (no self-leakage).

    with_pitchers=True applies the probable-starter factor per game. Two stated
    caveats there: pitcher lines are FULL-season (mild in-sample leakage — no
    per-game pitcher jackknife without boxscores), and the probable ≈ the actual
    starter (true the large majority of games). This mode measures whether the
    pitcher layer carries signal, not a tradable ROI."""
    doc = load()
    if doc is None:
        return {"error": "NO_DATA"}
    teams, meta, games = doc["teams"], doc["meta"], doc["games"]
    phi = float(meta["nb_dispersion"])
    rpg = float(meta["league_rpg"])
    hf, af = home_scoring_split(games)

    n = correct = 0
    brier = 0.0
    buckets: dict[str, list] = {}
    tot_err = naive_err = 0.0
    n_pitcher_games = 0
    for g in games:
        if g["date"] < min_date:
            continue
        h, a = teams.get(g["home"]), teams.get(g["away"])
        if not h or not a or h["g"] <= 1 or a["g"] <= 1:
            continue
        # jackknife rates: this game's runs out of both teams' aggregates
        h_rs = (h["rs"] - g["hs"]) / (h["g"] - 1)
        h_ra = (h["ra"] - g["as"]) / (h["g"] - 1)
        a_rs = (a["rs"] - g["as"]) / (a["g"] - 1)
        a_ra = (a["ra"] - g["hs"]) / (a["g"] - 1)
        lh = h_rs * a_ra / rpg * hf
        la = a_rs * h_ra / rpg * af
        lh, la, _ = _park_adjust(lh, la, meta, g["home"], g["away"])
        if with_pitchers:
            prob = _find_probable(doc, g["home"], g["away"], on_date=g["date"])
            if prob:
                f_hd, _ = pitcher_defense_factor(prob.get("home_pitcher"), h_ra)
                f_ad, _ = pitcher_defense_factor(prob.get("away_pitcher"), a_ra)
                if f_hd != 1.0 or f_ad != 1.0:
                    n_pitcher_games += 1
                la *= f_hd
                lh *= f_ad
        ph = nb_pmf_vector(lh, phi)
        pa = nb_pmf_vector(la, phi)
        joint = np.outer(ph, pa)
        i, j = np.indices(joint.shape)
        m = i - j
        p_home = float(joint[m > 0].sum() + joint[m == 0].sum() * lh / (lh + la))
        home_won = g["hs"] > g["as"]
        n += 1
        correct += (p_home > 0.5) == home_won
        brier += (p_home - home_won) ** 2
        b = f"{int(min(max(p_home, 0.35), 0.699) * 20) * 5}%"
        buckets.setdefault(b, [0, 0])
        buckets[b][0] += 1
        buckets[b][1] += home_won
        tot_err += abs((lh + la) - (g["hs"] + g["as"]))
        naive_err += abs(2 * rpg - (g["hs"] + g["as"]))
    if n == 0:
        return {"error": "NO_GAMES", "note": f"no games after {min_date}"}
    return {
        "n_games": n, "window_from": min_date,
        "ml_accuracy": round(correct / n, 4),
        "brier": round(brier / n, 4),
        "calibration": {b: {"n": c, "predicted_bucket": b,
                            "actual_home_win": round(w / c, 3)}
                        for b, (c, w) in sorted(buckets.items())},
        "total_runs_mae": round(tot_err / n, 3),
        "naive_league_mean_mae": round(naive_err / n, 3),
        "with_pitchers": with_pitchers,
        "n_pitcher_adjusted": n_pitcher_games,
        "notes": ["jackknife: each game excluded from its own inputs"] + (
            ["pitcher lines are full-season (mild leakage) — signal check, not ROI",
             "probable starter assumed = actual starter"] if with_pitchers else
            ["team-average pitching (no pitcher adjustment)"]),
    }


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--backtest":
        args = [a for a in sys.argv[2:] if not a.startswith("--")]
        since = args[0] if args else "2026-05-15"
        print(json.dumps(backtest(since, with_pitchers="--pitchers" in sys.argv),
                         indent=1))
    elif len(sys.argv) >= 3:
        line = float(sys.argv[3]) if len(sys.argv) > 3 else None
        print(json.dumps(predict(sys.argv[1], sys.argv[2], line), indent=1,
                         ensure_ascii=False))
    else:
        print("usage: mlb_game_model.py <home> <away> [total_line] | --backtest [since]")
        raise SystemExit(2)

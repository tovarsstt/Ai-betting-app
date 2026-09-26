"""
winner_judge.py — the Judge ("4th agent"). Winning first, price second.

Every other engine answers ONE question with ONE lens. The Judge makes them
vote, per bettable market:

  LENS 1  MARKET   devigged sharp/consensus odds -> margin distribution.
                   The strongest benchmark: it already prices injuries/news.
  LENS 2  RATINGS  team offense/defense ratings (edge_api._formula_margin:
                   points for/against, off/def rtg). Season-level data — it does
                   NOT know today's injuries, so when it disagrees with the
                   market by more than STALE_GAP it is flagged and muted.
  LENS 3  SIM      N_SIMS Monte Carlo games drawn from the blended distribution
                   -> hit rate of every market (the number you read).
  LENS 4  AGENTS   optional probabilities from the LLM agents (quant /
                   simulation / verdict). Capped weight — words never override math.

Ranking rule (user directive + CLAUDE.md): WIN PROBABILITY FIRST. Price/EV is
shown next to every pick and breaks ties; it never outranks a likelier winner.
Guard rails, both stated in the output: a pick needs all lenses on its side
(split = flagged), and a minimum payout (MIN_DECIMAL) so "+20.5 at 1.01"
can't win the list by being unlosable.

Pure local compute — no network, no API calls. Deterministic (seeded).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

N_SIMS = 2_000_000           # user spec; vectorised (numpy) so it stays fast
MIN_DECIMAL = 1.10            # payout floor (~ -1000): blocks "+30.5 @ 1.01" junk, keeps real ML favourites

# Lens weights. Market heaviest: it is the only lens that sees injuries/news
# (repo rule: "weigh market over model on big disagreements").
W_MARKET, W_RATINGS, W_AGENTS = 0.65, 0.20, 0.15
W_ENGINE = 0.20               # sport engine lens (MLB pitchers, etc.) at prob level
W_RATINGS_STALE = 0.05
# Evidence-based ratings weight per sport. NFL walk-forward backtest 2019-2025
# (scripts/backtest_nfl.py): market MAE 9.84 vs ratings 10.32, best blend weight
# 0.00 for margins AND totals; ratings ATS 49.0% when disagreeing by 3+. So NFL
# ratings are DISPLAY-ONLY context. Sports without a backtest keep W_RATINGS.
RATINGS_WEIGHT_BY_SPORT = {"NFL": 0.0}
VETO_MIN_WEIGHT = 0.10        # a lens needs this much weight to veto a pick
# Ratings built from a PREVIOUS season carry half weight until current-season
# data is loaded (game["ratings_season"] < game["season"]).
PRIOR_SEASON_FACTOR = 0.5

# Day-of conditions (injuries / lineups) — same sizes edge_api uses
# (CONDITION_MARGIN_PTS). Applied to the RATINGS lens only: the market lens
# already prices public news. A condition without a source is ignored.
CONDITION_PTS = {
    "NFL": {"minor": 1.5, "major": 3.5}, "NBA": {"minor": 1.5, "major": 3.5},
    "WNBA": {"minor": 1.5, "major": 3.5}, "MLB": {"minor": 0.25, "major": 0.6},
    "NHL": {"minor": 0.15, "major": 0.4},
}
# NFL player OUT, by position (points of spread). Midpoints of published
# oddsmaker/market ranges: starting QB -> backup 3-7 (elite up to ~10);
# elite pass rusher / shutdown CB 0.5-1.5; starting OL / top WR 0.5-1;
# No.1 RB/WR ~1 (bettingnews.com injury guide, oddsindex.com, Yahoo Sports
# 12-oddsmaker QB survey). A per-player sourced "pts" always wins.
NFL_POSITION_PTS = {
    "QB": 5.0, "EDGE": 1.0, "CB": 1.0, "WR": 0.75, "OL": 0.75, "LT": 0.75,
    "RB": 0.75, "TE": 0.5, "S": 0.5, "LB": 0.5, "DL": 0.5, "K": 0.25,
}

# Margin std-dev per sport (edge_api.SIGMA) and the gap (pts/runs/goals)
# beyond which the ratings lens is treated as stale vs the market.
# NFL 12.75 = maximum-likelihood fit of the key-number PMF to 1,759 real games
# (2019-2025, mu = closing spread; data/benchmarks/nfl_sigma_mle.json). Others: edge_api sizes.
SIGMA = {"NFL": 12.75, "NBA": 11.5, "WNBA": 9.5, "MLB": 3.0, "NHL": 2.2}
STALE_GAP = {"NFL": 7.0, "NBA": 7.0, "WNBA": 6.0, "MLB": 1.5, "NHL": 1.0}
# Game-total std-dev around the market total (rough, public-knowledge sizes)
# NFL 13.1 = SD of (actual total - closing total), 1,759 games (nfl_backtest.json)
TOTAL_SIGMA = {"NFL": 13.1, "NBA": 12.0, "WNBA": 11.0, "MLB": 3.2, "NHL": 1.7}

# NFL final margins cluster on key numbers — same weights as lib/betting-math.ts
NFL_KEY_WEIGHTS = {0: 0.05, 1: 0.7, 2: 0.6, 3: 2.6, 4: 0.9, 5: 0.65, 6: 1.1, 7: 1.8,
                   8: 0.9, 9: 0.8, 10: 1.3, 11: 0.7, 12: 0.75, 13: 0.7, 14: 1.4,
                   15: 0.8, 16: 0.9, 17: 1.1}

GRADE_LOCK, GRADE_PICK = 0.70, 0.62   # same bands as edge_api.pick_quality


# ── Price helpers ─────────────────────────────────────────────────────────────
def to_decimal(price: float) -> float:
    """American (-110, +150) or decimal (1.91) -> decimal."""
    if price is None:
        raise ValueError("price required")
    p = float(price)
    if p >= 100:
        return p / 100.0 + 1.0
    if p <= -100:
        return 100.0 / -p + 1.0
    if 1.0 < p < 100:
        return p
    raise ValueError(f"unrecognised price {price}")


def devig_pair(a: float, b: float) -> tuple[float, float]:
    ra, rb = 1.0 / to_decimal(a), 1.0 / to_decimal(b)
    s = ra + rb
    return ra / s, rb / s


# ── Margin distributions (home margin = home score - away score) ─────────────
def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def margin_pmf(sport: str, mu: float, sigma: Optional[float] = None) -> dict[int, float]:
    """Discrete PMF of the home margin. NFL gets key-number weighting; every
    sport drops (almost all) ties — OT/extra innings/shootouts decide games."""
    s = sigma or SIGMA.get(sport, 11.0)
    lim = int(max(30, 6 * s + abs(mu)))
    pmf: dict[int, float] = {}
    for m in range(-lim, lim + 1):
        base = _norm_cdf((m + 0.5 - mu) / s) - _norm_cdf((m - 0.5 - mu) / s)
        if sport == "NFL":
            base *= NFL_KEY_WEIGHTS.get(abs(m), 1.0)
        elif m == 0:
            base = 0.0
        pmf[m] = base
    tot = sum(pmf.values())
    return {m: v / tot for m, v in pmf.items()}


def p_home_win(pmf: dict[int, float]) -> float:
    return sum(v for m, v in pmf.items() if m > 0) + 0.5 * pmf.get(0, 0.0)


def p_cover(pmf: dict[int, float], side: str, line: float) -> tuple[float, float]:
    """(win, push) for a spread bet. line is from the BET's side (e.g. -4.5)."""
    win = push = 0.0
    for m, v in pmf.items():
        r = (m if side == "home" else -m) + line
        if r > 1e-9:
            win += v
        elif abs(r) <= 1e-9:
            push += v
    return win, push


def _bisect(f, target: float, lo: float = -60.0, hi: float = 60.0) -> float:
    for _ in range(70):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fit_mu_to_ml(sport: str, p_home: float, sigma: Optional[float] = None) -> float:
    return _bisect(lambda mu: p_home_win(margin_pmf(sport, mu, sigma)), p_home)


def fit_mu_to_spread(sport: str, home_line: float, p_home_cover: float,
                     sigma: Optional[float] = None) -> float:
    def f(mu: float) -> float:
        w, p = p_cover(margin_pmf(sport, mu, sigma), "home", home_line)
        return w / (1.0 - p) if p < 1 else 0.5
    return _bisect(f, p_home_cover)


def calibrate_nfl_sigma(games: list[dict]) -> Optional[float]:
    """Pick the NFL sigma that best reconciles each game's spread with its ML
    (same method as lib/slate-sim.ts). Needs >= 3 games with both."""
    pairs = []
    for g in games:
        ml, sp = g.get("moneyline"), g.get("spread")
        if g.get("sport", "NFL") != "NFL" or not ml or not sp:
            continue
        if ml.get("home") is None or ml.get("away") is None:
            continue
        ph, _ = devig_pair(ml["home"], ml["away"])
        pc, _ = devig_pair(sp.get("home_price", -110), sp.get("away_price", -110))
        pairs.append((sp["home_line"], pc, ph))
    if len(pairs) < 3:
        return None
    best = (SIGMA["NFL"], float("inf"))
    s = 9.0
    while s <= 16.0001:
        err = sum((p_home_win(margin_pmf("NFL", fit_mu_to_spread("NFL", ln, pc, s), s)) - ph) ** 2
                  for ln, pc, ph in pairs)
        if err < best[1]:
            best = (round(s, 2), err)
        s += 0.25
    return best[0]


# ── Lenses ────────────────────────────────────────────────────────────────────
def market_mu(game: dict, sigma: float) -> Optional[float]:
    sport = game["sport"]
    mus = []
    ml = game.get("moneyline") or {}
    if game.get("ml_consensus_home") is not None:     # multi-book no-vig average
        mus.append(fit_mu_to_ml(sport, float(game["ml_consensus_home"]), sigma))
    elif ml.get("home") is not None and ml.get("away") is not None:
        ph, _ = devig_pair(ml["home"], ml["away"])
        mus.append(fit_mu_to_ml(sport, ph, sigma))
    sp = game.get("spread")
    if sp and sp.get("home_line") is not None:
        pc, _ = devig_pair(sp.get("home_price", -110), sp.get("away_price", -110))
        mus.append(fit_mu_to_spread(sport, sp["home_line"], pc, sigma))
    return sum(mus) / len(mus) if mus else None


def ratings_mu(game: dict) -> tuple[Optional[float], dict]:
    """Team offense/defense lens via edge_api (lazy import: heavy module).
    Caller may pass game['ratings_margin'] directly (tests, other engines)."""
    if game.get("ratings_margin") is not None:
        return float(game["ratings_margin"]), game.get("ratings_detail", {})
    try:
        import edge_api as ea
        if not ea.ALL_RATINGS:
            ea.load_all()
        sport = game["sport"]
        h = ea.get_ratings(sport, game["home"])
        a = ea.get_ratings(sport, game["away"])
        defaults = {"NFL": {"ppg": 22.5, "pag": 22.5, "net": 0.0}}
        if not h or not a or h == defaults.get(sport) or a == defaults.get(sport):
            return None, {"note": "no ratings for one/both teams"}
        m = float(ea._formula_margin(sport, h, a))
        if game.get("neutral"):
            m -= {"NFL": 2.5, "NBA": 2.8, "WNBA": 2.2, "MLB": 0.15}.get(sport, 0.0)
        return m, {"home": h, "away": a}
    except Exception as e:                                      # noqa: BLE001
        return None, {"note": f"ratings lens unavailable: {e}"}


def condition_adjust(game: dict) -> tuple[float, list[str]]:
    """Home-margin adjustment from cited injuries/lineup facts.
    game['conditions'] = {"home"|"away": [{"position": "QB"|..., "severity":
    "minor"|"major", "note": "...", "source": "url", "pts": optional override}]}
    Size priority: sourced per-player pts > NFL position table > severity."""
    scale = CONDITION_PTS.get(game["sport"], {})
    adj, used = 0.0, []
    for side, sign in (("home", -1.0), ("away", 1.0)):
        for c in (game.get("conditions") or {}).get(side, []):
            if not c.get("source"):
                continue                                   # uncited = ignored
            pos = str(c.get("position", "")).upper()
            if c.get("pts") is not None:
                pts = float(c["pts"])
            elif game["sport"] == "NFL" and pos in NFL_POSITION_PTS:
                pts = NFL_POSITION_PTS[pos]
            else:
                pts = scale.get(c.get("severity", ""), 0.0)
            pts *= float(c.get("pts_scale", 1.0))      # e.g. Doubtful = 0.75
            if pts:
                adj += sign * pts
                used.append(f"{game[side]}: {c.get('note', c.get('severity'))} "
                            f"({'-' if sign < 0 else '+'}{pts:g} home margin) [{c['source']}]")
    return adj, used


def ratings_total(game: dict) -> tuple[Optional[float], dict]:
    """Totals lens from team offense/defense strength (team_off_def.json):
    home pts = league_avg x home_off x away_def (and mirrored). Plus the
    pass/rush yards each defense allows (opp_defense_<sport>.json) as a
    matchup profile. Caller may pass game['ratings_total'] directly."""
    if game.get("ratings_total") is not None:
        return float(game["ratings_total"]), {}
    try:
        import json
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent / "data"
        tod = json.loads((base / "team_off_def.json").read_text()).get(game["sport"].lower(), {})
        teams, avg = tod.get("teams", {}), tod.get("league_avg")
        h, a = teams.get(game["home"].lower()), teams.get(game["away"].lower())
        if not h or not a or not avg:
            return None, {}
        hp = avg * h["off_rating"] * a["def_rating"]
        ap = avg * a["off_rating"] * h["def_rating"]
        detail = {"home_pts": round(hp, 1), "away_pts": round(ap, 1), "season": tod.get("season")}
        opp = base / f"opp_defense_{game['sport'].lower()}.json"
        if opp.exists():
            od = json.loads(opp.read_text()).get("teams", {})
            prof = {}
            for side in ("home", "away"):
                d = od.get(game[side].lower())
                if d:
                    prof[f"{side}_defense"] = {"pass_allowed_pg": round(d["pass_allowed"], 1),
                                               "rush_allowed_pg": round(d["rush_allowed"], 1)}
            if prof:
                detail["matchup_profile"] = prof
        return hp + ap, detail
    except (OSError, ValueError, KeyError, TypeError):
        return None, {}


def total_mean(game: dict) -> Optional[float]:
    t = game.get("total")
    if not t or t.get("points") is None:
        return None
    po, _ = devig_pair(t.get("over_price", -110), t.get("under_price", -110))
    s = TOTAL_SIGMA.get(game["sport"], 10.0)
    line = float(t["points"])
    # mean such that P(total > line) = po under a normal (no-push basis)
    return line + s * _inv_norm(po)


def _inv_norm(p: float) -> float:
    return _bisect(lambda z: _norm_cdf(z), p, -8.0, 8.0)


# ── Candidate markets ─────────────────────────────────────────────────────────
def candidates(game: dict) -> list[dict]:
    out = []
    ml = game.get("moneyline") or {}
    for side in ("home", "away"):
        if ml.get(side) is not None:
            out.append({"label": f"{game[side]} ML", "kind": "ml", "side": side,
                        "line": 0.0, "decimal": to_decimal(ml[side])})
    sp = game.get("spread")
    if sp and sp.get("home_line") is not None:
        hl = float(sp["home_line"])
        out.append({"label": f"{game['home']} {hl:+g}", "kind": "spread", "side": "home",
                    "line": hl, "decimal": to_decimal(sp.get("home_price", -110))})
        out.append({"label": f"{game['away']} {-hl:+g}", "kind": "spread", "side": "away",
                    "line": -hl, "decimal": to_decimal(sp.get("away_price", -110))})
    t = game.get("total")
    if t and t.get("points") is not None:
        for side in ("over", "under"):
            out.append({"label": f"{side.title()} {t['points']}", "kind": "total", "side": side,
                        "line": float(t["points"]),
                        "decimal": to_decimal(t.get(f"{side}_price", -110))})
    for o in game.get("offers") or []:            # e.g. Stake alt lines the user sees
        out.append({"label": o["label"], "kind": o["kind"], "side": o["side"],
                    "line": float(o.get("line", 0.0)), "decimal": to_decimal(o["price"]),
                    "offered": True})
    return out


def _prob_from_pmf(c: dict, pmf: dict[int, float]) -> tuple[float, float]:
    if c["kind"] == "ml":
        w, p = p_cover(pmf, c["side"], 0.0)
        return w + p / 2, 0.0          # ties ~0 in all margin sports modelled
    return p_cover(pmf, c["side"], c["line"])


def _prob_total(c: dict, mean: float, sport: str) -> tuple[float, float]:
    s = TOTAL_SIGMA.get(sport, 10.0)
    line = c["line"]
    if float(line).is_integer():
        push = _norm_cdf((line + 0.5 - mean) / s) - _norm_cdf((line - 0.5 - mean) / s)
        under = _norm_cdf((line - 0.5 - mean) / s)
    else:
        push, under = 0.0, _norm_cdf((line - mean) / s)
    over = 1.0 - under - push
    return (over if c["side"] == "over" else under), push


def grade(p: float, agree: bool, voters: Optional[dict] = None) -> str:
    if not agree:
        if voters and all(0.48 <= v <= 0.52 for v in voters.values()):
            return "COINFLIP"
        return "SPLIT"
    return "LOCK" if p >= GRADE_LOCK else "PICK" if p >= GRADE_PICK else "LEAN"


# ── The Judge ─────────────────────────────────────────────────────────────────
def judge_game(game: dict, sigma: Optional[float] = None, n_sims: int = N_SIMS,
               seed: int = 20260927, min_decimal: float = MIN_DECIMAL) -> dict:
    sport = game["sport"].upper()
    game = {**game, "sport": sport}
    s = sigma or SIGMA.get(sport, 11.0)
    flags: list[str] = []

    mu_mkt = market_mu(game, s)
    mu_rt, rt_detail = ratings_mu(game)
    if mu_mkt is None and mu_rt is None:
        return {"game": f"{game['away']} @ {game['home']}", "error": "no odds and no ratings"}
    cond_adj, cond_used = condition_adjust(game)
    if mu_rt is not None and cond_used:
        mu_rt += cond_adj
        rt_detail = {**rt_detail, "conditions_applied": cond_used}

    # Ratings trust: evidence-based cap per sport, halved for prior-season data,
    # then shrinks smoothly with disagreement vs the market (down to 5%).
    w_max = RATINGS_WEIGHT_BY_SPORT.get(sport, W_RATINGS)
    if w_max == 0:
        flags.append(f"RATINGS_DISPLAY_ONLY: {sport} backtest shows the market beats team ratings "
                     "(best blend weight 0) — ratings shown for context, no vote")
    elif game.get("ratings_season") and game.get("season") and game["ratings_season"] < game["season"]:
        w_max *= PRIOR_SEASON_FACTOR
        flags.append(f"RATINGS_PRIOR_SEASON: team ratings are from {game['ratings_season']}, "
                     f"not {game['season']} — ratings weight capped at {w_max*100:.0f}%")
    w_rt = w_max
    if mu_rt is not None and mu_mkt is not None:
        gap = abs(mu_rt - mu_mkt)
        frac = min(1.0, gap / STALE_GAP.get(sport, 7.0))
        w_rt = (0.0 if w_max == 0 else
                round(max(W_RATINGS_STALE, w_max - (w_max - W_RATINGS_STALE) * frac), 4))
        if frac >= 0.5 and w_max > 0:
            flags.append(
                f"RATINGS_DISAGREE: team ratings say home {mu_rt:+.1f}, market {mu_mkt:+.1f} — "
                "season ratings miss today's news (injuries/lineups/starters/form); "
                f"ratings weight cut to {w_rt*100:.0f}%")
    lens_mu = {k: v for k, v in (("market", mu_mkt), ("ratings", mu_rt)) if v is not None}
    wts = {"market": W_MARKET, "ratings": w_rt}
    wsum = sum(wts[k] for k in lens_mu)
    mu = sum(wts[k] * v for k, v in lens_mu.items()) / wsum

    pmf_blend = margin_pmf(sport, mu, s)
    pmf_by_lens = {k: margin_pmf(sport, v, s) for k, v in lens_mu.items()}
    # Totals: market total blended with the offense x defense ratings total,
    # same trust rules as the margin lens (prior-season cap, shrink on disagreement)
    tmean_mkt = total_mean(game)
    rt_total, tot_detail = ratings_total(game)
    tmean, w_rt_tot = tmean_mkt, 0.0
    if tmean_mkt is not None and rt_total is not None:
        frac = min(1.0, abs(rt_total - tmean_mkt) / STALE_GAP.get(sport, 7.0))
        w_rt_tot = (0.0 if w_max == 0 else
                    round(max(W_RATINGS_STALE, w_max - (w_max - W_RATINGS_STALE) * frac), 4))
        tmean = (W_MARKET * tmean_mkt + w_rt_tot * rt_total) / (W_MARKET + w_rt_tot)
        if frac >= 0.5 and w_max > 0:
            flags.append(f"TOTAL_RATINGS_DISAGREE: offense/defense ratings project {rt_total:.1f} pts, "
                         f"market {tmean_mkt:.1f} — ratings weight on totals {w_rt_tot*100:.0f}%")

    # LENS 3 — Monte Carlo: n_sims games from the blended distribution (numpy)
    rng = np.random.default_rng(seed)
    keys = np.array(sorted(pmf_blend), dtype=np.int64)
    cum = np.cumsum([pmf_blend[k] for k in keys])
    idx = np.minimum(np.searchsorted(cum, rng.random(n_sims)), len(keys) - 1)
    sim_margin = keys[idx]
    sim_total = (np.rint(rng.normal(tmean, TOTAL_SIGMA.get(sport, 10.0), n_sims))
                 if tmean is not None else None)

    agents = game.get("agents") or {}
    engine_probs = game.get("engine_probs") or {}
    rows = []
    for c in candidates(game):
        lens: dict[str, float] = {}
        push = 0.0
        if c["kind"] == "total":
            if tmean is None:
                continue
            p, push = _prob_total(c, tmean, sport)
            lens["market"] = _prob_total(c, tmean_mkt, sport)[0]
            if rt_total is not None:
                lens["ratings"] = _prob_total(c, rt_total, sport)[0]
        else:
            for k, pmf in pmf_by_lens.items():
                lens[k] = _prob_from_pmf(c, pmf)[0]
            p, push = _prob_from_pmf(c, pmf_blend)
        # simulated hit rate (a push is not a win)
        if c["kind"] == "total":
            r = (sim_total - c["line"]) if c["side"] == "over" else (c["line"] - sim_total)
        else:
            r = (sim_margin if c["side"] == "home" else -sim_margin) + c["line"]
        lens["sim"] = float(np.count_nonzero(r > 1e-9)) / n_sims
        # Probability-level lenses on top of the margin blend: sport engine
        # (e.g. MLB pitcher model) and LLM agents
        extra_w = {}
        if c["label"] in engine_probs:
            lens["engine"] = float(engine_probs[c["label"]])
            extra_w["engine"] = W_ENGINE
        if c["label"] in agents:
            lens["agents"] = float(agents[c["label"]])
            extra_w["agents"] = W_AGENTS
        consensus = (1 - sum(extra_w.values())) * p + sum(w * lens[k] for k, w in extra_w.items())
        # Veto power only for lenses carrying real weight (sim is the check, not a voter)
        w_rt_here = w_rt_tot if c["kind"] == "total" else w_rt
        voters = {k: v for k, v in lens.items()
                  if k in ("market", "engine", "agents") or (k == "ratings" and w_rt_here >= VETO_MIN_WEIGHT)}
        side_agree = all(v > 0.5 for v in voters.values())
        fair = 1.0 / consensus if consensus > 0 else None
        ev = consensus * c["decimal"] - 1.0
        rows.append({
            **c,
            "win_prob": round(consensus, 4),
            "push_prob": round(push, 4),
            "lenses": {k: round(v, 4) for k, v in lens.items()},
            "worst_lens": round(min(lens.values()), 4),
            "lenses_agree": side_agree,
            "grade": grade(consensus, side_agree, voters),
            "fair_decimal": round(fair, 2) if fair else None,
            "ev_pct": round(ev * 100, 1),
            "price_note": ("VALUE" if ev >= 0 else
                           f"OVERPRICED — fair {fair:.2f}, book pays {c['decimal']:.2f}"),
        })

    eligible = [r for r in rows if r["decimal"] >= min_decimal and r["lenses_agree"]]
    # WINNING FIRST: highest win prob; worst lens then EV only break ties
    eligible.sort(key=lambda r: (-r["win_prob"], -r["worst_lens"], -r["ev_pct"]))
    rows.sort(key=lambda r: (-r["win_prob"], -r["ev_pct"]))
    best = eligible[0] if eligible else None
    if best is None:
        flags.append(f"NO_PICK: no market pays >= {min_decimal} with every lens agreeing")

    return {
        "game": f"{game['away']} @ {game['home']}",
        "sport": sport,
        "expected_home_margin": {"blended": round(mu, 2),
                                 **{k: round(v, 2) for k, v in lens_mu.items()}},
        "weights": {"market": W_MARKET, "ratings": w_rt if mu_rt is not None else 0.0,
                    "engine": W_ENGINE if engine_probs else 0.0,
                    "agents": W_AGENTS if agents else 0.0},
        "sigma": s,
        "n_sims": n_sims,
        "ratings_detail": rt_detail,
        "total_projection": ({"blended": round(tmean, 1), "market": round(tmean_mkt, 1),
                              "ratings": round(rt_total, 1) if rt_total is not None else None,
                              "ratings_weight": w_rt_tot, **tot_detail}
                             if tmean is not None else None),
        "records": game.get("records"),
        "context": game.get("context"),
        "kickoff": game.get("kickoff"),
        "best_winning_pick": best,
        "markets": rows,
        "flags": flags,
    }


def bernoulli_parlays(board: list[dict], n_sims: int = N_SIMS, seed: int = 7,
                      sizes: tuple = (2, 3, 4), top: int = 6, pool: int = 8) -> list[dict]:
    """Best WINNING parlays: each leg is a Bernoulli trial at its consensus win
    prob (one leg per game -> independent), n_sims slips simulated per combo.
    Ranked by simulated hit rate; payout + EV shown second."""
    from itertools import combinations
    legs = [b for b in board if b.get("win_prob")][:pool]
    rng = np.random.default_rng(seed)
    out = []
    for n in sizes:
        for combo in combinations(legs, n):
            if len({c["game"] for c in combo}) < n:
                continue
            draws = rng.random((n_sims, n)) < np.array([c["win_prob"] for c in combo])
            hit = float(np.count_nonzero(draws.all(axis=1))) / n_sims
            dec = float(np.prod([c["decimal"] for c in combo]))
            out.append({
                "legs": [f"{c['label']} @ {c['decimal']:.2f} ({c['win_prob']:.0%})" for c in combo],
                "sim_hit_rate": round(hit, 4),
                "exact_hit_rate": round(float(np.prod([c["win_prob"] for c in combo])), 4),
                "decimal": round(dec, 2),
                "ev_pct": round((hit * dec - 1) * 100, 1),
                "n_sims": n_sims,
            })
    out.sort(key=lambda p: (-p["sim_hit_rate"], -p["ev_pct"]))
    # Best per leg-count so 3- and 4-leg tickets show up, not only 2-leg ones
    best_by_n = {}
    for p in out:
        best_by_n.setdefault(len(p["legs"]), p)
    top_list = out[:top]
    for p in best_by_n.values():
        if p not in top_list:
            top_list.append(p)
    return top_list


def games_from_odds_api(events: list[dict], sport: str,
                        sharp_first: tuple = ("pinnacle", "draftkings", "fanduel")) -> list[dict]:
    """The Odds API /odds payload -> Judge games. Market lens = no-vig average
    across every book quoting both sides; each pick shows the BEST price."""
    games = []
    for e in events:
        h, a = e["home_team"], e["away_team"]
        fair, best = [], {}
        for b in e.get("bookmakers", []):
            m = next((m for m in b.get("markets", []) if m["key"] == "h2h"), None)
            if not m:
                continue
            ph = next((o["price"] for o in m["outcomes"] if o["name"] == h), None)
            pa = next((o["price"] for o in m["outcomes"] if o["name"] == a), None)
            if ph is not None and pa is not None and len(m["outcomes"]) == 2:
                fair.append(devig_pair(ph, pa)[0])
            for side, p in (("home", ph), ("away", pa)):
                if p is not None and (side not in best or to_decimal(p) > to_decimal(best[side])):
                    best[side] = p

        def pick(key):
            for bk in sharp_first:
                b = next((b for b in e.get("bookmakers", []) if b["key"] == bk), None)
                m = b and next((m for m in b["markets"] if m["key"] == key), None)
                if m:
                    return m
            return next((m for b in e.get("bookmakers", []) for m in b["markets"] if m["key"] == key), None)

        sp, tt = pick("spreads"), pick("totals")
        hs = sp and next((o for o in sp["outcomes"] if o["name"] == h), None)
        as_ = sp and next((o for o in sp["outcomes"] if o["name"] == a), None)
        ov = tt and next((o for o in tt["outcomes"] if o["name"] == "Over"), None)
        un = tt and next((o for o in tt["outcomes"] if o["name"] == "Under"), None)
        games.append({
            "sport": sport, "home": h, "away": a, "commence_time": e.get("commence_time"),
            "moneyline": best,
            "ml_consensus_home": sum(fair) / len(fair) if fair else None,
            "spread": ({"home_line": hs["point"], "home_price": hs["price"],
                        "away_price": as_["price"] if as_ else -110}
                       if hs and hs.get("point") is not None else None),
            "total": ({"points": ov["point"], "over_price": ov["price"],
                       "under_price": un["price"] if un else -110}
                      if ov and ov.get("point") is not None else None),
        })
    return games


def judge_slate(games: list[dict], n_sims: int = N_SIMS, seed: int = 20260927,
                min_decimal: float = MIN_DECIMAL) -> dict:
    # NFL sigma is fitted to real outcomes (SIGMA["NFL"]), not to the slate's own lines
    nfl_sigma = SIGMA["NFL"] if any(g.get("sport", "NFL").upper() == "NFL" for g in games) else None
    results = []
    for i, g in enumerate(games):
        sport = g.get("sport", "NFL").upper()
        sig = nfl_sigma if sport == "NFL" and nfl_sigma else None
        if sport == "MLB":
            import judge_engines as je        # pitcher-model lens
            results.append(je.judge_mlb(g, n_sims=n_sims, sigma=sig, seed=seed + i,
                                        min_decimal=min_decimal))
            continue
        results.append(judge_game(g, sigma=sig, n_sims=n_sims, seed=seed + i,
                                  min_decimal=min_decimal))
    board = [r["best_winning_pick"] | {"game": r["game"]}
             for r in results if r.get("best_winning_pick")]
    board.sort(key=lambda b: (-b["win_prob"], -b["worst_lens"], -b["ev_pct"]))
    return {"nfl_sigma": nfl_sigma, "rule": "win probability first; price/EV second",
            "board": board,
            "winning_parlays": bernoulli_parlays(board, n_sims=n_sims),
            "games": results}

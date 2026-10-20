"""
pwin_ensemble.py — THE registry behind the P(win) Rule in CLAUDE.md.

P(win) is never one formula: every applicable tool runs, each reports its own probabilities, and the
spread between them is shown. A tool that cannot run is listed with the reason (never dropped silently,
never invented). Tool kinds:
  model   -> averaged (equal weight) into the model estimate
  market  -> devigged market views, averaged into the market estimate
  flag    -> not a probability (e.g. chaos engine draw risk); shown as a warning
Final P = MODEL_WEIGHT * model_mean + (1 - MODEL_WEIGHT) * market_mean (a judgement, NOT fitted:
no closing-line history is in the repo to fit it on).
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import betting_math as bm  # noqa: E402
import calibrate_ucl as cu  # noqa: E402
import chaos_engine as ce  # noqa: E402
import eigen_ratings as er  # noqa: E402
import nba_stack as ns  # noqa: E402
import poisson_model as pm  # noqa: E402
import poisson_regression as preg  # noqa: E402
import soccer_markets as sm  # noqa: E402
import sport_math as spm  # noqa: E402
import ucl_model as um  # noqa: E402

MODEL_WEIGHT = 0.5
DATA = Path(__file__).parent.parent / "data"
N_SIMS = 200_000
SEED = 20261020


@dataclass
class ToolOut:
    name: str
    family: str          # e.g. "poisson", "monte-carlo", "binomial", "elo", "market"
    kind: str            # model | market | flag
    probs: dict | None   # {"home","draw"?,"away"} or None when not run
    note: str = ""


# Tools fed by the SAME information are grouped: averaged inside the group first, then across groups,
# so e.g. Poisson / Monte Carlo / Skellam off one Elo count once, not three times.
GROUPS = {
    "elo_poisson_dixon_coles": "elo-goal", "elo_monte_carlo_200k": "elo-goal", "elo_skellam": "elo-goal",
    "poisson_regression": "poisson-regression", "eigenvector_keener": "eigenvector", "binomial_wdl_rates": "binomial",
    "stacked_elo_form_context": "elo-form", "elo_only": "elo-form", "form_only": "elo-form",
    "normal_margin": "margin-normal", "monte_carlo_margin": "margin-normal", "beta_binomial_log5": "binomial",
    "devig_multiplicative": "market-devig", "devig_power": "market-devig", "devig_shin": "market-devig",
    "sport_math_anchored_dc": "market-anchored", "spread_implied_normal": "market-spread",
}


def _norm(p: dict) -> dict:
    s = sum(p.values())
    return {k: v / s for k, v in p.items()}


def _not_run(name: str, family: str, kind: str, why: str) -> ToolOut:
    return ToolOut(name, family, kind, None, f"NOT RUN: {why}")


# ═════════════════════════ SOCCER ═════════════════════════
@dataclass
class SoccerCtx:
    rows: list
    elo: dict
    elo_model: um.EloGoalModel
    games: dict
    preg: object
    eig: object
    eig_model: um.EloGoalModel
    by_team: dict = field(default_factory=lambda: defaultdict(list))


def build_soccer_ctx(paths: list[Path]) -> SoccerCtx:
    raw = cu.load_results(*paths)
    rows = [{**r, "home_team": cu.normalize(r["home_team"]), "away_team": cu.normalize(r["away_team"])} for r in raw]
    rows.sort(key=lambda r: r["date"])
    elo, samples = um.build_elo(rows)
    elo_model = um.calibrate_pre(samples)
    pr = preg.fit(rows)
    eg = er.fit(rows)
    es = [{**s, "eh": 400 * math.log(max(eg.ratings.get(s["home_team"], 1e-9), 1e-9)),
           "ea": 400 * math.log(max(eg.ratings.get(s["away_team"], 1e-9), 1e-9))} for s in samples]
    ctx = SoccerCtx(rows, elo, elo_model, {}, pr, eg, um.calibrate_pre(es))
    for r in rows:
        ctx.games[r["home_team"]] = ctx.games.get(r["home_team"], 0) + 1
        ctx.games[r["away_team"]] = ctx.games.get(r["away_team"], 0) + 1
        ctx.by_team[r["home_team"]].append(("H", int(r["home_score"]), int(r["away_score"])))
        ctx.by_team[r["away_team"]].append(("A", int(r["away_score"]), int(r["home_score"])))
    return ctx


def _matrix_probs(lh: float, la: float) -> dict:
    b = sm.derive_markets(sm.score_matrix(lh, la))
    return {"home": b.home_win, "draw": b.draw, "away": b.away_win}


def _wdl_counts(ctx: SoccerCtx, team: str, venue: str, last: int = 30) -> tuple[int, int, int] | None:
    res = [(f, a) for v, f, a in ctx.by_team.get(team, []) if v == venue][-last:]
    if len(res) < 6:
        return None
    return sum(f > a for f, a in res), sum(f == a for f, a in res), sum(f < a for f, a in res)


def soccer_tools(ctx: SoccerCtx, home: str, away: str, market: dict | None, total_line: float | None) -> list[ToolOut]:
    out: list[ToolOut] = []
    h, a = cu.normalize(home), cu.normalize(away)
    # 1-3: Elo -> goals (analytic Dixon-Coles, Monte Carlo, Skellam)
    if h in ctx.elo and a in ctx.elo:
        lh, la = um.lambdas(ctx.elo_model, ctx.elo[h], ctx.elo[a])
        note = f"λ {lh:.2f}-{la:.2f}, calibrated={ctx.elo_model.calibrated}"
        out.append(ToolOut("elo_poisson_dixon_coles", "poisson", "model", _matrix_probs(lh, la), note))
        sim = sm.simulate_match(lh, la, n_sims=N_SIMS, seed=SEED)["simulated_1x2"]
        out.append(ToolOut("elo_monte_carlo_200k", "monte-carlo", "model",
                           {k: sim[k]["prob"] for k in ("home", "draw", "away")}, f"{N_SIMS:,} sims from the same matrix"))
        out.append(ToolOut("elo_skellam", "poisson", "model",
                           {"home": float(stats.skellam.sf(0, lh, la)), "draw": float(stats.skellam.pmf(0, lh, la)),
                            "away": float(stats.skellam.cdf(-1, lh, la))}, "exact goal-difference law, independent Poissons"))
    else:
        miss = home if h not in ctx.elo else away
        for n, f in (("elo_poisson_dixon_coles", "poisson"), ("elo_monte_carlo_200k", "monte-carlo"), ("elo_skellam", "poisson")):
            out.append(_not_run(n, f, "model", f"no Elo rating for {miss}"))
    # 4: data-fit Poisson regression (team attack/defence, all competitions)
    pt = ctx.preg.teams
    if h in pt and a in pt and pt[h].get("n_matches", 0) >= 8 and pt[a].get("n_matches", 0) >= 8:
        lh, la = preg.lambdas_for(ctx.preg, h, a, neutral=False)
        out.append(ToolOut("poisson_regression", "poisson", "model", _matrix_probs(lh, la), f"λ {lh:.2f}-{la:.2f}, per-team attack/defence"))
    else:
        out.append(_not_run("poisson_regression", "poisson", "model", "club has <8 matches in the fit"))
    # 5: eigenvector (Keener) ratings -> goals
    er_, ea_ = ctx.eig.ratings.get(h), ctx.eig.ratings.get(a)
    if er_ and ea_:
        lh, la = um.lambdas(ctx.eig_model, 400 * math.log(er_), 400 * math.log(ea_))
        out.append(ToolOut("eigenvector_keener", "eigenvector", "model", _matrix_probs(lh, la), f"λ {lh:.2f}-{la:.2f}; goal map fit in-sample"))
    else:
        out.append(_not_run("eigenvector_keener", "eigenvector", "model", "club not in rating graph"))
    # 6: binomial / Bernoulli / Dirichlet W-D-L rates by venue
    ch, ca = _wdl_counts(ctx, h, "H"), _wdl_counts(ctx, a, "A")
    if ch and ca:
        pri = np.array([0.45, 0.26, 0.29]) * 6.0
        rh = (np.array(ch) + pri) / (sum(ch) + 6.0)          # home team's home record: W,D,L
        ra = (np.array(ca) + pri) / (sum(ca) + 6.0)          # away team's away record: W,D,L
        p = _norm({"home": (rh[0] + ra[2]) / 2, "draw": (rh[1] + ra[1]) / 2, "away": (rh[2] + ra[0]) / 2})
        lo, hi = bm.wilson(ch[0], sum(ch))
        out.append(ToolOut("binomial_wdl_rates", "binomial", "model", p, f"home-team home win rate {ch[0]}/{sum(ch)} (Wilson95 {lo:.2f}-{hi:.2f})"))
    else:
        out.append(_not_run("binomial_wdl_rates", "binomial", "model", "fewer than 6 venue matches for a club"))
    # market tools
    if market and all(k in market for k in ("home", "draw", "away")):
        dec = [am(market[k]) for k in ("home", "draw", "away")]
        for name, fn in (("devig_multiplicative", bm.devig_multiplicative), ("devig_power", bm.devig_power), ("devig_shin", bm.devig_shin)):
            p = fn(dec)
            out.append(ToolOut(name, "market", "market", dict(zip(("home", "draw", "away"), map(float, p))), f"overround {bm.overround(dec)*100:.1f}%"))
        pw = bm.devig_power(dec)
        if total_line:
            r = spm.price_game("soccer", float(total_line), float(pw[0]), p_draw=float(pw[1]))
            out.append(ToolOut("sport_math_anchored_dc", "market", "market", {"home": r["home"], "draw": r["draw"], "away": r["away"]},
                               "Dixon-Coles refit per match to market home+draw (total line = O/U line, approximate)"))
        else:
            out.append(_not_run("sport_math_anchored_dc", "market", "market", "no total line"))
        # chaos engine (flag): draw-risk, from real GF/GA per game
        try:
            def tf(n, raw):
                g = ctx.games.get(n, 0)
                gf = sum(f for _, f, _ in ctx.by_team.get(n, [])); ga = sum(x for _, _, x in ctx.by_team.get(n, []))
                return ce.TeamForm(raw, gf, ga, g)
            fav_dec = min(dec[0], dec[2])
            res = ce.assess_match(ce.MatchInput(tf(h, home), tf(a, away), float(pw[0]), float(pw[1]), float(pw[2]), fav_dec, dec[1]))
            out.append(ToolOut("chaos_engine_draw_risk", "chaos", "flag", None,
                               f"draw score {res.draw_score:.2f}, grade {res.grade}, upset {res.upset_level}"))
        except Exception as e:  # keep the report alive; say why
            out.append(_not_run("chaos_engine_draw_risk", "chaos", "flag", f"{type(e).__name__}: {e}"))
    else:
        for n in ("devig_multiplicative", "devig_power", "devig_shin", "sport_math_anchored_dc", "chaos_engine_draw_risk"):
            out.append(_not_run(n, "market", "market", "no 3-way moneyline"))
    return out


# ═════════════════════════ NBA ═════════════════════════
@dataclass
class NbaCtx:
    st: object
    stacker: object
    games: list
    sigma: float
    home_logit: float
    last: dict = field(default_factory=lambda: defaultdict(list))


def build_nba_ctx(game_files: list[Path]) -> NbaCtx:
    g = ns.load_games(*game_files)
    st, stk = ns.fit_final(g)
    cal = spm._cal().get("nba", {})
    c = NbaCtx(st, stk, g, float(cal.get("sigma_margin", 12.0)), 0.0)
    wins = sum(x["hs"] > x["as"] for x in g)
    c.home_logit = math.log(wins / (len(g) - wins))
    for x in g:
        c.last[x["home"]].append(int(x["hs"] > x["as"]))
        c.last[x["away"]].append(int(x["as"] > x["hs"]))
    return c


def am(a: int) -> float:
    return a / 100 + 1 if a > 0 else 100 / -a + 1


def nba_tools(ctx: NbaCtx, home: str, away: str, day: date, market: dict | None, spread: float | None) -> list[ToolOut]:
    out: list[ToolOut] = []
    st = ctx.st
    if home not in st.teams or away not in st.teams:
        miss = home if home not in st.teams else away
        names = ["stacked_elo_form_context", "elo_only", "form_only", "normal_margin", "monte_carlo_margin", "beta_binomial_log5"]
        return [_not_run(n, "nba", "model", f"{miss} not in rating history") for n in names]
    season = day.year if day.month >= 9 else day.year - 1
    if season != st.season:
        st.new_season(season, max(1, season - st.season))
    f = st.features(home, away, day)
    p_st = float(ctx.stacker.predict([f])[0])
    out.append(ToolOut("stacked_elo_form_context", "stacking", "model", {"home": p_st, "away": 1 - p_st},
                       f"Elo diff {f['elo_diff']:+.0f}, form diff {f['form_diff']:+.1f}, rest {f['rest_diff']:+.0f}"))
    pa, pb = ns.base_a(f), ns.base_b(f)
    out.append(ToolOut("elo_only", "elo", "model", {"home": pa, "away": 1 - pa}))
    out.append(ToolOut("form_only", "form", "model", {"home": pb, "away": 1 - pb}, "last-5 margin"))
    m = (f["elo_diff"] + ns.HOME_ELO) / 28.0          # ~28 Elo per point of spread
    out.append(ToolOut("normal_margin", "normal", "model", {"home": float(stats.norm.cdf(m / ctx.sigma)), "away": float(stats.norm.sf(m / ctx.sigma))},
                       f"expected margin {m:+.1f}, σ {ctx.sigma:.1f} (calibrated on closing lines)"))
    rng = np.random.default_rng(SEED)
    mu = rng.normal(m, 2.5, N_SIMS)                    # rating uncertainty (±2.5 pts)
    marg = rng.normal(mu, ctx.sigma)
    ph = float((marg > 0).mean())
    out.append(ToolOut("monte_carlo_margin", "monte-carlo", "model", {"home": ph, "away": 1 - ph}, f"{N_SIMS:,} sims, rating uncertainty ±2.5 pts"))
    rh, ra = ctx.last[home][-20:], ctx.last[away][-20:]
    if len(rh) >= 8 and len(ra) >= 8:
        bh, ba = (sum(rh) + 1) / (len(rh) + 2), (sum(ra) + 1) / (len(ra) + 2)    # Beta(1,1) posterior mean
        log5 = (bh - bh * ba) / (bh + ba - 2 * bh * ba)
        z = math.log(log5 / (1 - log5)) + ctx.home_logit
        p = 1 / (1 + math.exp(-z))
        out.append(ToolOut("beta_binomial_log5", "binomial", "model", {"home": p, "away": 1 - p}, f"last-20 win rates {bh:.2f} vs {ba:.2f}, log5 + home edge from data"))
    else:
        out.append(_not_run("beta_binomial_log5", "binomial", "model", "fewer than 8 games of history"))
    out.append(_not_run("team_ratings_ridge", "ridge", "model", "needs the closing-line history set (not in repo)"))
    if market and "home" in market and "away" in market:
        dec = [am(market["home"]), am(market["away"])]
        for name, fn in (("devig_multiplicative", bm.devig_multiplicative), ("devig_power", bm.devig_power), ("devig_shin", bm.devig_shin)):
            p = fn(dec)
            out.append(ToolOut(name, "market", "market", {"home": float(p[0]), "away": float(p[1])}, f"overround {bm.overround(dec)*100:.1f}%"))
        if spread is not None:
            ps = float(stats.norm.cdf(-spread / ctx.sigma))
            out.append(ToolOut("spread_implied_normal", "market", "market", {"home": ps, "away": 1 - ps}, f"spread {spread:+.1f}, σ {ctx.sigma:.1f}"))
    else:
        out.append(_not_run("devig_*", "market", "market", "no moneyline"))
    return out


# ═════════════════════════ AGGREGATION ═════════════════════════
def aggregate(tools: list[ToolOut], w_model: float = MODEL_WEIGHT) -> dict:
    """model_mean / market_mean / final, per outcome, plus min-max spread across model tools."""
    def mean(kind: str):
        ts = [t for t in tools if t.kind == kind and t.probs]
        if not ts:
            return None, 0, {}
        keys = list(ts[0].probs)
        groups: dict[str, list] = defaultdict(list)
        for t in ts:
            groups[GROUPS.get(t.name, t.name)].append(t.probs)
        gm = [{k: float(np.mean([p[k] for p in ps])) for k in keys} for ps in groups.values()]
        mu = {k: float(np.mean([g[k] for g in gm])) for k in keys}
        sp = {k: float(max(t.probs[k] for t in ts) - min(t.probs[k] for t in ts)) for k in keys}
        return _norm(mu), len(ts), sp
    mm, nm, spread = mean("model")
    mk, nk, _ = mean("market")
    if mm is None and mk is None:
        return {"error": "no tool produced a probability"}
    if mm is None:
        final = mk
    elif mk is None:
        final = mm
    else:
        final = _norm({k: w_model * mm[k] + (1 - w_model) * mk[k] for k in mm})
    return {"final": final, "model_mean": mm, "market_mean": mk, "n_model_tools": nm, "n_market_tools": nk, "model_spread": spread,
            "not_run": [t.name for t in tools if t.probs is None and t.kind != "flag"]}


def tools_table(tools: list[ToolOut]) -> str:
    lines = []
    for t in tools:
        if t.probs:
            ps = " / ".join(f"{k[0].upper()} {v*100:5.1f}%" for k, v in t.probs.items())
            lines.append(f"    [{t.kind:6}] {t.name:26} {ps}   {t.note}")
        else:
            lines.append(f"    [{t.kind:6}] {t.name:26} {t.note}")
    return "\n".join(lines)

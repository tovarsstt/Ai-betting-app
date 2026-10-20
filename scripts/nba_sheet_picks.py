"""
nba_sheet_picks.py — price a pasted NBA sheet (ML, spread ladder, total ladder, team totals, margin buckets) with the
full toolkit (CLAUDE.md P(win) Rule + Total-Anchor Rule) and Stake's halftime-refund promo on the Winner market.

Margin: M ~ N(m, sigma_m) with sigma_m ~13.1 (post-2018 residual sd vs the closing line, derived from the stored held-out log-lik; the 11.77 train value is stale). m_final = 50% model-tool mean
(stacked Elo+form+context, Elo, form, normal margin, Monte Carlo margin, Beta-Binomial log5) + 50% market margin, where the
market margin is fitted to the whole SPREAD LADDER (spread line predicts the winner better than the devigged ML on those
18.5k games: logloss 0.6103 vs 0.6118). Total: T = market total fitted to the total ladder (Total-Anchor Rule: the model
has no independent total), sigma_t = 17.47. Team totals use home=(T+M)/2, away=(T-M)/2 with corr(M,total) ~ -0.01.
Order: P(win) first -> odds/payout -> EV last; ML rows also show EV with the halftime refund.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm

import betting_math as bm
import nba_halftime as nh
import pwin_ensemble as pe

DATA = Path(__file__).parent.parent / "data"
SIGMA_M, SIGMA_T, RHO_MT = pe.nba_sigma_margin(pe.spm._cal().get('nba', {})), 17.47, -0.009   # sigma_m ~13.1 (post-2018 held-out residual sd); sigma_t train-only
W_MODEL_FRESH = 0.5      # Total/P(win) Rule weight when the ratings include games of the current season
W_MODEL_STALE = 0.2      # judgement: ratings are LAST season's (rosters changed, e.g. LeBron to PHI) -> lean on the market
NEAR_EVEN = 0.12         # fit the market margin/total only on ladder rows whose devigged prob is within 0.5 +/- this


def two_way(o: list[float]) -> tuple[float, float]:
    p = bm.devig_power(o)
    return float(p[0]), float(p[1])


def fit_margin(spread: dict) -> float:
    """Home expected margin m so that P(home covers line L) = Φ((m+L)/σ) matches every devigged ladder row."""
    rows = [(float(L), two_way(o)[0]) for L, o in spread.items()]
    rows = [r for r in rows if abs(r[1] - 0.5) <= NEAR_EVEN] or rows       # tails carry the book's longshot-side margin
    return float(minimize_scalar(lambda m: sum((norm.cdf((m + L) / SIGMA_M) - p) ** 2 for L, p in rows), bounds=(-25, 25), method="bounded").x)


def fit_total(total: dict) -> float:
    rows = [(float(L), two_way(o)[0]) for L, o in total.items()]            # P(over L)
    rows = [r for r in rows if abs(r[1] - 0.5) <= NEAR_EVEN] or rows
    return float(minimize_scalar(lambda T: sum((1 - norm.cdf((L - T) / SIGMA_T) - p) ** 2 for L, p in rows), bounds=(190, 260), method="bounded").x)


def to_am(d: float) -> int:
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))


def row(match, market, pick, p, dec, extra=None):
    r = {"league": "NBA", "match": match, "market": market, "pick": pick, "p_win": float(p), "decimal": dec, "payout_10": 10 * dec, "ev": float(p * dec - 1)}
    r.update(extra or {})
    return r


def price_game(nctx, name: str, g: dict, day, params: dict) -> tuple[list[dict], dict]:
    home, away = g["home"], g["away"]
    m_mkt = fit_margin(g["spread"])
    T = fit_total(g["total"])
    ml_am = {"home": to_am(g["ml"][0]), "away": to_am(g["ml"][1])}
    tools = pe.nba_tools(nctx, home, away, day, ml_am, None)
    agg = pe.aggregate(tools)
    p_model = agg["model_mean"]["home"] if agg.get("model_mean") else None
    m_model = float(SIGMA_M * norm.ppf(min(max(p_model, 1e-4), 1 - 1e-4))) if p_model is not None else None
    stale = all(nctx.st.teams[t].gp < 10 for t in (home, away) if t in nctx.st.teams)
    w = W_MODEL_STALE if stale else W_MODEL_FRESH
    m = w * m_model + (1 - w) * m_mkt if m_model is not None else m_mkt
    info = {"w_model": w, "stale": stale, "gap": (m_model - m_mkt) if m_model is not None else None, "m_market": m_mkt, "m_model": m_model, "m_final": m, "T": T, "tools": tools, "agg": agg,
            "ratings_as_of": nctx.st.as_of, "p_ml_market": two_way(g["ml"])[0]}
    rows: list[dict] = []
    # ── Winner (ML) — with halftime-refund promo
    ph = float(norm.cdf(m / SIGMA_M))
    for side, p, dec, lab, mm in (("home", ph, g["ml"][0], f"{home} gana (incl. prórroga)", m), ("away", 1 - ph, g["ml"][1], f"{away} gana (incl. prórroga)", -m)):
        pr = nh.refund_prob(mm, params)
        rows.append(row(name, "Ganador", lab, p, dec, {"p_refund": pr, "ev_promo": nh.ev_with_refund(p, dec, pr), "side": side}))
    # ── Spread ladder
    for L, (oh, oa) in g["spread"].items():
        L = float(L)
        p_home = float(norm.cdf((m + L) / SIGMA_M))
        rows.append(row(name, "Hándicap", f"{home} {L:+g}", p_home, oh))
        rows.append(row(name, "Hándicap", f"{away} {-L:+g}", 1 - p_home, oa))
    # ── Total ladder (market-anchored)
    for L, (oo, ou) in g["total"].items():
        L = float(L)
        po = float(1 - norm.cdf((L - T) / SIGMA_T))
        rows.append(row(name, "Total", f"Más de {L:g}", po, oo, {"anchored": True}))
        rows.append(row(name, "Total", f"Menos de {L:g}", 1 - po, ou, {"anchored": True}))
    # ── Team totals
    sd_team = float(np.sqrt((SIGMA_T ** 2 + SIGMA_M ** 2 + 2 * RHO_MT * SIGMA_T * SIGMA_M) / 4))
    for key, mean, lab in (("team_total_home", (T + m) / 2, home), ("team_total_away", (T - m) / 2, away)):
        for L, (oo, ou) in g[key].items():
            L = float(L)
            po = float(1 - norm.cdf((L - mean) / sd_team))
            rows.append(row(name, "Total del equipo", f"{lab} más de {L:g}", po, oo, {"anchored": True}))
            rows.append(row(name, "Total del equipo", f"{lab} menos de {L:g}", 1 - po, ou, {"anchored": True}))
    # ── Margin of victory buckets (integer margins)
    cuts = {"1_5": (0.5, 5.5), "6_10": (5.5, 10.5), "11p": (10.5, 80.0)}
    # A regulation tie (|M|<0.5, ~3% of games) goes to OT and ends with a small margin: give that mass to the 1-5 buckets.
    # OT winner = 0.5 + 0.3*(P(home wins) - 0.5): five minutes dilute the strength edge (assumption, stated).
    p_tie = float(norm.cdf((0.5 - m) / SIGMA_M) - norm.cdf((-0.5 - m) / SIGMA_M))
    p_home_ot = 0.5 + 0.3 * (float(norm.cdf(m / SIGMA_M)) - 0.5)
    for side, sign, lab in (("home", 1, home), ("away", -1, away)):
        for k, (lo, hi) in cuts.items():
            mu = sign * m
            p = float(norm.cdf((hi - mu) / SIGMA_M) - norm.cdf((lo - mu) / SIGMA_M))
            if k == "1_5":
                p += p_tie * (p_home_ot if side == "home" else 1 - p_home_ot)
            dec = g["mov"][f"{side}_{k}"]
            rows.append(row(name, "Margen de victoria", f"{lab} por {k.replace('_', '-').replace('p', '+')}", p, dec))
    return rows, info


def main() -> None:
    import datetime
    sheet = json.loads(Path(sys.argv[1]).read_text())["matches"]
    day = datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.date.today()
    params = nh.load_params()
    nctx = pe.build_nba_ctx([DATA / "nba_historical.csv", DATA / "nba_games_2526.csv"])
    allrows, infos = [], {}
    for name, g in sheet.items():
        r, info = price_game(nctx, name, g, day, params)
        allrows += r; infos[name] = info
    print(f"=== NBA === (ratings as of {nctx.st.as_of}: LAST season, offseason moves not captured) | halftime params: {'fitted on real half scores' if params.get('fitted') else 'DEFAULT (not fitted)'}")
    for name, info in infos.items():
        mm = f"{info['m_model']:+.1f}" if info["m_model"] is not None else "n/a"
        print(f"- {name}: market margin {info['m_market']:+.1f} (home), model-tool margin {mm} (weight {info['w_model']:.0%}"
              f"{', STALE ratings' if info['stale'] else ''}), final {info['m_final']:+.1f}; market total {info['T']:.1f} (anchored)")
    ml = [r for r in allrows if r["market"] == "Ganador"]
    print("\nGANADOR — P(win) first (EV last; with and without the halftime-refund promo):")
    for r in sorted(ml, key=lambda r: -r["p_win"]):
        print(f"  {r['pick']} [{r['match']}]  P(win) {r['p_win']*100:.1f}% | cuota {r['decimal']:.2f} -> $10 pagan ${r['payout_10']:.2f} | EV {r['ev']*100:+.1f}% | con reembolso (P {r['p_refund']*100:.2f}%) EV {r['ev_promo']*100:+.1f}%")
    pos = sorted([r for r in allrows if r.get("ev_promo", r["ev"]) > 0 and r["market"] != "Ganador"], key=lambda r: -r["p_win"])
    print(f"\nOTROS MERCADOS con EV > 0 ({len(pos)} de {len(allrows)}), por P(win):")
    for r in pos[:14]:
        print(f"  {r['pick']} [{r['match']} · {r['market']}]  P(win) {r['p_win']*100:.1f}% | {r['decimal']:.2f} -> $10 pagan ${r['payout_10']:.2f} | EV {r['ev']*100:+.1f}%")
    out = DATA / "slips" / "nba_rows_latest.json"
    out.write_text(json.dumps([{k: v for k, v in r.items()} for r in allrows], indent=1))


if __name__ == "__main__":
    main()

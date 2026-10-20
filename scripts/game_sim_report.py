"""
game_sim_report.py — "what does the simulation say" per game: final score, win prob, scoreline/margin spread, stats.

UCL (first): final 1X2 = the full-toolkit blend from sheet_picks (50% model tools / 50% devigged market). The score grid
keeps the MARKET total (Total-Anchor Rule) and fixes only the home/away split so that P(H)-P(A) equals that blend;
400k scorelines are then drawn from the Dixon-Coles matrix.
NBA: market margin/total blended with the stale-ratings model weight (nba_sheet_picks), quarter-by-quarter Monte Carlo
(nba_flow_sim, 400k). Player stat means come from the market line moved to the final P(over) from props_picks.

Injuries / lineups are NOT inputs to the model: the sheet odds already carry them (pasted after the official reports).
Optional hand-set SCENARIOS (assumptions, labelled) show how far a star absence could move a game.

    python3 scripts/game_sim_report.py data/sheets/2026-10-20_ucl.json data/sheets/2026-10-20_nba.json data/sheets/2026-10-20_nba_props.json 2026-10-20
"""
from __future__ import annotations

import datetime
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm

import nba_flow_sim as fs
import nba_halftime as nh
import nba_sheet_picks as nsp
import props_picks as pp
import pwin_ensemble as pe
import sheet_picks as sp
import soccer_markets as sm

DATA = Path(__file__).parent.parent / "data"
N = 400_000
UCL_SCENARIOS = {  # ASSUMPTIONS, not fitted: expected-goals change for the named team if the player is out
    "Manchester City vs AEK Athens": ("home", -0.30, "Haaland fuera (duda, supuesto: -0.30 goles esperados de City)"),
}


def split_for(total: float, margin_target: float) -> tuple[float, float]:
    """(λh, λa) with λh+λa = total whose Dixon-Coles P(H)-P(A) equals margin_target."""
    def gap(lh):
        b = sm.derive_markets(sm.score_matrix(lh, total - lh))
        return (b.home_win - b.away_win - margin_target) ** 2
    lh = minimize_scalar(gap, bounds=(0.15, total - 0.15), method="bounded").x
    return float(lh), float(total - lh)


def sample_scores(lh: float, la: float, seed: int = 7) -> np.ndarray:
    mat = np.array(sm.score_matrix(lh, la))
    flat = mat.ravel() / mat.sum()
    idx = np.random.default_rng(seed).choice(flat.size, size=N, p=flat)
    return np.column_stack(np.divmod(idx, mat.shape[1]))


def ucl_block(sheet: dict) -> None:
    soc = DATA / "soccer"
    ctx = pe.build_soccer_ctx([soc / "club_results.csv", soc / "extra_league_results.csv", soc / "uefa_results.csv"])
    print("=== UCL === simulación por partido (P(win) primero; EV no se usa)\n")
    for name, m in sheet.items():
        rows, notrun, _ = sp.price_match(ctx, name, m)
        p = {r["key"]: r["p_win"] for r in rows if r["key"] in ("H", "D", "A")}
        pm = {r["key"]: r["p_model"] for r in rows if r["key"] in ("H", "D", "A")}
        pw = sp.bm.devig_power(m["x12"])
        ou = sp.two_way(m["ou"]["2.5"])
        lh0, la0 = sp.anchored_lambdas(pw, ou[0])
        total = lh0 + la0
        lh, la = split_for(total, p["H"] - p["A"])
        sc = sample_scores(lh, la)
        h, a = sc[:, 0], sc[:, 1]
        top = Counter(map(tuple, sc.tolist())).most_common(4)
        n_tools = len(rows[0]["per_tool"]) if rows else 0
        print(f"{name}  [{m['home']} local]")
        print(f"  P(win) final: {m['home']} {p['H']*100:.1f}% | empate {p['D']*100:.1f}% | {m['away']} {p['A']*100:.1f}%"
              f"   (solo modelos {pm['H']*100:.0f}/{pm['D']*100:.0f}/{pm['A']*100:.0f}; {n_tools} herramientas)")
        hrow = next(r for r in rows if r["key"] == "H")
        print("  P(local) por herramienta: " + ", ".join(f"{k.replace('elo_poisson_dixon_coles','Elo-DC').replace('poisson_regression','Poisson-reg').replace('eigenvector_keener','eigenvector').replace('binomial_wdl_rates','binomial').replace('elo_skellam','Skellam')} {v*100:.0f}%" for k, v in hrow["per_tool"].items())
              + f" | mercado {hrow['p_market']*100:.0f}% | dispersión {hrow['spread']*100:.0f} pts")
        print(f"  goles esperados {lh:.2f}-{la:.2f} (total {total:.2f} = mercado). marcador más probable {top[0][0][0]}-{top[0][0][1]} ({top[0][1]/N*100:.1f}%); "
              f"siguientes " + ", ".join(f"{s[0]}-{s[1]} ({c/N*100:.1f}%)" for s, c in top[1:]))
        print(f"  portería a cero: {m['home']} {np.mean(a == 0)*100:.0f}% | {m['away']} {np.mean(h == 0)*100:.0f}%; ambos marcan {np.mean((h > 0) & (a > 0))*100:.0f}%; "
              f"más de 2.5 {np.mean(h + a > 2)*100:.0f}%, más de 3.5 {np.mean(h + a > 3)*100:.0f}%; margen >=2 goles: local {np.mean(h - a >= 2)*100:.0f}% / visita {np.mean(a - h >= 2)*100:.0f}%")
        print(f"  goles totales p10/p50/p90: {np.percentile(h + a, 10):.0f}/{np.percentile(h + a, 50):.0f}/{np.percentile(h + a, 90):.0f}")
        if name in UCL_SCENARIOS:
            side, delta, label = UCL_SCENARIOS[name]
            lh2, la2 = (max(lh + delta, 0.2), la) if side == "home" else (lh, max(la + delta, 0.2))
            b = sp.book(lh2, la2)
            print(f"  ESCENARIO (supuesto) {label}: {m['home']} {b['H']*100:.0f}% | empate {b['D']*100:.0f}% | {m['away']} {b['A']*100:.0f}%")
        if notrun:
            print(f"  nota: herramientas que NO corrieron: {', '.join(notrun)}")
        print()


def last_season_env(df: pd.DataFrame, team: str) -> str:
    g = df[(df.home_team == team) | (df.away_team == team)]
    if g.empty:
        return "sin datos"
    pf = np.where(g.home_team == team, g.home_score, g.away_score)
    pa = np.where(g.home_team == team, g.away_score, g.home_score)
    return f"{len(g)} juegos, anota {pf.mean():.1f} permite {pa.mean():.1f}, total medio {np.mean(pf + pa):.1f}"


def nba_block(sheet: dict, props: list[dict], day: datetime.date) -> None:
    params = nh.load_params()
    nctx = pe.build_nba_ctx([DATA / "nba_historical.csv", DATA / "nba_games_2526.csv"])
    df = pd.read_csv(DATA / "nba_games_2526.csv")
    df = df[df.season == df.season.max()]
    rows = pp.price(props)
    over = {(r["player"], r["stat"]): r for r in rows if " Más de " in r["pick"]}
    print("=== NBA === simulación por cuartos (400k) por partido\n")
    for name, g in sheet.items():
        _, info = nsp.price_game(nctx, name, g, day, params)
        m, T = info["m_final"], info["T"]
        rho = params.get("rho", 0.0)
        sim = fs.simulate(m, T, nsp.SIGMA_M, nsp.SIGMA_T, rho_q=rho / (2 - rho) if params.get("fitted") else 0.0)
        home, away = g["home"], g["away"]
        ph = float(sim["win_home"].mean())
        M, H, A, S = sim["M"], sim["H"], sim["A"], sim["S"]
        print(f"{name}  [{home} local]")
        print(f"  P(win) final: {home} {ph*100:.1f}% | {away} {(1-ph)*100:.1f}%   (mercado {info['p_ml_market']*100:.1f}% local; modelo-tools {('%+.1f' % info['m_model']) if info['m_model'] is not None else 'n/a'} pts, peso {info['w_model']:.0%}"
              f"{', ratings viejos' if info['stale'] else ''})")
        print(f"  marcador esperado {home} {H.mean():.0f} - {away} {A.mean():.0f}  (margen {M.mean():+.1f} local, total {S.mean():.1f} = mercado). "
              f"rango 80%: {home} {np.percentile(H,10):.0f}-{np.percentile(H,90):.0f}, {away} {np.percentile(A,10):.0f}-{np.percentile(A,90):.0f}, total {np.percentile(S,10):.0f}-{np.percentile(S,90):.0f}")
        h1 = sim["h1"]
        print(f"  descanso: {home} {'+' if h1.mean()>=0 else ''}{h1.mean():.1f} esperado, lidera al medio {np.mean(h1>0)*100:.0f}%; cuarto esperado {home} {H.mean()/4:.1f} / {away} {A.mean()/4:.1f}")
        print(f"  cerrado (<=5 pts) {np.mean(np.abs(M)<=5.5)*100:.0f}% | paliza 15+ local {np.mean(M>=14.5)*100:.0f}% / visita {np.mean(M<=-14.5)*100:.0f}% | prórroga ~{np.mean(np.abs(M)<0.5)*100:.1f}%")
        sens = ", ".join(f"{'+' if d>0 else ''}{d:g} pts -> {home} {float(fs.simulate(m+d, T, nsp.SIGMA_M, nsp.SIGMA_T, n=100_000)['win_home'].mean())*100:.0f}%" for d in (-2, -1, 1, 2))
        print(f"  sensibilidad (ausencia/duda de rotación = ±1-2 pts de margen): {sens}")
        print(f"  contexto 2025-26: {home}: {last_season_env(df, home)} | {away}: {last_season_env(df, away)}")
        abbr = {"DET": "Detroit", "BOS": "Boston", "SAS": "San Antonio", "OKC": "Oklahoma"}
        mine = [r for k, r in over.items() if any(abbr[r["team"]] in t for t in (home, away))]
        shown = {}
        for r in mine:
            pr = next(x for x in props if x["player"] == r["player"] and x["stat"] == r["stat"])
            if r["stat"] == "Doble doble":
                shown.setdefault(r["player"], []).append(f"doble doble {r['p_win']*100:.0f}%")
                continue
            sd0 = max(pp.CV.get(r["stat"], 0.5) * max(pr["line"], 1.0), 0.8)
            mu = pp.prior_mean_from_market(pr["line"], r["p_win"], sd0)
            shown.setdefault(r["player"], []).append(f"{r['stat'].lower()} {mu:.1f} (línea {pr['line']:g})")
        if shown:
            print("  stats esperadas de jugadores (línea del mercado movida a la P final; evidencia débil, K=10):")
            for pl, items in shown.items():
                print(f"    - {pl}: " + "; ".join(items))
        print()


def main() -> None:
    ucl = json.loads(Path(sys.argv[1]).read_text())["matches"]
    nba = json.loads(Path(sys.argv[2]).read_text())["matches"]
    props = json.loads(Path(sys.argv[3]).read_text())["props"]
    day = datetime.date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else datetime.date.today()
    ucl_block(ucl)
    nba_block(nba, props, day)


if __name__ == "__main__":
    main()

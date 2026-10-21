"""
nba_box_sim.py — player box-score simulation tied to the game simulation, built on REAL 2025-26 box scores (ESPN).

Game environment: market margin/total (nba_sheet_picks) -> quarter-by-quarter Monte Carlo (nba_flow_sim) gives each
team's points H, A per simulation. Player line: bootstrap one of the player's own 2025-26 games (minutes included, DNP
excluded) and re-express its team-relative output in today's environment: pts, 3PM, ast scale by H_sim / team_pts_of_that_game
(rebounds by the square root). This keeps the player's real share/minutes variance and lets both teams' players move together
through the shared score. Pairs on the same game are therefore correlated; different games are independent.

Limits (stated, not hidden): rosters/roles changed (e.g. Brown now at PHI next to Embiid/LeBron/Maxey, Tatum returned from injury
with 22 games): last season's role is assumed unless a role scale is given. Minutes are not projected. No usage redistribution
between teammates (only matters for a player's absence).

    python3 scripts/nba_box_sim.py data/slips/2026-10-20_props_6leg.json data/sheets/2026-10-20_nba.json 2026-10-20 
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import itertools

import nba_flow_sim as fs
import nba_halftime as nh
import nba_sheet_picks as nsp
import pwin_ensemble as pe
import usage_vacuum as uv
import validate_usage_vacuum as vuv

DATA = Path(__file__).parent.parent / "data"
N_SIM = 200_000
MIN_GAME_MIN = 8.0
MODEL_W = 0.5            # P(win) Rule: 50% model tools / 50% market


def load_logs() -> tuple[pd.DataFrame, pd.DataFrame]:
    p, _ = vuv.load()                                                          # 2025-26 box scores of real teams (no All-Star games), with team totals
    p["pra"] = p.pts + p.reb + p.ast
    tot = p[["game_id", "team_id"] + [c for c in p.columns if c.endswith("_t")]].drop_duplicates(["game_id", "team_id"])
    return p, uv.build_rates(p, tot)


def team_scenarios(team: str, roster: pd.DataFrame, inj: pd.DataFrame, lineups: dict, rates: pd.DataFrame) -> list[tuple[float, dict]]:
    """[(prob, {athlete_id: roles})] over the Day-To-Day players (Out players removed, Day-To-Day in/out with p_play)."""
    r = roster[roster.team == team]
    ids = {n: str(i) for n, i in zip(r.name, r.athlete_id)}
    st = inj[inj.team_id.isin(r.team_id.unique())]
    out = {str(i) for i in st[st.status == "Out"].athlete_id}
    dtd = [str(i) for i in st[st.status == "Day-To-Day"].athlete_id]
    starters = {ids[n] for n in lineups["starters"][team]}
    base = [i for i in ids.values() if i not in out and i not in dtd]
    p_play = lineups["p_play_day_to_day"]
    res = []
    for combo in itertools.product([0, 1], repeat=len(dtd)):
        prob = float(np.prod([p_play if c else 1 - p_play for c in combo]))
        avail = base + [d for d, c in zip(dtd, combo) if c]
        res.append((prob, uv.roles(avail, starters & set(avail), rates)))
    return res


def game_env(nctx, name: str, g: dict, day: datetime.date, params: dict, n: int = N_SIM) -> dict:
    _, info = nsp.price_game(nctx, name, g, day, params)
    rho = params.get("rho", 0.0)
    sim = fs.simulate(info["m_final"], info["T"], nsp.SIGMA_M, nsp.SIGMA_T, rho_q=rho / (2 - rho) if params.get("fitted") else 0.0, n=n)
    return {"H": sim["H"], "A": sim["A"], "E_H": float(sim["H"].mean()), "E_A": float(sim["A"].mean()), "m": info["m_final"], "T": info["T"]}


def player_draws(logs: pd.DataFrame, aid: str, side_pts: np.ndarray, stat: str, rng: np.random.Generator, scen: list, use_roles: bool = True) -> np.ndarray:
    q = logs[logs.athlete_id == aid]
    if q.empty:
        raise KeyError(f"no 2025-26 box scores for athlete {aid}")
    n = len(side_pts)
    idx = rng.integers(0, len(q), size=n)
    row = q.iloc[idx]
    f = side_pts / row.pts_t.to_numpy()                                         # today's team points vs the bootstrapped game's team points
    pick = rng.choice(len(scen), size=n, p=[p for p, _ in scen])
    def role(k):
        return np.array([scen[j][1].get(aid, {}).get(k, 1.0) for j in range(len(scen))])[pick] if use_roles else 1.0
    rm = role("pts"), role("ast"), role("reb"), role("fg3m")
    pts, ast, reb, tpm = row.pts.to_numpy() * f * rm[0], row.ast.to_numpy() * f * rm[1], row.reb.to_numpy() * np.sqrt(f) * rm[2], row.fg3m.to_numpy() * f * rm[3]
    return {"pts": pts, "ast": ast, "reb": reb, "fg3m": tpm, "pra": pts + ast + reb}[stat]


def run(slip: dict, sheet: dict, day: datetime.date, use_roles: bool = True) -> dict:
    params = nh.load_params()
    nctx = pe.build_nba_ctx([DATA / "nba_historical.csv", DATA / "nba_games_2526.csv"])
    logs, rates = load_logs()
    tag = day.strftime("%Y%m%d")
    roster = pd.read_csv(DATA / "nba" / f"roster_{tag}.csv", dtype={"athlete_id": str, "team_id": str})
    inj = pd.read_csv(DATA / "nba" / f"injuries_{tag}.csv", dtype={"athlete_id": str, "team_id": str})
    lineups = json.loads((DATA / "sheets" / f"{day.isoformat()}_nba_lineups.json").read_text())
    rng = np.random.default_rng(20261020)
    res = {"groups": []}
    for grp in slip["groups"]:
        env = game_env(nctx, grp["game"], sheet[grp["game"]], day, params)
        away_t, home_t = sheet[grp["game"]]["away"], sheet[grp["game"]]["home"]
        scen = {t: team_scenarios(t, roster, inj, lineups, rates) for t in (home_t, away_t)}
        hits, legs = [], []
        for leg in grp["legs"]:
            team = home_t if leg["side_of_game"] == "home" else away_t
            pts = env["H"] if leg["side_of_game"] == "home" else env["A"]
            r = roster[(roster.team == team) & (roster.name == leg["player"])]
            aid = str(r.athlete_id.iloc[0])
            x = player_draws(logs, aid, pts, leg["stat"], rng, scen[team], use_roles)
            hit = x > leg["line"]
            ro = scen[team][-1][1].get(aid, {})
            hits.append(hit)
            legs.append({**leg, "p": float(hit.mean()), "mean": float(x.mean()), "p10": float(np.percentile(x, 10)), "p90": float(np.percentile(x, 90)),
                         "n_games": int((logs.athlete_id == aid).sum()), "min": ro.get("min"), "share_today": ro.get("pts_share"), "share_ls": float(rates.share_pts.get(aid, np.nan)),
                         "role_pts": ro.get("pts"), "mpg_ls": float(rates.mpg.get(aid, np.nan))})
        joint = hits[0] & hits[1]
        res["groups"].append({"game": grp["game"], "odds": grp["odds"], "legs": legs, "joint": float(joint.mean()), "indep": float(np.prod([l["p"] for l in legs])),
                              "env": {k: env[k] for k in ("m", "T", "E_H", "E_A")}})
    return res


def main() -> None:
    slip = json.loads(Path(sys.argv[1]).read_text())
    sheet = json.loads(Path(sys.argv[2]).read_text())["matches"]
    day = datetime.date.fromisoformat(sys.argv[3])
    for use_roles, title in ((False, "SIN usage vacante (rol de la temporada pasada)"), (True, "CON usage vacante (rosters/lesiones de hoy)")):
        r = run(slip, sheet, day, use_roles)
        ps = [g["joint"] for g in r["groups"]]
        print(f"\n=== {title} — simulación con box scores reales 2025-26 ===")
        for g in r["groups"]:
            e = g["env"]
            print(f"\n{g['game']}  (margen mercado local {e['m']:+.1f}, total {e['T']:.1f}; puntos esp. local {e['E_H']:.1f} / visita {e['E_A']:.1f})")
            for l in g["legs"]:
                extra = (f" | min {l['mpg_ls']:.0f} -> {l['min']:.0f}, % de los puntos del equipo {l['share_ls']*100:.1f} -> {l['share_today']*100:.1f} (rol x{l['role_pts']:.2f})" if use_roles else "")
                print(f"  - {l['player']} {l['stat']} Más de {l['line']:g}: P {l['p']*100:.1f}% | media {l['mean']:.1f} (p10-p90 {l['p10']:.1f}-{l['p90']:.1f}) | {l['n_games']} juegos{extra}")
            pb = [MODEL_W * l["p"] + (1 - MODEL_W) * 0.5 for l in g["legs"]]          # lines sit near 50/50: market prior ~0.5 per leg
            jb = pb[0] * pb[1] * (g["joint"] / g["indep"])
            g["joint_blend"] = jb
            print(f"  PAREJA: P(win) simulación {g['joint']*100:.1f}% | mezclada 50/50 con el mercado {jb*100:.1f}% (patas {pb[0]*100:.0f}% y {pb[1]*100:.0f}%) | cuota {g['odds']:.2f} -> justa {1/jb:.2f} | EV {jb*g['odds']*100-100:+.1f}%")
        ps = [g["joint_blend"] for g in r["groups"]]
        p_all = float(np.prod(ps))
        k = {i: 0.0 for i in range(4)}
        for mask in range(8):
            pr = float(np.prod([ps[j] if (mask >> j) & 1 else 1 - ps[j] for j in range(3)]))
            k[bin(mask).count("1")] += pr
        o = slip["odds"]
        print(f"\nTICKET 6 patas (mezcla modelo/mercado) (cuota {o:.2f}): P(win) {p_all*100:.1f}% | justa {1/p_all:.1f} | $5 pagan ${5*o:.2f}, $10 pagan ${10*o:.2f} | EV {p_all*o*100-100:+.1f}%")
        print(f"  parejas acertadas: 3/3 {k[3]*100:.1f}% | 2/3 {k[2]*100:.1f}% | 1/3 {k[1]*100:.1f}% | 0/3 {k[0]*100:.1f}%")


if __name__ == "__main__":
    main()

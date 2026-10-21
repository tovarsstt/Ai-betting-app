"""
slate_today.py — today's UCL slate from the Actions snapshot (data/value_picks.txt): every game's final 1X2 (50% model-tool groups /
50% devigged market), score grid anchored to the MARKET total, then any ticket priced by exact leg math (win, over, team total, 1UP).

    python3 scripts/slate_today.py data/value_picks.txt
Legs are listed in LEGS at the bottom of a call: (match, kind, arg, stake-site odds).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

import game_sim_report as gs
import parlay_check as pc
import soccer_markets as sm

ROW = re.compile(r"^\s+\[(model|market)\s*\]\s+(\S+)\s+H\s+([\d.]+)% / D\s+([\d.]+)% / A\s+([\d.]+)%(.*)$")
HEAD = re.compile(r"^  (.+? vs .+?)  \(")
TOT = re.compile(r"anchored to market total ([\d.]+)")


def parse(path: Path) -> dict:
    games, cur = {}, None
    for line in path.read_text().splitlines():
        if line.startswith("PER-TOOL DETAIL"):
            continue
        m = HEAD.match(line)
        if m and " @ " not in line and line.startswith("  ") and not line.startswith("    "):
            cur = m.group(1)
            games[cur] = {"model": {}, "market": {}, "T": None}
            continue
        r = ROW.match(line)
        if r and cur:
            kind, name = r.group(1), r.group(2)
            games[cur][kind][name] = tuple(float(r.group(i)) / 100 for i in (3, 4, 5))
            t = TOT.search(r.group(6))
            if t:
                games[cur]["T"] = float(t.group(1))
    return {k: v for k, v in games.items() if v["T"]}


def final_1x2(g: dict) -> tuple[float, float, float, float, float]:
    mod = g["model"]
    elo = [v for k, v in mod.items() if k in ("elo_poisson_dixon_coles", "elo_monte_carlo_200k", "elo_skellam")]
    groups = [np.mean(elo, axis=0)] if elo else []
    groups += [np.array(mod[k]) for k in ("poisson_regression", "eigenvector_keener", "binomial_wdl_rates") if k in mod]
    pm = np.mean(groups, axis=0)
    pk = np.mean([np.array(v) for v in g["market"].values()], axis=0)
    p = 0.5 * pm + 0.5 * pk
    return tuple(p / p.sum()) + (float(pm[0] - pk[0]), float(max(np.array(list(mod.values()))[:, 0]) - min(np.array(list(mod.values()))[:, 0])))


def grid(g: dict) -> tuple[list, tuple, float, float]:
    pH, pD, pA, gap, spread = final_1x2(g)
    lh, la = gs.split_for(g["T"], pH - pA)
    return sm.score_matrix(lh, la), (pH, pD, pA), lh, la


def leg_p(M, lh, la, kind: str, arg) -> float:
    n = len(M)
    s = 0.0
    for i in range(n):
        for j in range(n):
            p = M[i][j]
            if kind == "win_h":
                ok = i > j
            elif kind == "win_a":
                ok = j > i
            elif kind == "over":
                ok = i + j > arg
            elif kind == "tt_h":
                ok = i > arg
            elif kind == "tt_a":
                ok = j > arg
            elif kind == "1up_h":
                s += p * pc.p_ever_ahead(i, j)
                continue
            elif kind == "1up_a":
                s += p * pc.p_ever_ahead(j, i)
                continue
            else:
                raise ValueError(kind)
            s += p if ok else 0
    return s


def main() -> None:
    games = parse(Path(sys.argv[1]))
    print(f"{len(games)} partidos con herramientas completas\n")
    cache = {}
    for name, g in games.items():
        M, (pH, pD, pA), lh, la = grid(g)
        cache[name] = (M, lh, la)
        mkt = np.mean([np.array(v) for v in g["market"].values()], axis=0)
        print(f"{name}: P(win) final {pH*100:.0f}/{pD*100:.0f}/{pA*100:.0f} (mercado {mkt[0]*100:.0f}/{mkt[1]*100:.0f}/{mkt[2]*100:.0f}) | goles esp. {lh:.2f}-{la:.2f} (total mercado {g['T']:.2f}) | "
              f"más 2.5 {leg_p(M,lh,la,'over',2.5)*100:.0f}%, más 3.5 {leg_p(M,lh,la,'over',3.5)*100:.0f}%")
    import json
    slip = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else None
    if slip:
        print("\nTICKET:")
        total_p, total_o = 1.0, 1.0
        for leg in slip["legs"]:
            M, lh, la = cache[leg["match"]]
            p = leg_p(M, lh, la, leg["kind"], leg.get("arg"))
            total_p *= p
            total_o *= leg["odds"]
            print(f"  {leg['label']} [{leg['match']}]  P(win) {p*100:.1f}% | cuota {leg['odds']:.2f}")
        print(f"  => P(win) del ticket {total_p*100:.1f}% | cuota {total_o:.2f} | cuota justa {1/total_p:.2f} | EV {total_p*total_o*100-100:+.1f}%")
        for st in (26, 35, 50):
            print(f"     ${st} pagan ${st*total_o:.2f} (ganancia ${st*(total_o-1):.2f})")


if __name__ == "__main__":
    main()

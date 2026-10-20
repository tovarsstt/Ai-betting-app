"""
props_picks.py — NBA player props from the pasted sheet, P(win) first (EV last, informational — user rule).

Tools per prop (all shrunk toward the MARKET because the only player data is 5 games, and on opening night those are
PRESEASON games with limited minutes against full-season lines):
  market      : devigged (power) P(over)
  beta-binomial: hits of the last 5 vs the line, Beta prior centred on the market with strength K
  normal      : shrunk mean / sd of the last 5 (prior mean = line-implied mean, prior sd = CV by stat)
  count (NB)  : negative binomial for rebounds / assists / threes / double-double-like counts
  bootstrap   : resample the last 5 (+ jitter), shrunk the same way
Final P = 50% mean(model tools) + 50% market. DNP games (PRA == 0) are dropped for that player. With K=10 the model can
only move the market by ~1/3 of the gap the 5 games suggest: there is NO independent player model in this repo.
Name<->stats mapping of the paste is an ASSUMPTION (stat block belongs to the last name of the preceding list).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import nbinom, norm

import betting_math as bm

K = 10.0
CV = {"Puntos": 0.40, "Rebotes": 0.50, "Asistencias": 0.60, "Triples": 0.75, "PRA": 0.30}
COUNT_STATS = {"Rebotes", "Asistencias", "Triples"}
MIN_ODDS = 1.25


def two_way(o, u):
    p = bm.devig_power([o, u])
    return float(p[0]), float(p[1])


def prior_mean_from_market(line: float, p_over: float, sd: float) -> float:
    """Mean mu such that P(X > line) = p_over for X ~ N(mu, sd) (half-point line -> continuity ok)."""
    return line + sd * norm.ppf(min(max(p_over, 1e-4), 1 - 1e-4))


def tools_for(pr: dict, valid: list[int]) -> dict:
    x = np.array([pr["last5"][i] for i in valid], float)
    n, line = len(x), pr["line"]
    p_mkt, _ = two_way(pr["over"], pr["under"])
    out = {"market": p_mkt}
    stat = pr["stat"]
    if stat == "Doble doble":
        hits = float((x > 0.5).sum())
        out["beta-binomial"] = (hits + K * p_mkt) / (n + K)
        return out
    hits = float((x > line).sum())
    out["beta-binomial"] = (hits + K * p_mkt) / (n + K)
    sd0 = max(CV.get(stat, 0.5) * max(line, 1.0), 0.8)
    mu0 = prior_mean_from_market(line, p_mkt, sd0)
    mu = (n * x.mean() + K * mu0) / (n + K)
    s2 = (max(n - 1, 1) * (x.std(ddof=1) ** 2 if n > 1 else sd0 ** 2) + K * sd0 ** 2) / (max(n - 1, 1) + K)
    sd = max(np.sqrt(s2), 0.7)
    out["normal"] = float(1 - norm.cdf((line - mu) / sd))
    if stat in COUNT_STATS:
        r = 8.0
        mu_c = max(mu, 0.05)
        p = r / (r + mu_c)
        out["count-NB"] = float(1 - nbinom.cdf(int(np.floor(line)), r, p))
    rng = np.random.default_rng(7)
    draw = rng.choice(x, 20000) + rng.normal(0, sd0 * 0.5, 20000)
    raw = float((draw > line).mean())
    out["bootstrap"] = (n * raw + K * p_mkt) / (n + K)
    return out


def price(props: list[dict]) -> list[dict]:
    dnp: dict[str, set[int]] = {}
    for pr in props:
        if pr["stat"] == "PRA":
            dnp[pr["player"]] = {i for i, v in enumerate(pr["last5"]) if v == 0}
    rows = []
    for pr in props:
        valid = [i for i in range(5) if i not in dnp.get(pr["player"], set())]
        if len(valid) < 3:
            continue
        t = tools_for(pr, valid)
        p_mkt = t["market"]
        model = [v for k, v in t.items() if k != "market"]
        p_over = 0.5 * float(np.mean(model)) + 0.5 * p_mkt
        for side, p, dec in (("Más de", p_over, pr["over"]), ("Menos de", 1 - p_over, pr["under"])):
            rows.append({"player": pr["player"], "team": pr["team"], "stat": pr["stat"], "pick": f"{pr['player']} {pr['stat']} {side} {pr['line']:g}",
                         "p_win": p, "decimal": dec, "ev": p * dec - 1, "tools": {k: (v if side == "Más de" else 1 - v) for k, v in t.items()},
                         "n_games": len(valid), "dnp_dropped": 5 - len(valid)})
    return rows


def main() -> None:
    props = json.loads(Path(sys.argv[1]).read_text())["props"]
    rows = [r for r in price(props) if r["decimal"] >= MIN_ODDS]
    rows.sort(key=lambda r: (-round(r["p_win"], 3), -r["decimal"]))
    print(f"PLAYER PROPS NBA — mayor P(win), cuota >= {MIN_ODDS} (EV al final, informativo). Últimos-5 = PRETEMPORADA: evidencia débil, K={K:g}.")
    for r in rows[:14]:
        tl = ", ".join(f"{k} {v*100:.0f}%" for k, v in r["tools"].items())
        print(f"- {r['pick']} [{r['team']}]  P(win) {r['p_win']*100:.1f}% | cuota {r['decimal']:.2f} -> $10 pagan ${10*r['decimal']:.2f} | EV {r['ev']*100:+.1f}%\n    herramientas: {tl}"
              + (f"  | {r['dnp_dropped']} juego(s) sin jugar excluido(s)" if r["dnp_dropped"] else ""))
    json.dump(rows, open("/tmp/props_rows.json", "w"), default=float)


if __name__ == "__main__":
    main()

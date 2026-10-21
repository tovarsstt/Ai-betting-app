"""
sheet_picks.py — price EVERY market on a pasted sportsbook sheet with the full toolkit (CLAUDE.md P(win) Rule).

Input: data/sheets/<date>_ucl.json (decimal odds: 1X2, double chance, draw-no-bet, BTTS, O/U).
Per match, each goal-rate tool (Elo/Dixon-Coles, Poisson regression, eigenvector, market-anchored DC) gives a full
score matrix -> 1X2, double chance, DNB, BTTS, Over 2.5; Monte Carlo (200k) re-checks the Elo matrix; Skellam and the
binomial W-D-L tool contribute to 1X2-derived markets. Market views = devig of the sheet itself. Final = 50% model-tool
mean (grouped) + 50% market-tool mean. Output order: P(win) first -> odds/payout -> EV last; UCL section only here.

    python3 scripts/sheet_picks.py data/sheets/2026-10-20_ucl.json [--only "Napoli vs Bodo/Glimt"]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import betting_math as bm
import pwin_ensemble as pe
import soccer_markets as sm

DATA = Path(__file__).parent.parent / "data"
W_MODEL = pe.MODEL_WEIGHT
GAP_WARN, SPREAD_WARN, LONGSHOT = 0.15, 0.20, 0.35
TOTALS_KEYS = ("BTTS_Y", "BTTS_N", "O2.5", "U2.5", "O3.5", "U3.5")


def book(lh: float, la: float) -> dict:
    b = sm.derive_markets(sm.score_matrix(lh, la))
    h, d, a = b.home_win, b.draw, b.away_win
    return {"H": h, "D": d, "A": a, "1X": h + d, "X2": d + a, "12": h + a, "DNB_H": h / (h + a), "DNB_A": a / (h + a),
            "BTTS_Y": b.btts_yes, "BTTS_N": 1 - b.btts_yes, "O2.5": b.over_under[2.5]["over"], "U2.5": b.over_under[2.5]["under"],
            "O3.5": b.over_under[3.5]["over"], "U3.5": b.over_under[3.5]["under"]}


def from_1x2(p: dict) -> dict:
    h, d, a = p["home"], p["draw"], p["away"]
    return {"H": h, "D": d, "A": a, "1X": h + d, "X2": d + a, "12": h + a, "DNB_H": h / (h + a), "DNB_A": a / (h + a)}


def anchored_lambdas(pw: np.ndarray, over25: float) -> tuple[float, float]:
    """(λh, λa) of a Dixon-Coles matrix matching the market's home win, away win and Over 2.5 (3 eq, 2 unknowns)."""
    def res(x):
        b = sm.derive_markets(sm.score_matrix(abs(x[0]) + 0.05, abs(x[1]) + 0.05))
        return [b.home_win - pw[0], b.away_win - pw[2], 0.5 * (b.over_under[2.5]["over"] - over25)]
    r = least_squares(res, x0=[1.5, 1.2])
    return abs(r.x[0]) + 0.05, abs(r.x[1]) + 0.05


def two_way(odds: list[float]) -> list[float]:
    return [float(x) for x in bm.devig_power(odds)]


SELECTIONS = [  # key in book, label factory, sheet getter
    ("H", lambda m: f"{m['home']} gana", lambda s: s["x12"][0]), ("D", lambda m: "Empate", lambda s: s["x12"][1]),
    ("A", lambda m: f"{m['away']} gana", lambda s: s["x12"][2]),
    ("1X", lambda m: f"{m['home']} o empate", lambda s: s["dc"]["1X"]), ("X2", lambda m: f"{m['away']} o empate", lambda s: s["dc"]["X2"]),
    ("12", lambda m: f"{m['home']} o {m['away']} (sin empate)", lambda s: s["dc"]["12"]),
    ("DNB_H", lambda m: f"{m['home']} (apuesta sin empate)", lambda s: s["dnb"][0]),
    ("DNB_A", lambda m: f"{m['away']} (apuesta sin empate)", lambda s: s["dnb"][1]),
    ("BTTS_Y", lambda m: "Ambos marcan: Sí", lambda s: s["btts"][0]), ("BTTS_N", lambda m: "Ambos marcan: No", lambda s: s["btts"][1]),
    ("O2.5", lambda m: "Más de 2.5", lambda s: s["ou"]["2.5"][0]), ("U2.5", lambda m: "Menos de 2.5", lambda s: s["ou"]["2.5"][1]),
    ("O3.5", lambda m: "Más de 3.5", lambda s: s["ou"]["3.5"][0]), ("U3.5", lambda m: "Menos de 3.5", lambda s: s["ou"]["3.5"][1]),
]


def price_match(ctx, name: str, m: dict) -> tuple[list[dict], list[str], str]:
    ml_dec = m["x12"]
    # tools run on the sheet's own 1X2 (decimal -> american only for the shared pwin_ensemble API)
    to_am = lambda d: int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))
    market_am = {"home": to_am(ml_dec[0]), "draw": to_am(ml_dec[1]), "away": to_am(ml_dec[2])}
    pw0 = bm.devig_power(ml_dec)
    ou0 = two_way(m["ou"]["2.5"])
    mtotal = pe.market_total_from_ou(float(pw0[0]), float(pw0[2]), ou0[0], 2.5)          # market sets the total
    tools = pe.soccer_tools(ctx, m["home"], m["away"], market_am, 2.5, market_total=mtotal)
    notes: list[str] = []
    model_books: dict[str, dict] = {}                      # tool -> full book
    for t in tools:
        if t.kind == "model" and t.lam:
            model_books[t.name] = book(*t.lam)
    # Monte Carlo + Skellam only refine 1X2-derived markets (same λ as Elo); binomial likewise
    one_x_two = {t.name: from_1x2(t.probs) for t in tools if t.kind == "model" and t.probs}
    pw = bm.devig_power(ml_dec)
    ou = two_way(m["ou"]["2.5"])
    lh, la = anchored_lambdas(pw, ou[0])
    mkt_book = book(lh, la)
    raw = pe.um.lambdas(ctx.elo_model, ctx.elo.get(pe.cu.normalize(m["home"]), 1500), ctx.elo.get(pe.cu.normalize(m["away"]), 1500), comp="UCL")
    total_gap = (lh + la) - sum(raw)        # diagnostic only: how far the raw (bias-corrected) Elo total was from the market
    notes.append(f"market total {lh+la:.2f} goals; raw Elo total {sum(raw):.2f} (gap {total_gap:+.2f}) -> every tool anchored to the market total")
    # direct 2-way / 3-way devig of the sheet for each market
    mk = {k: v for k, v in zip(("H", "D", "A"), map(float, pw))}
    mk.update({"1X": mk["H"] + mk["D"], "X2": mk["D"] + mk["A"], "12": mk["H"] + mk["A"]})
    dn = two_way(m["dnb"]); mk.update({"DNB_H": dn[0], "DNB_A": dn[1]})
    bt = two_way(m["btts"]); mk.update({"BTTS_Y": bt[0], "BTTS_N": bt[1]})
    mk.update({"O2.5": ou[0], "U2.5": ou[1]}); o35 = two_way(m["ou"]["3.5"]); mk.update({"O3.5": o35[0], "U3.5": o35[1]})
    rows, groups = [], {"elo": ["elo_poisson_dixon_coles"], "preg": ["poisson_regression"], "eig": ["eigenvector_keener"]}
    for key, label, getter in SELECTIONS:
        vals_by_group: dict[str, list[float]] = {}
        per_tool: dict[str, float] = {}
        for g, names in groups.items():
            ps = [model_books[n][key] for n in names if n in model_books]
            if ps:
                vals_by_group[g] = ps; per_tool[names[0]] = float(np.mean(ps))
        if key in ("H", "D", "A", "1X", "X2", "12", "DNB_H", "DNB_A"):
            for n in ("binomial_wdl_rates", "elo_skellam"):
                if n in one_x_two:
                    per_tool[n] = one_x_two[n][key]
            if "binomial_wdl_rates" in one_x_two:
                vals_by_group["binomial"] = [one_x_two["binomial_wdl_rates"][key]]
        # Elo family also includes MC + Skellam (same λ): fold into the elo group
        if "elo" in vals_by_group and key in ("H", "D", "A", "1X", "X2", "12", "DNB_H", "DNB_A") and "elo_skellam" in one_x_two:
            vals_by_group["elo"].append(one_x_two["elo_skellam"][key])
        if not vals_by_group:
            continue
        p_model = float(np.mean([np.mean(v) for v in vals_by_group.values()]))
        p_mkt = float(np.mean([mkt_book[key], mk[key]]))
        spread = max(per_tool.values()) - min(per_tool.values()) if len(per_tool) > 1 else 0.0
        p = W_MODEL * p_model + (1 - W_MODEL) * p_mkt
        dec = getter(m)
        rows.append({"match": name, "pick": label(m), "key": key, "p_win": p, "p_model": p_model, "p_market": p_mkt, "spread": spread,
                     "decimal": dec, "payout_10": 10 * dec, "ev": p * dec - 1, "per_tool": per_tool, "n_groups": len(vals_by_group),
                     "total_gap": total_gap})
    detail = pe.tools_table(tools) + "\n    " + "\n    ".join(notes)
    return rows, [t.name for t in tools if t.probs is None and t.kind != "flag"], detail


def warnings(r: dict, low_sample: list[str]) -> list[str]:
    w = [f"LOW-SAMPLE club: {', '.join(low_sample)}"] if low_sample else []
    if abs(r["p_model"] - r["p_market"]) > GAP_WARN:
        w.append(f"model vs market gap {abs(r['p_model'] - r['p_market'])*100:.0f} pts")
    if r["spread"] > SPREAD_WARN:
        w.append(f"tools disagree ({r['spread']*100:.0f} pt spread)")
    if r["p_win"] < LONGSHOT:
        w.append("longshot")
    return w


def fmt(r: dict, low: list[str]) -> str:
    w = warnings(r, low)
    return (f"{r['pick']} [{r['match']}]  P(win) {r['p_win']*100:.1f}% (model {r['p_model']*100:.1f} / mkt {r['p_market']*100:.1f})"
            f" | {r['decimal']:.2f} -> $10 pays ${r['payout_10']:.2f} | EV {r['ev']*100:+.1f}%" + (f"   !! {'; '.join(w)}" if w else ""))


def main() -> None:
    path = Path(sys.argv[1])
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    sheet = json.loads(path.read_text())["matches"]
    soc = DATA / "soccer"
    ctx = pe.build_soccer_ctx([soc / "club_results.csv", soc / "extra_league_results.csv", soc / "uefa_results.csv"])
    allrows, details, lows = [], [], {}
    for name, m in sheet.items():
        if only and only != name:
            continue
        rows, notrun, detail = price_match(ctx, name, m)
        low = [n for n in (m["home"], m["away"]) if ctx.games.get(pe.cu.normalize(n), 0) < 15]
        lows[name] = low
        allrows += rows
        details.append(f"  {name}  (not run: {', '.join(notrun) or 'none'})\n{detail}")
    rank = lambda rs: sorted(rs, key=lambda r: (-round(r["p_win"], 3), -r["ev"]))
    print("=== UCL === (P(win) first, EV last; every selection on the sheet)")
    print("RECOMMENDED — EV > 0, ordered by P(win):")
    for r in rank([r for r in allrows if r["ev"] > 0]):
        print("* " + fmt(r, lows[r["match"]]))
    print("\nBEST SELECTION PER MATCH BY P(win) (not necessarily +EV):")
    best = {}
    for r in allrows:
        if r["key"] in ("H", "D", "A", "1X", "X2", "12", "DNB_H", "DNB_A") and (r["match"] not in best or r["p_win"] > best[r["match"]]["p_win"]):
            best[r["match"]] = r
    for r in rank(list(best.values())):
        print("- " + fmt(r, lows[r["match"]]))
    print("\nPER-TOOL DETAIL:")
    print("\n".join(details))


if __name__ == "__main__":
    main()

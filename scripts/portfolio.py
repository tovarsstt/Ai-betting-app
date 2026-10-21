"""
portfolio.py — build a small-bankroll slate from two priced sheets (UCL first, then NBA), P(win) first, EV last.

Candidates are single selections from the full-toolkit pricing (sheet_picks for UCL, nba_sheet_picks for NBA). Legs of a
ticket come from DIFFERENT matches (independent: P(ticket) = product of leg P). Guards on every leg:
  EV > 0, P(win) >= 50% for singles/parlay legs (priority = winning), no model-vs-market gap > 15 pts, tool spread <= 20 pts,
  no low-sample club, no 'stale' flag on NBA unless the leg has a margin cushion (reported, not hidden).
Stake = quarter-Kelly of the bankroll, capped at 5%; a practical floor is shown because Kelly on ~1-4% edges is cents.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import betting_math as bm
import nba_halftime as nh
import nba_sheet_picks as nsp
import pwin_ensemble as pe
import sheet_picks as sp

BANKROLL = 30.0


def ucl_rows(ctx, sheet: dict) -> list[dict]:
    rows = []
    for name, m in sheet.items():
        rr, _, _ = sp.price_match(ctx, name, m)
        low = [n for n in (m["home"], m["away"]) if ctx.games.get(pe.cu.normalize(n), 0) < 15]
        for r in rr:
            r = {**r, "league": "UCL", "market": r["key"], "low": low}
            r["warn"] = sp.warnings(r, low)
            rows.append(r)
    return rows


def nba_rows(nctx, sheet: dict, day, params) -> list[dict]:
    rows = []
    for name, g in sheet.items():
        rr, info = nsp.price_game(nctx, name, g, day, params)
        for r in rr:
            r = {**r, "ev_eff": r.get("ev_promo", r["ev"]), "stale": info["stale"], "gap": info["gap"], "low": []}
            rows.append(r)
    return rows


def eff_ev(r: dict) -> float:
    return r.get("ev_eff", r["ev"])


LEG_MIN_ODDS, TICKET_MIN_ODDS = 1.25, 2.0          # payout floors only (a 1.02 "sure thing" pays nothing); EV is NEVER a filter


def clean(r: dict, min_p: float = 0.5) -> bool:
    """User rule: win probability decides. Only a minimum P(win) and a payout floor; warnings are shown, not used to exclude."""
    return r["p_win"] >= min_p and r["decimal"] >= LEG_MIN_ODDS


def kelly_stake(p: float, odds: float, bankroll: float = BANKROLL, frac: float = 0.25, cap: float = 0.05) -> float:
    f = bm.kelly(p, odds) * frac
    return round(bankroll * min(f, cap), 2)


def ticket(legs: list[dict]) -> dict:
    p = math.prod(l["p_win"] for l in legs)
    o = math.prod(l["decimal"] for l in legs)
    return {"legs": legs, "p": p, "odds": o, "ev": p * o - 1, "kelly": kelly_stake(p, o)}


def best_combos(pool: list[dict], n: int, k: int = 3, min_odds: float = TICKET_MIN_ODDS, max_odds: float = 12.0) -> list[dict]:
    """Best n-leg tickets by P(win) among legs from different matches, ticket odds >= the payout floor (EV not used)."""
    out = []
    for combo in itertools.combinations(pool, n):
        if len({l["match"] for l in combo}) < n:
            continue
        t = ticket(list(combo))
        if min_odds <= t["odds"] <= max_odds:
            out.append(t)
    return sorted(out, key=lambda t: (-round(t["p"], 4), -t["ev"]))[:k]


def fmt_leg(l: dict) -> str:
    extra = f" (EV con reembolso {l['ev_promo']*100:+.1f}%)" if "ev_promo" in l else ""
    return f"{l['pick']} [{l['match']}] P {l['p_win']*100:.1f}% @ {l['decimal']:.2f} EV {l['ev']*100:+.1f}%{extra}"


def fmt_ticket(t: dict) -> str:
    head = f"P(ganar todo) {t['p']*100:.1f}% | cuota {t['odds']:.2f} -> $10 pagan ${10*t['odds']:.2f} | EV {t['ev']*100:+.1f}% (informativo)"
    return head + "\n" + "\n".join(f"      · {fmt_leg(l)}" for l in t["legs"])


def main() -> None:
    import datetime
    day = datetime.date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else datetime.date.today()
    ucl_sheet = json.loads(Path(sys.argv[1]).read_text())["matches"]
    nba_sheet = json.loads(Path(sys.argv[2]).read_text())["matches"]
    soc = pe.DATA / "soccer"
    sctx = pe.build_soccer_ctx([soc / "club_results.csv", soc / "extra_league_results.csv", soc / "uefa_results.csv"])
    nctx = pe.build_nba_ctx([pe.DATA / "nba_historical.csv", pe.DATA / "nba_games_2526.csv"])
    params = nh.load_params()
    U, N = ucl_rows(sctx, ucl_sheet), nba_rows(nctx, nba_sheet, day, params)
    uc, nc = [r for r in U if clean(r)], [r for r in N if clean(r)]
    print(f"Candidatos (P(win) >= 50%, cuota >= {LEG_MIN_ODDS}): UCL {len(uc)} de {len(U)}, NBA {len(nc)} de {len(N)} | promo medio tiempo: {'ajustada' if params.get('fitted') else 'por defecto'}\n"
          f"Regla: manda la probabilidad de ganar; el EV va al final y es solo informativo.\n")
    rank = lambda rs: sorted(rs, key=lambda r: (-round(r["p_win"], 3), -r["decimal"]))

    def best_per_match(rs):
        d = {}
        for r in rank(rs):
            d.setdefault(r["match"], r)
        return list(d.values())

    for title, pool_rows in (("UCL", uc), ("NBA", nc)):
        print(f"=== {title} ===")
        print("SENCILLAS — mayor P(win) (una por partido):")
        for r in best_per_match(pool_rows)[:5]:
            warn = f"   !! {'; '.join(r['warn'])}" if r.get("warn") else (f"   !! ratings de temporada pasada" if r.get("stale") else "")
            print(f"  {fmt_leg(r)}{warn}")
        pool = best_per_match(pool_rows)
        for n in (3, 2):
            combos = best_combos(pool, n, k=2)
            if combos:
                print(f"PARLAY DE {n} (partidos distintos), mayor P(win), cuota total >= {TICKET_MIN_ODDS}:")
                for t in combos:
                    print("  " + fmt_ticket(t))
        print()
    print("=== COMBINADO UCL + NBA (partidos distintos) ===")
    mixed = best_per_match(uc)[:6] + best_per_match(nc)
    for n in (3, 2):
        res = [t for t in best_combos(mixed, n, k=60) if {l["league"] for l in t["legs"]} == {"UCL", "NBA"}]
        print(f"COMBINADO DE {n}:")
        for t in res[:2]:
            print("  " + fmt_ticket(t))
    json.dump({"ucl": U, "nba": N}, open(Path("/tmp/portfolio_rows.json"), "w"), default=str)


if __name__ == "__main__":
    main()

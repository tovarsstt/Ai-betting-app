#!/usr/bin/env python3
"""
judge_slate.py — run a whole slate through the winner-first Judge.

  python3 scripts/judge_slate.py data/slates/nfl-2026-week3-sunday.json \
      [--sims 2000000] [--min-decimal 1.25] [--out reports/nfl-2026-week3-judge]

Reads the slate JSON used by scripts/slate-sim.ts (moneylines per book, spread,
total, notes, sources) plus optional per-game "conditions" (cited injuries /
lineup facts) and "offers" (alt lines at your book, e.g. Stake).
Prints a markdown report; --out also writes <out>.md and <out>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import winner_judge as wj  # noqa: E402


DATA = Path(__file__).resolve().parent.parent / "data"


def season_context(sport: str) -> dict:
    """Ratings season (team_off_def.json) + current-season records if loaded."""
    ctx: dict = {}
    try:
        tod = json.loads((DATA / "team_off_def.json").read_text()).get(sport.lower(), {})
        ctx["ratings_season"] = tod.get("season")
    except (OSError, ValueError):
        pass
    rec_file = DATA / f"{sport.lower()}_2026_records.json"
    if rec_file.exists():
        rec = json.loads(rec_file.read_text())
        ctx["season"] = rec.get("season")
        ctx["records"] = rec.get("records", {})
    return ctx


def to_judge_games(slate: dict) -> list[dict]:
    default = slate.get("default_price", -110)
    ctx = season_context(slate.get("sport", "NFL"))
    recs = ctx.get("records", {})
    games = []
    for g in slate["games"]:
        books = [b for b in g.get("moneylines", []) if b.get("home") is not None and b.get("away") is not None]
        fair = [wj.devig_pair(b["home"], b["away"])[0] for b in books]
        best = {}
        for side in ("home", "away"):
            prices = [b[side] for b in g.get("moneylines", []) if b.get(side) is not None]
            if prices:
                best[side] = max(prices, key=wj.to_decimal)
        sp, tot = g.get("spread"), g.get("total")
        games.append({
            "sport": slate.get("sport", "NFL"),
            "home": g["home"], "away": g["away"], "id": g["id"],
            "neutral": g.get("neutral", False),
            "moneyline": best,
            "ml_consensus_home": sum(fair) / len(fair) if fair else None,
            "spread": ({"home_line": sp["home"], "home_price": sp.get("home_price", default),
                        "away_price": sp.get("away_price", default)} if sp else None),
            "total": ({"points": tot["points"], "over_price": tot.get("over_price", default),
                       "under_price": tot.get("under_price", default)} if tot else None),
            "conditions": g.get("conditions"),
            "offers": g.get("offers"),
            "agents": g.get("agents"),
            "ratings_season": ctx.get("ratings_season"),
            "season": ctx.get("season"),
            "records": ({"home": recs.get(g["home"]), "away": recs.get(g["away"])} if recs else None),
        })
    return games


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def to_markdown(slate: dict, res: dict, elapsed: float, sims: int) -> str:
    L = [f"# Judge — {slate['slate']}", ""]
    L.append(f"Rule: **win probability first, price second.** {sims:,} Monte Carlo games per matchup + "
             f"{sims:,} Bernoulli slips per parlay. NFL σ={res['nfl_sigma']} (fitted to this slate). "
             f"Ran in {elapsed:.1f}s.")
    L.append(f"Lines: {slate.get('captured_at', '?')} — {slate.get('capture_method', '')}")
    L.append("")
    L.append("## Best winning pick per game (ranked by win %)")
    L.append("")
    L.append("| # | Game | Pick | Win % | 2M-sim % | Market | Ratings | Grade | Price | Fair | EV (2nd) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, b in enumerate(res["board"], 1):
        ln = b["lenses"]
        L.append(f"| {i} | {b['game']} | **{b['label']}** | **{pct(b['win_prob'])}** | {pct(ln.get('sim'))} | "
                 f"{pct(ln.get('market'))} | {pct(ln.get('ratings'))} | {b['grade']} | {b['decimal']:.2f} | "
                 f"{b['fair_decimal']} | {b['ev_pct']:+.1f}% |")
    L.append("")
    L.append("## Best winning parlays (Bernoulli sims, one leg per game)")
    L.append("")
    L.append("| Legs | Hit % (sim) | Hit % (exact) | Payout | EV (2nd) |")
    L.append("|---|---|---|---|---|")
    for p in res["winning_parlays"]:
        L.append(f"| {'<br>'.join(p['legs'])} | **{pct(p['sim_hit_rate'])}** | {pct(p['exact_hit_rate'])} | "
                 f"{p['decimal']:.2f} | {p['ev_pct']:+.1f}% |")
    L.append("")
    L.append("## Per game — every market, every lens")
    for g in res["games"]:
        L.append("")
        em = g["expected_home_margin"]
        rec = g.get("records") or {}
        rec_txt = f" — 2026: away {rec.get('away')}, home {rec.get('home')}" if rec.get("home") else ""
        L.append(f"### {g['game']}{rec_txt}")
        L.append(f"Expected home margin — blended {em['blended']:+.1f} | market {em.get('market', float('nan')):+.1f}"
                 + (f" | ratings {em['ratings']:+.1f}" if "ratings" in em else " | ratings n/a")
                 + f" · weights {g['weights']}")
        tp = g.get("total_projection") or {}
        if tp.get("ratings") is not None:
            L.append(f"- 🔢 Total: market {tp['market']} · offense×defense ratings {tp['ratings']} "
                     f"(home {tp.get('home_pts')}, away {tp.get('away_pts')}, {tp.get('season')} data) "
                     f"→ blended {tp['blended']}")
        prof = tp.get("matchup_profile") or {}
        for side in ("away", "home"):
            d = prof.get(f"{side}_defense")
            if d:
                L.append(f"- 🛡️ {side} defense allows {d['pass_allowed_pg']} pass yds / "
                         f"{d['rush_allowed_pg']} rush yds per game")
        for c in (g.get("ratings_detail") or {}).get("conditions_applied", []):
            L.append(f"- 🏥 {c}")
        for f in g["flags"]:
            L.append(f"- ⚠️ {f}")
        L.append("")
        L.append("| Market | Win % | Sim % | Lenses | Grade | Price | EV |")
        L.append("|---|---|---|---|---|---|---|")
        for m in g["markets"]:
            lens = " · ".join(f"{k} {v * 100:.0f}" for k, v in m["lenses"].items())
            L.append(f"| {m['label']} | {pct(m['win_prob'])} | {pct(m['lenses']['sim'])} | {lens} | "
                     f"{m['grade']} | {m['decimal']:.2f} | {m['ev_pct']:+.1f}% |")
    L.append("")
    L.append("Grades: LOCK ≥70% · PICK ≥62% · LEAN below · SPLIT = a weighted lens disagrees on the side. "
             "Win % never means guaranteed; EV shows whether the price pays enough for that win rate.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slate")
    ap.add_argument("--sims", type=int, default=wj.N_SIMS)
    ap.add_argument("--min-decimal", type=float, default=wj.MIN_DECIMAL)
    ap.add_argument("--out")
    a = ap.parse_args()
    slate = json.loads(Path(a.slate).read_text())
    t = time.time()
    res = wj.judge_slate(to_judge_games(slate), n_sims=a.sims, min_decimal=a.min_decimal)
    md = to_markdown(slate, res, time.time() - t, a.sims)
    print(md)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(f"{a.out}.md").write_text(md + "\n")
        Path(f"{a.out}.json").write_text(json.dumps(res, indent=2, default=float) + "\n")
        print(f"wrote {a.out}.md / .json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

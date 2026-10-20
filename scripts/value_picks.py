"""
value_picks.py — today's UCL + NBA: P(win) from the FULL toolkit (pwin_ensemble) vs DraftKings moneylines.

Rules (CLAUDE.md "P(win) Rule"): every applicable tool runs and is shown; order is P(win) first ->
odds/payout -> EV last; rank by P(win) (likely winners before longshots); RECOMMEND only when EV > 0.
Warnings (low-sample club, big model-vs-market gap, wide tool spread, longshot) are printed next to a pick,
never used to hide it. Lines come from ESPN's public scoreboard (DraftKings provider) — no Odds API.
Missing lines are reported, never invented.

    python3 scripts/value_picks.py [YYYY-MM-DD]      # live; needs ESPN reachable
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import fetch_europe_data as fe
import pwin_ensemble as pe

DATA = Path(__file__).parent.parent / "data"
MIN_EV = 0.0
GAP_WARN = 0.15       # model-vs-market gap (prob points) worth a warning
SPREAD_WARN = 0.20    # max-min across model tools worth a warning
LONGSHOT = 0.35


def am_to_dec(a: int) -> float:
    return a / 100 + 1 if a > 0 else 100 / -a + 1


def parse_american(x) -> int | None:
    try:
        return int(str(x).replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def parse_moneyline(odds_list: list | None) -> dict | None:
    """ESPN odds list -> {'home','away'(,'draw'): american int, 'provider'}. Uses the CLOSE (current)
    price, falling back to open. Returns None unless both home and away prices exist."""
    for o in odds_list or []:
        ml = o.get("moneyline") or {}
        out: dict = {}
        for side in ("home", "away", "draw"):
            node = ml.get(side) or {}
            px = parse_american((node.get("close") or {}).get("odds"))
            if px is None:
                px = parse_american((node.get("open") or {}).get("odds"))
            if px is None and side == "draw":
                px = parse_american((o.get("drawOdds") or {}).get("moneyLine"))
            if px is not None:
                out[side] = px
        if "home" in out and "away" in out:
            out["provider"] = (o.get("provider") or {}).get("name", "?")
            return out
    return None


def events_from_scoreboard(data: dict) -> list[dict]:
    """Raw ESPN scoreboard -> compact events (name, date, state, home, away, odds)."""
    out = []
    for ev in data.get("events", []) or []:
        try:
            comp = ev["competitions"][0]
            side = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
            out.append({"name": ev.get("name"), "date": ev["date"], "state": ev["status"]["type"].get("state"),
                        "home": side["home"], "away": side["away"], "odds": comp.get("odds")})
        except (KeyError, IndexError, TypeError):
            continue
    return out


SECTION_ORDER = ["UCL", "NBA"]   # project rule: Champions League first, then NBA


def devig(decimals: list[float]) -> list[float]:
    inv = [1 / d for d in decimals]
    t = sum(inv)
    return [v / t for v in inv]


def parse_total(odds_item: dict) -> tuple[float, float] | None:
    """ESPN odds object -> (line, P(over)) from the CLOSE over/under prices, devigged. None if either side is missing."""
    t = (odds_item or {}).get("total") or {}
    ov, un = (t.get("over") or {}).get("close") or {}, (t.get("under") or {}).get("close") or {}
    po, pu = parse_american(ov.get("odds")), parse_american(un.get("odds"))
    try:
        line = float(str(ov.get("line", "")).lstrip("ou"))
    except ValueError:
        return None
    if po is None or pu is None:
        return None
    return line, devig([am_to_dec(po), am_to_dec(pu)])[0]


def rows_from_agg(agg: dict, ml: dict, labels: dict, match: str, flags: list[str] | None = None, league: str = "UCL") -> list[dict]:
    """One row per outcome: final P(win) from the ensemble, price, payout, EV (last)."""
    rows = []
    for side, label in labels.items():
        if side not in ml or side not in agg["final"]:
            continue
        dec = am_to_dec(ml[side])
        p = agg["final"][side]
        rows.append({"match": match, "pick": label, "p_win": p, "p_model": agg["model_mean"][side] if agg["model_mean"] else None,
                     "p_market": agg["market_mean"][side] if agg["market_mean"] else None,
                     "spread": agg["model_spread"].get(side, 0.0), "american": ml[side], "decimal": dec,
                     "payout_10": 10 * dec, "ev": p * dec - 1, "flags": list(flags or []), "league": league,
                     "n_tools": agg["n_model_tools"] + agg["n_market_tools"]})
    return rows


def warnings(r: dict) -> list[str]:
    w = list(r["flags"])
    if r["p_model"] is not None and r["p_market"] is not None and abs(r["p_model"] - r["p_market"]) > GAP_WARN:
        w.append(f"model vs market gap {abs(r['p_model'] - r['p_market'])*100:.0f} pts")
    if r["spread"] > SPREAD_WARN:
        w.append(f"tools disagree ({r['spread']*100:.0f} pt spread)")
    if r["p_win"] < LONGSHOT:
        w.append("longshot")
    return w


def rank(rows: list[dict]) -> list[dict]:
    """Win probability first, EV second (project rule)."""
    return sorted(rows, key=lambda r: (-round(r["p_win"], 3), -r["ev"]))


def best_per_match(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for r in rows:
        if r["match"] not in best or r["p_win"] > best[r["match"]]["p_win"]:
            best[r["match"]] = r
    return rank(list(best.values()))


def fmt(r: dict) -> str:
    w = warnings(r)
    return (f"{r['pick']} [{r['match']}]  P(win) {r['p_win']*100:.1f}% | {r['american']:+d} -> $10 pays ${r['payout_10']:.2f}"
            f" | EV {r['ev']*100:+.1f}%" + (f"   !! {'; '.join(w)}" if w else ""))


def render(rows_all: list[dict], skipped: list[str], tool_blocks: list[str] | None = None) -> str:
    """UCL section first, NBA second (project rule). Inside each: P(win) first, EV last, ranked by P(win)."""
    lines: list[str] = []
    leagues = SECTION_ORDER + sorted({r.get("league", "UCL") for r in rows_all} - set(SECTION_ORDER))
    for lg in leagues:
        rows = [r for r in rows_all if r.get("league", "UCL") == lg]
        if not rows:
            continue
        lines += [f"=== {lg} ===", "MOST LIKELY WINNER PER GAME (P(win) first, EV last)"]
        lines += [f"- {fmt(r)}" for r in best_per_match(rows)]
        picks = rank([r for r in rows if r["ev"] > MIN_EV])
        lines += ["", f"{lg} RECOMMENDED — EV > 0, ordered by P(win):" if picks else f"{lg} RECOMMENDED: none — no side has EV > 0 at these prices."]
        lines += [f"* {fmt(r)}" for r in picks]
        lines.append("")
    lines += [f"SKIPPED: {x}" for x in sorted(skipped, key=lambda x: (0 if "@" not in x else 1, x))]
    if tool_blocks:
        lines += ["", "PER-TOOL DETAIL (UCL first, then NBA; H/D/A = home/draw/away):"] + tool_blocks
    return "\n".join(lines)


def _odds0(ev: dict) -> dict:
    return (ev.get("odds") or [{}])[0] or {}


def soccer_rows(events: list[dict], ctx) -> tuple[list[dict], list[str], list[str]]:
    rows, skipped, blocks = [], [], []
    for ev in events:
        match = f"{ev['home']} vs {ev['away']}"
        if ev["state"] != "pre":
            skipped.append(f"{match} (already {ev['state']})"); continue
        ml = parse_moneyline(ev["odds"])
        if not ml or "draw" not in ml:
            skipped.append(f"{match} (no 3-way moneyline from ESPN)"); continue
        mtotal = None
        tot = parse_total(_odds0(ev))
        if tot:
            pw = pe.bm.devig_power([am_to_dec(ml["home"]), am_to_dec(ml["draw"]), am_to_dec(ml["away"])])
            mtotal = pe.market_total_from_ou(float(pw[0]), float(pw[2]), tot[1], tot[0])
        tools = pe.soccer_tools(ctx, ev["home"], ev["away"], ml, _odds0(ev).get("overUnder"), market_total=mtotal)
        agg = pe.aggregate(tools)
        if "error" in agg:
            skipped.append(f"{match} ({agg['error']})"); continue
        low = [n for n in (ev["home"], ev["away"]) if ctx.games.get(pe.cu.normalize(n), 0) < 15]
        flags = [f"LOW-SAMPLE club: {', '.join(low)}"] if low else []
        label = {"home": f"{ev['home']} to win", "draw": "Draw", "away": f"{ev['away']} to win"}
        rows += rows_from_agg(agg, ml, label, match, flags, league="UCL")
        blocks.append(f"  {match}  ({agg['n_model_tools']} model + {agg['n_market_tools']} market tools; not run: {', '.join(agg['not_run']) or 'none'})\n" + pe.tools_table(tools))
    return rows, skipped, blocks


def nba_rows(events: list[dict], ctx) -> tuple[list[dict], list[str], list[str]]:
    rows, skipped, blocks = [], [], []
    for ev in events:
        match = f"{ev['away']} @ {ev['home']}"
        if ev["state"] != "pre":
            skipped.append(f"{match} (already {ev['state']})"); continue
        ml = parse_moneyline(ev["odds"])
        if not ml:
            skipped.append(f"{match} (no moneyline from ESPN)"); continue
        day = datetime.date.fromisoformat(ev["date"][:10])
        tools = pe.nba_tools(ctx, ev["home"], ev["away"], day, ml, _odds0(ev).get("spread"))
        agg = pe.aggregate(tools)
        if "error" in agg:
            skipped.append(f"{match} ({agg['error']})"); continue
        rows += rows_from_agg(agg, {k: v for k, v in ml.items() if k != "draw"}, {"home": f"{ev['home']} ML", "away": f"{ev['away']} ML"}, match, league="NBA")
        blocks.append(f"  {match}  ({agg['n_model_tools']} model + {agg['n_market_tools']} market tools; not run: {', '.join(agg['not_run']) or 'none'})\n" + pe.tools_table(tools))
    return rows, skipped, blocks


def main() -> None:
    day = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    soc = DATA / "soccer"
    sctx = pe.build_soccer_ctx([soc / "club_results.csv", soc / "extra_league_results.csv", soc / "uefa_results.csv"])
    nctx = pe.build_nba_ctx([DATA / "nba_historical.csv", DATA / "nba_games_2526.csv"])
    base = "https://site.api.espn.com/apis/site/v2/sports"
    ucl = events_from_scoreboard(json.loads(fe._get(f"{base}/soccer/uefa.champions/scoreboard?dates={day:%Y%m%d}")))
    nba = events_from_scoreboard(json.loads(fe._get(f"{base}/basketball/nba/scoreboard?dates={day:%Y%m%d}")))
    r1, s1, b1 = soccer_rows(ucl, sctx)
    r2, s2, b2 = nba_rows(nba, nctx)
    print(f"{day} | final P = {int(pe.MODEL_WEIGHT*100)}% model-tool mean + {int((1-pe.MODEL_WEIGHT)*100)}% market-tool mean (judgement weight, not fitted)"
          f" | NBA ratings as of {nctx.st.as_of}")
    print(render(r1 + r2, s1 + s2, b1 + b2))


if __name__ == "__main__":
    main()

"""
value_picks.py — today's UCL + NBA: model P(win) vs DraftKings moneylines (via ESPN scoreboard).

Rules (CLAUDE.md): rank by WIN PROBABILITY first, edge (+EV) second; favour likely winners over
longshots. Report order per pick: P(win) -> odds/payout -> EV last. A pick is only RECOMMENDED when
its EV > 0; otherwise it is listed as 'no value' (a likely winner at a bad price still loses money).

Probability = MODEL_WEIGHT * model + (1 - MODEL_WEIGHT) * devigged market. The market is the
stronger prior; the model only moves it where it has real disagreement. No Odds API is used:
lines come from ESPN's public scoreboard (DraftKings provider). Missing lines are reported, never made up.

    python3 scripts/value_picks.py [YYYY-MM-DD]      # live; needs ESPN reachable
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import calibrate_ucl as cu
import fetch_europe_data as fe
import nba_stack as ns
import ucl_model as um

DATA = Path(__file__).parent.parent / "data"
MODEL_WEIGHT = 0.35
MIN_EV = 0.0
MIN_P_WIN = 0.50      # priority is WINNING: only back the side that is more likely than not to win
MAX_DISAGREE = 0.15   # model vs market gap above this is treated as model error, not edge (validation showed no proven edge)


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


def devig(decimals: list[float]) -> list[float]:
    inv = [1 / d for d in decimals]
    s = sum(inv)
    return [v / s for v in inv]


def build_rows(p_model: dict[str, float], ml: dict, label_by_side: dict[str, str], match: str,
               w: float = MODEL_WEIGHT) -> list[dict]:
    sides = [s for s in ("home", "draw", "away") if s in ml and s in p_model]
    dec = {s: am_to_dec(ml[s]) for s in sides}
    fair = dict(zip(sides, devig([dec[s] for s in sides])))
    rows = []
    for s in sides:
        p = w * p_model[s] + (1 - w) * fair[s]
        rows.append({"match": match, "pick": label_by_side[s], "p_win": p, "p_model": p_model[s], "p_market": fair[s],
                     "american": ml[s], "decimal": dec[s], "payout_10": 10 * dec[s], "ev": p * dec[s] - 1})
    return rows


def reject_reason(r: dict) -> str | None:
    """Why a +EV side is NOT recommended (None = passes every guard)."""
    if r["ev"] <= MIN_EV:
        return "EV <= 0"
    if r["p_win"] < MIN_P_WIN:
        return f"longshot (P(win) {r['p_win']*100:.0f}% < {MIN_P_WIN*100:.0f}%)"
    if abs(r["p_model"] - r["p_market"]) > MAX_DISAGREE:
        return f"model vs market gap {abs(r['p_model'] - r['p_market'])*100:.0f} pts > {MAX_DISAGREE*100:.0f} (likely model error)"
    if "LOW-SAMPLE" in r["match"]:
        return "low-sample club rating"
    return None


def rank(rows: list[dict]) -> list[dict]:
    """Win probability first, EV second (project rule)."""
    return sorted(rows, key=lambda r: (-round(r["p_win"], 3), -r["ev"]))


def best_per_match(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for r in rows:
        if r["match"] not in best or r["p_win"] > best[r["match"]]["p_win"]:
            best[r["match"]] = r
    return rank(list(best.values()))


def render(rows_all: list[dict], skipped: list[str]) -> str:
    lines = ["MOST LIKELY WINNER PER GAME (ranked by P(win); EV last)"]
    for r in best_per_match(rows_all):
        why = reject_reason(r)
        tag = "RECOMMENDED" if why is None else ("model +EV but NOT recommended: " + why if r["ev"] > MIN_EV else "no value")
        lines.append(f"- {r['pick']} [{r['match']}]  P(win) {r['p_win']*100:.1f}% (model {r['p_model']*100:.1f} / mkt {r['p_market']*100:.1f})"
                     f" | {r['american']:+d} -> $10 pays ${r['payout_10']:.2f} | EV {r['ev']*100:+.1f}%  [{tag}]")
    picks = rank([r for r in rows_all if reject_reason(r) is None])
    lines.append("")
    lines.append("RECOMMENDED (P(win) >= 50%, EV > 0, model agrees with market within 15 pts):" if picks
                 else "RECOMMENDED: none — nothing clears every guard (P(win) >= 50%, EV > 0, sane model-market gap).")
    for r in picks:
        lines.append(f"* {r['pick']} [{r['match']}] P(win) {r['p_win']*100:.1f}% | {r['american']:+d} | EV {r['ev']*100:+.1f}%")
    flagged = rank([r for r in rows_all if r["ev"] > MIN_EV and reject_reason(r)])
    if flagged:
        lines.append("")
        lines.append("MODEL-ONLY +EV, NOT recommended (read why):")
        for r in flagged:
            lines.append(f"  x {r['pick']} [{r['match']}] P(win) {r['p_win']*100:.1f}% | {r['american']:+d} | EV {r['ev']*100:+.1f}% -> {reject_reason(r)}")
    for s_ in skipped:
        lines.append(f"SKIPPED: {s_}")
    return "\n".join(lines)


def soccer_rows(events: list[dict], elo: dict, model: um.EloGoalModel, games: dict) -> tuple[list[dict], list[str]]:
    rows, skipped = [], []
    for ev in events:
        match = f"{ev['home']} vs {ev['away']}"
        if ev["state"] != "pre":
            skipped.append(f"{match} (already {ev['state']})"); continue
        ml = parse_moneyline(ev["odds"])
        if not ml or "draw" not in ml:
            skipped.append(f"{match} (no 3-way moneyline from ESPN)"); continue
        r = um.price_match(cu.normalize(ev["home"]), cu.normalize(ev["away"]), elo, model)
        if "error" in r:
            skipped.append(f"{match} ({r['error']})"); continue
        low = [n for n in (ev["home"], ev["away"]) if games.get(cu.normalize(n), 0) < 15]
        label = {"home": f"{ev['home']} to win", "draw": "Draw", "away": f"{ev['away']} to win"}
        for row in build_rows(r["model_only"], ml, label, match + (f"  (LOW-SAMPLE: {', '.join(low)})" if low else "")):
            rows.append(row)
    return rows, skipped


def nba_rows(events: list[dict], st, stacker) -> tuple[list[dict], list[str]]:
    rows, skipped = [], []
    for ev in events:
        match = f"{ev['away']} @ {ev['home']}"
        if ev["state"] != "pre":
            skipped.append(f"{match} (already {ev['state']})"); continue
        ml = parse_moneyline(ev["odds"])
        if not ml:
            skipped.append(f"{match} (no moneyline from ESPN)"); continue
        day = datetime.date.fromisoformat(ev["date"][:10])
        ph = ns.predict_fixture(st, stacker, ev["home"], ev["away"], day)
        if ph is None:
            skipped.append(f"{match} (team not in rating history)"); continue
        label = {"home": f"{ev['home']} ML", "away": f"{ev['away']} ML"}
        rows += build_rows({"home": ph, "away": 1 - ph}, {k: v for k, v in ml.items() if k != "draw"}, label, match)
    return rows, skipped


def main() -> None:
    day = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
    soc = DATA / "soccer"
    elo = json.loads((soc / "elo_ratings.json").read_text())
    m = json.loads((soc / "ucl_elo_goal_model.json").read_text())
    model = um.EloGoalModel(a=m["a"], h=m["h"], b=m["b"], calibrated=m["calibrated"], n_matches=m["n_matches"])
    games = json.loads((soc / "club_games.json").read_text())
    base = "https://site.api.espn.com/apis/site/v2/sports"
    ucl = events_from_scoreboard(json.loads(fe._get(f"{base}/soccer/uefa.champions/scoreboard?dates={day:%Y%m%d}")))
    nba = events_from_scoreboard(json.loads(fe._get(f"{base}/basketball/nba/scoreboard?dates={day:%Y%m%d}")))
    rows, skipped = soccer_rows(ucl, elo, model, games)
    g = ns.load_games(DATA / "nba_historical.csv", DATA / "nba_games_2526.csv")
    st, stacker = ns.fit_final(g)
    nrows, nskipped = nba_rows(nba, st, stacker)
    print(f"{day} | UCL model calibrated on {model.n_matches} matches | NBA ratings as of {st.as_of}")
    print(render(rows + nrows, skipped + nskipped))


if __name__ == "__main__":
    main()

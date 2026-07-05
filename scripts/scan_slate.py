#!/usr/bin/env python3
"""
scan_slate.py — auto-scan a whole soccer slate for +EV edges.

Brain = the SAME market-calibrated Dixon-Coles engine as /predict-soccer.
For every game it devigs the 1X2, fits lambdas, builds the score matrix, then
computes model EV across 1X2 / totals / BTTS / double-chance and ranks the best
edge per game. This is the "stop copy-pasting" piece: feed it a slate, it tells
you where the value is.

Odds source is pluggable:
  default : reads a local JSON fixture (data/slate_fixture.json) — safe, no API.
  --live  : pulls the live slate from the-odds-api.com (uses ODDS_API_KEY).
            REAL app runs only — never in dev/test (project rule: no quota APIs
            during debug). The fetch is isolated so flipping the flag is the only
            thing that ever touches the network.
"""
import sys, json, os, argparse, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import soccer_markets as sm

VALUE_GATE = 0.02            # flag a market at >= +2% model EV
BASE = Path(__file__).parent.parent
FIXTURE = BASE / "data" / "slate_fixture.json"


def dec2am(d: float) -> float:
    return (d - 1) * 100 if d >= 2 else -100 / (d - 1)


def _ev_total(tot, od, line, side):
    """Back-bet EV for an asian total (handles .0 push + .25/.75 split)."""
    if abs((line * 2) - round(line * 2)) > 1e-9:
        return (_ev_total(tot, od, line - 0.25, side) +
                _ev_total(tot, od, line + 0.25, side)) / 2
    w = l = 0.0
    for k, p in tot.items():
        if abs(k - line) < 1e-9:          # exact line -> push
            continue
        hit = (k > line) if side == "over" else (k < line)
        w += p if hit else 0.0
        l += 0.0 if hit else p
    return w * (od - 1) - l


def scan_game(game: dict) -> dict:
    """Calibrate one game off its 1X2 and return ranked market edges."""
    ho, dr, ao = game["h2h"]
    dv = sm.devig_3way(dec2am(ho), dec2am(dr), dec2am(ao))
    lh, la, _ = sm.solve_lambdas_from_1x2(dv["home"], dv["draw"], dv["away"])
    mat = sm.score_matrix(lh, la, rho=sm.DEFAULT_RHO)
    N, M = len(mat), len(mat[0])
    tot = collections.defaultdict(float)
    for h in range(N):
        for a in range(M):
            tot[h + a] += mat[h][a]
    P = lambda c: sum(mat[h][a] for h in range(N) for a in range(M) if c(h, a))

    # 4th slot = the BOOK decimal price the EV was computed against, so
    # downstream consumers (bank_builder) never have to reverse-engineer it.
    edges = []
    edges.append(("Home ML", dv["home"] * ho - 1, dv["home"], ho))
    edges.append(("Away ML", dv["away"] * ao - 1, dv["away"], ao))
    for line, ov, un in (game.get("totals") or []):
        edges.append((f"Over {line}", _ev_total(tot, ov, line, "over"),
                      P(lambda h, a: h + a > line), ov))
        edges.append((f"Under {line}", _ev_total(tot, un, line, "under"),
                      P(lambda h, a: h + a < line), un))
    if game.get("btts"):
        y, n = game["btts"]
        bt = P(lambda h, a: h >= 1 and a >= 1)
        edges.append(("BTTS Yes", bt * y - 1, bt, y))
        edges.append(("BTTS No", (1 - bt) * n - 1, 1 - bt, n))
    if game.get("dc_x2"):                   # draw-or-away
        x2 = P(lambda h, a: a >= h)
        edges.append(("DC X2", x2 * game["dc_x2"] - 1, x2, game["dc_x2"]))
    if game.get("dc_1x"):                   # home-or-draw
        d1x = P(lambda h, a: h >= a)
        edges.append(("DC 1X", d1x * game["dc_1x"] - 1, d1x, game["dc_1x"]))

    edges.sort(key=lambda e: e[1], reverse=True)
    return {
        "name": game["name"],
        "devig": dv,
        "xg_total": round(sum(k * p for k, p in tot.items()), 2),
        "edges": edges,
    }


def kickoff_label(iso: str | None) -> str:
    """Local 'Fri 03 Jul 13:00' from the API's ISO commence_time ('' if absent)."""
    if not iso:
        return ""
    from datetime import datetime
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return t.strftime("%a %d %b %H:%M")
    except ValueError:
        return ""


def scan_slate(games: list) -> None:
    games = sorted(games, key=lambda g: g.get("commence_time") or "")
    results = [scan_game(g) for g in games]
    picks = []
    print(f"\n{'='*64}\n  SLATE SCAN — {len(games)} games  (value gate +{VALUE_GATE*100:.0f}%)\n{'='*64}")
    for g, r in zip(games, results):
        best_ev, best_mkt, best_p = r["edges"][0][1], r["edges"][0][0], r["edges"][0][2]
        tag = "  <== EDGE" if best_ev >= VALUE_GATE else ""
        ko = kickoff_label(g.get("commence_time"))
        when = f"  [{ko}]" if ko else ""
        print(f"\n• {r['name']}{when}  (xG {r['xg_total']}, vig {r['devig']['vig_pct']}%)")
        print(f"    best: {best_mkt:10} model {best_p*100:4.1f}%  EV {best_ev*100:+5.1f}%{tag}")
        if best_ev >= VALUE_GATE:
            picks.append((best_ev, r["name"], best_mkt, best_p, ko))
    print(f"\n{'-'*64}")
    if picks:
        picks.sort(reverse=True)
        print("  PLAYS (ranked):")
        for ev, name, mkt, p, ko in picks:
            when = f"  [{ko}]" if ko else ""
            print(f"    {ev*100:+5.1f}%  {name} — {mkt} ({p*100:.0f}%){when}")
    else:
        print("  No edges clear the gate — disciplined PASS on the whole slate.")
    print(f"{'-'*64}\n")


def normalize_2way_event(ev: dict) -> dict | None:
    """One the-odds-api event -> sharp-anchored 2-way game, or None.

    Pinnacle's devigged line is the fair-prob anchor: no Pinnacle price for
    the game means no candidate — we never guess a fair line. `best` is the
    highest available price per side across every book in the payload
    (line shopping is the whole 2-way edge)."""
    home, away = ev.get("home_team"), ev.get("away_team")
    if not home or not away:
        return None
    pin = None
    best = {home: (0.0, ""), away: (0.0, "")}
    for bk in ev.get("bookmakers", []):
        mk = next((m for m in bk.get("markets", []) if m.get("key") == "h2h"), None)
        if not mk:
            continue
        o = {x.get("name"): float(x.get("price", 0)) for x in mk.get("outcomes", [])}
        if not o.get(home) or not o.get(away):
            continue
        if bk.get("key") == "pinnacle":
            pin = (o[home], o[away])
        for side in (home, away):
            if o[side] > best[side][0]:
                best[side] = (o[side], bk.get("key", ""))
    if pin is None:
        return None
    return {
        "name": f"{home} v {away}", "home": home, "away": away,
        "pinnacle": list(pin),
        "best": [best[home][0], best[away][0]],
        "best_books": [best[home][1], best[away][1]],
        "commence_time": ev.get("commence_time"),
    }


def fetch_slate_2way_oddsapi(sport_key: str, regions="us,eu") -> list:
    """LIVE: 2-way ML slate for NBA/NFL/MLB/NHL/tennis keys. Real runs only."""
    import urllib.request
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise SystemExit("ODDS_API_KEY not set in env — cannot fetch live slate.")
    url = (f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
           f"?apiKey={key}&regions={regions}&markets=h2h&oddsFormat=decimal")
    with urllib.request.urlopen(url, timeout=15) as resp:
        raw = json.load(resp)
    return [g for g in (normalize_2way_event(ev) for ev in raw) if g]


def discover_tennis_keys(max_keys: int = 3) -> list[str]:
    """LIVE: active tennis_* sport keys via /v4/sports (a FREE endpoint —
    costs no quota). Capped so a busy tennis week can't drain credits."""
    import urllib.request
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise SystemExit("ODDS_API_KEY not set in env.")
    with urllib.request.urlopen(
            f"https://api.the-odds-api.com/v4/sports/?apiKey={key}", timeout=15) as resp:
        sports = json.load(resp)
    keys = [s["key"] for s in sports
            if s.get("active") and str(s.get("key", "")).startswith("tennis_")]
    return keys[:max_keys]


def fetch_slate_oddsapi(sport_key: str, regions="eu", markets="h2h,totals") -> list:
    """LIVE: pull a slate from the-odds-api.com. Real runs only (never in dev)."""
    import urllib.request
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise SystemExit("ODDS_API_KEY not set in env — cannot fetch live slate.")
    url = (f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
           f"?apiKey={key}&regions={regions}&markets={markets}&oddsFormat=decimal")
    with urllib.request.urlopen(url, timeout=15) as resp:
        raw = json.load(resp)
    games = []
    for ev in raw:
        bk = next((b for b in ev.get("bookmakers", []) if b["key"] == "pinnacle"),
                  (ev.get("bookmakers") or [None])[0])
        if not bk:
            continue
        mk = {m["key"]: m for m in bk["markets"]}
        h2h = mk.get("h2h")
        if not h2h:
            continue
        o = {x["name"]: x["price"] for x in h2h["outcomes"]}
        home, away = ev["home_team"], ev["away_team"]
        if home not in o or away not in o:
            continue
        draw = o.get("Draw")
        if draw is None:
            continue
        g = {"name": f"{home} v {away}", "h2h": [o[home], draw, o[away]], "totals": [],
             "commence_time": ev.get("commence_time")}
        if "totals" in mk:
            lines = collections.defaultdict(dict)
            for x in mk["totals"]["outcomes"]:
                lines[x["point"]][x["name"]] = x["price"]
            for pt, sides in sorted(lines.items()):
                if "Over" in sides and "Under" in sides:
                    g["totals"].append([pt, sides["Over"], sides["Under"]])
        games.append(g)
    return games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="pull live slate from the-odds-api (REAL runs only)")
    ap.add_argument("--sport", default="soccer_fifa_world_cup",
                    help="the-odds-api sport key (live mode)")
    ap.add_argument("--fixture", default=str(FIXTURE))
    args = ap.parse_args()

    if args.live:
        print(f"[scan_slate] LIVE pull: {args.sport} (uses ODDS_API_KEY quota)")
        games = fetch_slate_oddsapi(args.sport)
    else:
        games = json.load(open(args.fixture))["games"]
        print(f"[scan_slate] fixture mode: {args.fixture} (no API)")
    scan_slate(games)


if __name__ == "__main__":
    main()

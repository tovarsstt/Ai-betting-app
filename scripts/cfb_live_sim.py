"""Live CFB re-sim from the ESPN play-by-play: reads score, period, clock and every drive played so far, folds this game's drives into the teams' rates,
then simulates the rest of the game (possessions left from the clock, ~0.383 drives/min both teams combined) with cfb_box_sim's drive engine.
Usage: python3 scripts/cfb_live_sim.py EVENT_ID [--n 250000] [--first TEAMID:TD,FG,MFG,TO,DTD,NO] [--ball TEAMID] [--line HOME_HANDICAP ...]
--first fixes the outcome odds of the drive in progress (e.g. 1st&goal), --ball says who has the ball (default: team that did not run the last drive)."""
import sys, json, argparse, urllib.request
import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cfb_box_sim as S

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
DRIVES_PER_MIN = 0.383        # combined, both teams (23 drives / 60 min in the 31-game sample)
EXTRA_DRIVE = 0.5             # probability the drive count rounds up


def summary(eid: str) -> dict:
    return json.load(urllib.request.urlopen(f"{SITE}/summary?event={eid}", timeout=25))


def live_state(s: dict) -> dict:
    h = s["header"]["competitions"][0]
    st = h["status"]
    clock = st.get("displayClock", "0:00")
    mm, ss = (clock.split(":") + ["0"])[:2]
    period = int(st.get("period") or 1)
    sec_left_period = int(mm) * 60 + int(ss)
    remaining_min = max(0.0, (4 - period) * 15 + sec_left_period / 60.0) if st["type"]["description"] != "Halftime" else 30.0
    teams = {c["team"]["id"]: {"abbr": c["team"]["abbreviation"], "name": c["team"]["displayName"], "score": int(c.get("score") or 0), "home": c["homeAway"] == "home"} for c in h["competitors"]}
    for t in s["boxscore"]["teams"]:
        teams[t["team"]["id"]]["box"] = {x["name"]: x["displayValue"] for x in t["statistics"]}
    drives = [d for d in s["drives"]["previous"] if (d.get("displayResult") or d.get("result"))]
    return {"teams": teams, "remaining_min": remaining_min, "period": period, "status": st["type"]["description"], "drives": drives,
            "last_team": s["drives"]["previous"][-1]["team"]["id"] if s["drives"]["previous"] else None}


def with_live_game(games: dict, eid: str, state: dict) -> dict:
    pseudo = {"id": eid, "teams": {k: {"name": v["name"], "score": v["score"], "home": v["home"], "box": v["box"]} for k, v in state["teams"].items()},
              "drives": [{"team": d["team"]["id"], "result": d.get("displayResult") or d.get("result"), "yards": d.get("yards", 0), "plays": d.get("offensivePlays", 0)} for d in state["drives"]]}
    return {**games, "live_" + eid: pseudo}


def n_drives(rng, N: int, total: float, first_team_extra: bool) -> tuple:
    """split the drives left between the team with the ball and the other (alternating possessions)"""
    a = total / 2 + (0.5 if first_team_extra else 0.0)
    b = total / 2 - (0.5 if first_team_extra else 0.0)
    f = lambda x: int(np.floor(x)) + (rng.random(N) < (x - np.floor(x))).astype(int)
    return f(max(a, 0)), f(max(b, 0))


def simulate_rest(eid: str, n: int = 250_000, seed: int = 5, first: tuple | None = None, ball: str | None = None) -> dict:
    s = summary(eid)
    state = live_state(s)
    games = with_live_game(S.load_games(), eid, state)
    L = S.league_rates(games)
    ids = list(state["teams"])
    home = next(k for k in ids if state["teams"][k]["home"]); away = next(k for k in ids if k != home)
    TH, TA = S.team_tables(games, home), S.team_tables(games, away)
    p_h = S.matchup_probs(S.shrunk(TH["off"], TH["n_off"], L), S.shrunk(TA["def"], TA["n_def"], L), L)
    p_a = S.matchup_probs(S.shrunk(TA["off"], TA["n_off"], L), S.shrunk(TH["def"], TH["n_def"], L), L)
    rng = np.random.default_rng(seed)
    ball_team = ball or (home if state["last_team"] == away else away)
    total = state["remaining_min"] * DRIVES_PER_MIN
    extra, other = n_drives(rng, n, total, True)
    nh, na = (extra, other) if ball_team == home else (other, extra)
    H = S.sim_offense(rng, n, nh, p_h, TH, 1.0)
    A = S.sim_offense(rng, n, na, p_a, TA, 1.0)
    if first:                                            # drive in progress with known odds: replace one drive of the team with the ball by this one
        tid, probs = first
        T, base = (TH, H) if tid == home else (TA, A)
        cls = rng.choice(len(S.CLASSES), size=n, p=probs)
        pts = np.select([cls == 0, cls == 1], [6 + (rng.random(n) < S.XP_RATE), 3], 0.0)
        base["pts"] += pts
    hp, ap = H["pts"] + A["dtd_pts"], A["pts"] + H["dtd_pts"]
    cur = state["teams"][home]["score"] - state["teams"][away]["score"]
    margin = cur + hp - ap
    return {"state": state, "home": home, "away": away, "margin": margin, "H": H, "A": A, "hp": hp, "ap": ap, "n": n, "ball": ball_team}


def report(r: dict, lines: list) -> str:
    st = r["state"]; T = st["teams"]; h, a = T[r["home"]], T[r["away"]]
    m = r["margin"]
    pw = float((m > 0).mean()); ties = float((m == 0).mean())
    out = [f"=== {a['name']} @ {h['name']}  ahora {a['abbr']} {a['score']} - {h['score']} {h['abbr']} | {st['status']} P{st['period']} | restan ~{st['remaining_min']:.0f} min | n={r['n']:,}",
           f"  GANA: {h['name']} {pw*100:.1f}% | {a['name']} {(1-pw-ties)*100:.1f}% | empate reg. {ties*100:.1f}%  margen final medio {h['abbr']} {m.mean():+.1f} (sd {m.std():.1f})"]
    if lines:
        out.append("  COBERTURA (P que " + h["abbr"] + " cubra): " + " | ".join(f"{x:+g}: {S.cover(m, x)*100:.0f}%" for x in lines))
    fh, fa = h["score"] + r["hp"], a["score"] + r["ap"]
    out.append(f"  FINAL medio {a['abbr']} {fa.mean():.1f} - {fh.mean():.1f} {h['abbr']}  (total {np.mean(fa + fh):.1f}; recuerda +5 de sesgo)")
    for tid, X, nm in ((r["home"], r["H"], h), (r["away"], r["A"], a)):
        b = nm["box"]
        py0, ry0 = float(b["netPassingYards"]), float(b["rushingYards"])
        out.append(f"  {nm['abbr']} yds ahora {int(py0 + ry0)} (pase {int(py0)}, carrera {int(ry0)}) -> final proyectado {py0 + ry0 + (X['pass_yds'] + X['rush_yds']).mean():.0f} | 2a parte: pts {X['pts'].mean():.1f}, TD {X['tds'].mean():.2f}, FG {X['fgm'].mean():.2f}")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("event"); ap.add_argument("--n", type=int, default=250_000)
    ap.add_argument("--first"); ap.add_argument("--ball"); ap.add_argument("--line", type=float, nargs="*", default=[])
    a = ap.parse_args()
    first = None
    if a.first:
        tid, pr = a.first.split(":"); v = np.array([float(x) for x in pr.split(",")]); first = (tid, v / v.sum())
    res = simulate_rest(a.event, a.n, first=first, ball=a.ball)
    print(report(res, a.line))

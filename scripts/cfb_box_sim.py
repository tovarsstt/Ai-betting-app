"""CFB drive-by-drive Monte Carlo from OUR data only (ESPN drive logs of the teams' 2026 games, no market prices): every possession draws an outcome
(TD / FG / missed FG / turnover / defensive TD / no score) from the offense's rate crossed with the opponent defense's rate allowed (multiplicative, shrunk
toward the pooled league rate), then resamples a real drive of that outcome for plays and yards and splits it into pass/rush with the team's own mix.
Points, margin, total, win probability and the team box score all come from the same simulated games. Regulation only (a tie is a coin flip + 3).
Known gaps: no schedule-strength adjustment (8 games per team), no QB/injury layer, no 2-pt/safety modelling beyond a flat XP rate.
Usage: python3 scripts/cfb_box_sim.py HOME_ID AWAY_ID [--n 200000] [--spread HOME_SPREAD] [--total T]"""
import sys, json, argparse
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "data" / "cfb_box_cache.json"
CLASSES = ("TD", "FG", "MFG", "TO", "DTD", "NO")
RESULT_CLASS = {"Touchdown": "TD", "Field Goal": "FG", "Missed FG": "MFG", "Interception": "TO", "Fumble": "TO", "Downs": "TO",
                "Interception Touchdown": "DTD", "Fumble Touchdown": "DTD", "Fumble Return Touchdown": "DTD", "Punt Touchdown": "DTD"}
SHRINK_DRIVES = 30           # pseudo-drives of league average mixed into every team rate
XP_RATE = 0.95               # extra point made
TIE_BONUS = 3                # winner's margin when regulation ends level


def drive_class(result) -> str:
    return RESULT_CLASS.get(result, "NO")


def load_games() -> dict:
    return json.loads(CACHE.read_text())


def team_tables(games: dict, tid: str) -> dict:
    """offense rate per class, defense (allowed) rate per class, drive pools by class, yards/drive, tempo and pass/rush mix"""
    off, dfn, pool = defaultdict(int), defaultdict(int), defaultdict(list)
    n_off = n_def = 0
    per_game, box = [], defaultdict(float)
    ng = 0
    for g in games.values():
        if tid not in g["teams"]:
            continue
        ng += 1
        mine = 0
        for d in g["drives"]:
            c = drive_class(d["result"])
            if d["team"] == tid:
                off[c] += 1; n_off += 1; mine += 1
                pool[c].append((d["plays"], d["yards"]))
            else:
                dfn[c] += 1; n_def += 1
        per_game.append(mine)
        b = g["teams"][tid]["box"]
        ca, ct = b["completionAttempts"].split("/")
        box["pass_att"] += int(ct); box["comp"] += int(ca); box["pass_yds"] += float(b["netPassingYards"])
        box["rush_att"] += int(b["rushingAttempts"]); box["rush_yds"] += float(b["rushingYards"])
    pa, ra = box["pass_att"], box["rush_att"]
    return {"games": ng, "n_off": n_off, "n_def": n_def, "off": dict(off), "def": dict(dfn), "pool": {k: np.array(v, dtype=float) for k, v in pool.items()},
            "tempo": float(np.mean(per_game)), "pass_rate": pa / (pa + ra), "ypa": box["pass_yds"] / pa, "comp_pct": box["comp"] / pa, "ypc": box["rush_yds"] / ra}


def league_rates(games: dict) -> dict:
    cnt, n = defaultdict(int), 0
    for g in games.values():
        for d in g["drives"]:
            cnt[drive_class(d["result"])] += 1; n += 1
    return {c: cnt[c] / n for c in CLASSES}


def shrunk(counts: dict, n: int, L: dict) -> dict:
    return {c: (counts.get(c, 0) + SHRINK_DRIVES * L[c]) / (n + SHRINK_DRIVES) for c in CLASSES}


def matchup_probs(off_rate: dict, def_rate: dict, L: dict) -> np.ndarray:
    """offense rate x defense rate / league rate, renormalised"""
    raw = np.array([off_rate[c] * def_rate[c] / L[c] for c in CLASSES])
    return raw / raw.sum()


def sim_offense(rng, N: int, n_drives: np.ndarray, probs: np.ndarray, T: dict, ypd_scale: float) -> dict:
    """n_drives: per-sim possessions. Returns arrays for points scored by this offense (incl. XP), defensive-TD points given up, and the box."""
    out = {k: np.zeros(N) for k in ("pts", "dtd_pts", "plays", "pass_att", "comp", "pass_yds", "rush_att", "rush_yds", "tds", "fgm", "fga", "tov")}
    for slot in range(int(n_drives.max())):
        live = n_drives > slot
        cls = rng.choice(len(CLASSES), size=N, p=probs)
        for ci, c in enumerate(CLASSES):
            m = live & (cls == ci)
            k = int(m.sum())
            if not k:
                continue
            if c == "TD":
                out["pts"][m] += 6 + (rng.random(k) < XP_RATE); out["tds"][m] += 1
            elif c == "FG":
                out["pts"][m] += 3; out["fgm"][m] += 1; out["fga"][m] += 1
            elif c == "MFG":
                out["fga"][m] += 1
            elif c == "TO":
                out["tov"][m] += 1
            elif c == "DTD":
                out["tov"][m] += 1; out["dtd_pts"][m] += 6 + (rng.random(k) < XP_RATE)
            pl = T["pool"].get(c)
            if pl is None or not len(pl):
                pl = np.concatenate(list(T["pool"].values()))
            row = pl[rng.integers(0, len(pl), size=k)]
            plays, yds = row[:, 0], row[:, 1] * ypd_scale
            npass = rng.binomial(plays.astype(int), T["pass_rate"]); nrush = plays - npass
            ep, er = npass * T["ypa"], nrush * T["ypc"]
            tot = np.where(np.abs(ep + er) < 1e-9, 1.0, ep + er)
            py = yds * ep / tot
            out["plays"][m] += plays; out["pass_att"][m] += npass; out["rush_att"][m] += nrush
            out["comp"][m] += rng.binomial(npass, T["comp_pct"])
            out["pass_yds"][m] += py; out["rush_yds"][m] += yds - py
    return out


def simulate(home: str, away: str, n: int = 200_000, seed: int = 11, games: dict | None = None) -> dict:
    games = games or load_games()
    L = league_rates(games)
    TH, TA = team_tables(games, home), team_tables(games, away)
    rng = np.random.default_rng(seed)
    ypd = lambda T, pools=("pool",): float(np.mean(np.concatenate(list(T["pool"].values()))[:, 1]))
    league_ypd = float(np.mean([ypd(TH), ypd(TA)]))
    p_h = matchup_probs(shrunk(TH["off"], TH["n_off"], L), shrunk(TA["def"], TA["n_def"], L), L)
    p_a = matchup_probs(shrunk(TA["off"], TA["n_off"], L), shrunk(TH["def"], TH["n_def"], L), L)
    base = np.clip(np.round(rng.normal((TH["tempo"] + TA["tempo"]) / 2, 1.4, n)), 7, 17).astype(int)
    nh, na = base + rng.integers(0, 2, n), base + rng.integers(0, 2, n)
    H = sim_offense(rng, n, nh, p_h, TH, 1.0)
    A = sim_offense(rng, n, na, p_a, TA, 1.0)
    ph, pa_ = H["pts"] + A["dtd_pts"], A["pts"] + H["dtd_pts"]
    tie = ph == pa_
    margin = ph - pa_
    margin = np.where(tie, np.where(rng.random(n) < 0.5, TIE_BONUS, -TIE_BONUS), margin)
    return {"home": home, "away": away, "H": H, "A": A, "pts_h": ph, "pts_a": pa_, "margin": margin, "total": ph + pa_, "p_h": p_h, "p_a": p_a,
            "tables": {"home": TH, "away": TA}, "league": L, "n": n}


def cover(margin: np.ndarray, line: float) -> float:
    """P(home margin + line > 0), push half"""
    d = margin + line
    return float((d > 0).mean() + 0.5 * (d == 0).mean())


def qtxt(v: np.ndarray, d: int = 0) -> str:
    return f"{np.mean(v):.{d}f} [{np.percentile(v, 10):.{d}f}-{np.percentile(v, 90):.{d}f}]"


def report(r: dict, names: tuple, spread: float | None, total: float | None) -> str:
    hn, an = names
    m, T = r["margin"], r["total"]
    pw = float((m > 0).mean())
    s = [f"=== {an} @ {hn}  (n={r['n']:,} juegos simulados)",
         f"  GANA: {hn} {pw*100:.1f}% | {an} {(1-pw)*100:.1f}%   marcador medio {an} {r['pts_a'].mean():.1f} - {r['pts_h'].mean():.1f} {hn}   margen {hn} {m.mean():+.1f} (sd {m.std():.1f})   total {T.mean():.1f} (sd {T.std():.1f})",
         f"  tempo: {r['tables']['home']['tempo']:.1f} / {r['tables']['away']['tempo']:.1f} posesiones por juego ({hn} / {an}); muestra {r['tables']['home']['games']} y {r['tables']['away']['games']} juegos"]
    if spread is not None:
        ladder = [spread - 3, spread - 1.5, spread, spread + 1.5, spread + 3]
        s.append(f"  HANDICAP (P que {hn} cubra): " + " | ".join(f"{x:+g}: {cover(m, x)*100:.0f}%" for x in ladder))
    if total is not None:
        s.append(f"  TOTAL: over {total - 3:g}: {(T > total - 3).mean()*100:.0f}% | over {total:g}: {(T > total).mean()*100:.0f}% | over {total + 3:g}: {(T > total + 3).mean()*100:.0f}%")
    s.append("  BOX SCORE (media [p10-p90]):")
    for nm, X, pts in ((hn, r["H"], r["pts_h"]), (an, r["A"], r["pts_a"])):
        s.append(f"    {nm}: pts {qtxt(pts)} | jugadas {X['plays'].mean():.0f} | pase {X['comp'].mean():.1f}/{X['pass_att'].mean():.1f} {qtxt(X['pass_yds'])} yds | "
                 f"carrera {X['rush_att'].mean():.1f} acarr {qtxt(X['rush_yds'])} yds | total yds {qtxt(X['pass_yds'] + X['rush_yds'])} | TD ofensivos {X['tds'].mean():.2f} | FG {X['fgm'].mean():.2f}/{X['fga'].mean():.2f} | pérdidas {X['tov'].mean():.2f}")
    return "\n".join(s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("home"); ap.add_argument("away")
    ap.add_argument("--n", type=int, default=200_000)
    ap.add_argument("--spread", type=float); ap.add_argument("--total", type=float)
    a = ap.parse_args()
    g = load_games()
    name = lambda t: next(v["name"] for x in g.values() for k, v in x["teams"].items() if k == t)
    res = simulate(a.home, a.away, a.n, games=g)
    print(report(res, (name(a.home), name(a.away)), a.spread, a.total))

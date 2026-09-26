#!/usr/bin/env python3
"""
game_report.py — full per-game analysis + simulation for an NFL week.

  python3 scripts/game_report.py --nflverse 2026:3 [--sims 2000000] [--out reports/nfl-2026-week3-full]

Every game: consensus line, projected score, margin distribution (incl. key
numbers), moneyline / spread / alt-spread ladders for BOTH teams, alt totals,
QBs, ratings, playstyle, rest/roof, injuries + watchlist, and the Judge's
verdicts (winner-first pick, most likely underdog, total lean, price notes).
Slate section: expected upsets and their distribution.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import nflverse_feed as nf  # noqa: E402
import winner_judge as wj  # noqa: E402

ALT_SPREADS = (-13.5, -10.5, -7.5, -6.5, -3.5, -2.5, -1.5, 1.5, 2.5, 3.5, 6.5, 7.5, 10.5, 13.5)
ALT_TOTAL_OFFSETS = (-7, -3.5, 0, 3.5, 7)


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def analyze(g: dict, n_sims: int, seed: int) -> dict:
    sport, s = "NFL", wj.SIGMA["NFL"]
    r = wj.judge_game(g, n_sims=n_sims, seed=seed)
    mu = r["expected_home_margin"]["blended"]          # home margin (market-anchored)
    tp = r["total_projection"] or {}
    tmean = tp.get("blended", g["total"]["points"])
    pmf = wj.margin_pmf(sport, mu, s)
    rng = np.random.default_rng(seed)
    keys = np.array(sorted(pmf))
    cum = np.cumsum([pmf[k] for k in keys])
    m = keys[np.minimum(np.searchsorted(cum, rng.random(n_sims)), len(keys) - 1)]
    t = np.rint(rng.normal(tmean, wj.TOTAL_SIGMA[sport], n_sims))
    home_pts = (t + m) / 2
    away_pts = (t - m) / 2

    def ladder(side: str) -> list:
        sgn = 1 if side == "home" else -1
        out = [("ML", float(np.mean(sgn * m > 0) + 0.5 * np.mean(m == 0)))]
        for ln in ALT_SPREADS:
            out.append((f"{ln:+g}", float(np.mean(sgn * m + ln > 0))))
        return out

    buckets = [("lose by 8+", m <= -8), ("lose by 4-7", (m <= -4) & (m >= -7)),
               ("lose by 1-3", (m <= -1) & (m >= -3)), ("tie", m == 0),
               ("win by 1-3", (m >= 1) & (m <= 3)), ("win by 4-7", (m >= 4) & (m <= 7)),
               ("win by 8-14", (m >= 8) & (m <= 14)), ("win by 15+", m >= 15)]
    line = g["total"]["points"]
    totals = [(line + o, float(np.mean(t > line + o)), float(np.mean(t < line + o)))
              for o in ALT_TOTAL_OFFSETS]
    return {
        "judge": r, "mu": mu, "tmean": tmean, "sims": n_sims,
        "proj": (float(np.mean(away_pts)), float(np.mean(home_pts))),
        "home_buckets": [(k, float(v.mean())) for k, v in buckets],
        "key3": float(np.mean(np.abs(m) == 3)), "key7": float(np.mean(np.abs(m) == 7)),
        "ladder_home": ladder("home"), "ladder_away": ladder("away"),
        "totals": totals,
    }


def game_md(g: dict, a: dict) -> list[str]:
    ab = {v: k for k, v in nf.TEAM_NAMES.items()}
    h, aw = g["home"], g["away"]
    H, A = ab.get(h, h), ab.get(aw, aw)
    r = a["judge"]
    M = {x["label"]: x for x in r["markets"]}
    ph = M[f"{h} ML"]["win_prob"]
    fav, dog = (H, A) if ph >= 0.5 else (A, H)
    ctx = g.get("context") or {}
    hl = g["spread"]["home_line"]
    L = [f"## {A} @ {H} — {g.get('kickoff', '')}", ""]
    L.append(f"**Line:** {H} {hl:+g} · total {g['total']['points']} · ML {A} {g['moneyline']['away']:+.0f} / "
             f"{H} {g['moneyline']['home']:+.0f}  ")
    L.append(f"**Projected score ({a['sims']:,} sims):** {A} {a['proj'][0]:.1f} – {H} {a['proj'][1]:.1f} "
             f"(expected margin {H} {a['mu']:+.1f}, total {a['tmean']:.1f})  ")
    L.append(f"**Win the game:** {A} {pct(1 - ph)} · {H} {pct(ph)} → favorite **{fav}**, upset chance "
             f"**{pct(min(ph, 1 - ph))}**  ")
    L.append(f"**Key numbers:** decided by exactly 3 = {pct(a['key3'])}, exactly 7 = {pct(a['key7'])}")
    L.append("")
    # context
    q = ctx.get("qb", {})
    L.append(f"- 🏈 **QBs:** {q.get('away')} @ {q.get('home')}"
             + (f" · rest {ctx['rest_days']['away']}d / {ctx['rest_days']['home']}d" if ctx.get("rest_days") else "")
             + (f" · {ctx['roof']}" if ctx.get("roof") else "") + (" · division game" if ctx.get("div_game") else ""))
    for side, T in (("away", A), ("home", H)):
        rt = (ctx.get("ratings") or {}).get(side) or {}
        st = (ctx.get("playstyle") or {}).get(side) or {}
        if rt:
            L.append(f"- 📊 **{T}:** net {rt['net']:+.1f} pts vs avg (off {rt['off']:+.1f}, def {rt['def']:+.1f}; "
                     f"{rt['games_this_season']} games in 2026{', NEW QB since 2025' if rt.get('qb_changed') else ''})"
                     + (f" · EPA/play off {st['off_epa_play']:+.3f}, def allowed {st['def_epa_play']:+.3f} · "
                        f"pass {st['pass_rate']:.0%} · {st['plays_pg']} plays/g" if st else ""))
    for side, T in (("away", A), ("home", H)):
        outs = [c["note"].split(" — ")[0] for c in (g.get("conditions") or {}).get(side, [])]
        if outs:
            L.append(f"- 🏥 **{T} out/doubtful (starters):** {', '.join(outs)}")
        for w in (ctx.get("injury_watch") or {}).get(side, []):
            L.append(f"- 👀 {T}: {w}")
    L.append("")
    # margin distribution from home perspective
    L.append(f"| {H} result | chance |")
    L.append("|---|---|")
    for k, v in a["home_buckets"]:
        L.append(f"| {k} | {pct(v)} |")
    L.append("")
    # ladders
    L.append("| Line | " + " | ".join(x[0] for x in a["ladder_away"]) + " |")
    L.append("|---|" + "---|" * len(a["ladder_away"]))
    for T, lad in ((A, a["ladder_away"]), (H, a["ladder_home"])):
        L.append(f"| **{T}** win % | " + " | ".join(pct(p) for _, p in lad) + " |")
        L.append(f"| {T} fair odds | " + " | ".join(f"{1 / p:.2f}" if p > 0.005 else "—" for _, p in lad) + " |")
    L.append("")
    L.append("| Total | " + " | ".join(f"{ln:g}" for ln, _, _ in a["totals"]) + " |")
    L.append("|---|" + "---|" * len(a["totals"]))
    L.append("| Over | " + " | ".join(pct(o) for _, o, _ in a["totals"]) + " |")
    L.append("| Under | " + " | ".join(pct(u) for _, _, u in a["totals"]) + " |")
    L.append("")
    # verdicts
    best = r.get("best_winning_pick")
    dog_ml = M[f"{h if ph < 0.5 else aw} ML"]
    tot = max((x for x in r["markets"] if x["kind"] == "total"), key=lambda x: x["win_prob"])
    L.append("**Judge verdicts**")
    if best:
        L.append(f"- 🏆 Winner-first pick: **{best['label']}** — {pct(best['win_prob'])} "
                 f"({best['grade']}) @ {best['decimal']:.2f}, fair {best['fair_decimal']}, EV {best['ev_pct']:+.1f}%")
    L.append(f"- 🐶 Underdog: **{dog} ML** wins {pct(dog_ml['win_prob'])} @ {dog_ml['decimal']:.2f} "
             f"(fair {dog_ml['fair_decimal']}, EV {dog_ml['ev_pct']:+.1f}%)")
    L.append(f"- 🔢 Total lean: **{tot['label']}** {pct(tot['win_prob'])} "
             f"({'coin flip' if tot['win_prob'] < 0.53 else 'lean'}) @ {tot['decimal']:.2f}")
    for f in r.get("flags", []):
        if not f.startswith("RATINGS_DISPLAY_ONLY"):
            L.append(f"- ⚠️ {f}")
    L.append("")
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nflverse", required=True, help="SEASON:WEEK")
    ap.add_argument("--sims", type=int, default=wj.N_SIMS)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out")
    x = ap.parse_args()
    season, week = map(int, x.nflverse.split(":"))
    if x.refresh:
        nf.refresh(season)
    t0 = time.time()
    sl = nf.week_slate(season, week, overrides=nf.load_overrides(season))
    games = sorted(sl["games"], key=lambda g: g.get("kickoff", ""))
    res = [(g, analyze(g, x.sims, 1000 + i)) for i, g in enumerate(games)]
    # slate-level upset simulation
    dog_p = np.array([min(a["judge"]["markets"][0]["win_prob"], 1) for _, a in res])
    dog_p = np.array([min(next(m for m in a["judge"]["markets"] if m["label"] == f"{g['home']} ML")["win_prob"],
                          1 - next(m for m in a["judge"]["markets"] if m["label"] == f"{g['home']} ML")["win_prob"])
                      for g, a in res])
    ups = (np.random.default_rng(7).random((x.sims, len(dog_p))) < dog_p).sum(1)
    L = [f"# NFL {season} Week {week} — full game-by-game analysis & simulation", ""]
    L.append(f"{len(games)} games · {x.sims:,} Monte Carlo games each · margin σ {wj.SIGMA['NFL']} and total σ "
             f"{wj.TOTAL_SIGMA['NFL']} fitted to 1,759 real games · lines: {sl['lines_source']} · "
             f"injuries: official report + Friday finals (starters only) · built in {time.time() - t0:.0f}s")
    L.append("")
    L.append("## Slate at a glance")
    L.append("")
    L.append("| Game | Fav | Fav wins | Upset | Spread fav/dog | Proj. score | Total O/U |")
    L.append("|---|---|---|---|---|---|---|")
    ab = {v: k for k, v in nf.TEAM_NAMES.items()}
    for g, a in res:
        M = {m["label"]: m for m in a["judge"]["markets"]}
        h, aw = g["home"], g["away"]
        ph = M[f"{h} ML"]["win_prob"]
        hl = g["spread"]["home_line"]
        fav, dog = (h, aw) if hl < 0 or (hl == 0 and ph >= .5) else (aw, h)
        fl = -abs(hl)
        sp_f = M.get(f"{fav} {fl:+g}", {}).get("win_prob")
        sp_d = M.get(f"{dog} {-fl:+g}", {}).get("win_prob")
        t = g["total"]["points"]
        L.append(f"| {ab[aw]} @ {ab[h]} | {ab[fav]} {fl:+g} | {pct(max(ph, 1 - ph))} | {pct(min(ph, 1 - ph))} | "
                 f"{pct(sp_f)} / {pct(sp_d)} | {ab[aw]} {a['proj'][0]:.0f}–{a['proj'][1]:.0f} {ab[h]} | "
                 f"{t}: {pct(M[f'Over {t}']['win_prob'])} / {pct(M[f'Under {t}']['win_prob'])} |")
    L.append("")
    L.append(f"**Upsets across the slate ({x.sims:,} simulated Sundays):** expected {ups.mean():.1f} of {len(games)} · "
             + " · ".join(f"≥{k}: {pct(float((ups >= k).mean()))}" for k in (3, 5, 7))
             + f" · all favorites win: {pct(float((ups == 0).mean()))}")
    L.append("")
    for g, a in res:
        L += game_md(g, a)
    L.append("---")
    L.append("Win % = market-anchored (backtest: market beats team ratings; devigged ML calibration Brier 0.21). "
             "Ratings, playstyle and injuries are context the lines already price. Pushes count as not-a-win.")
    md = "\n".join(L)
    print(md)
    if x.out:
        Path(f"{x.out}.md").write_text(md + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

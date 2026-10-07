#!/usr/bin/env python3
"""
forward_tests.py — the honest way to settle a "watch" hypothesis: freeze it, then count games the study never saw.

Backtests that mine subsets after the fact cannot validate themselves (the NFL backup-QB audit: heavy-favourite cut p=0.14 raw,
p=1.00 after Bonferroni; effect 2012-19 -2.4 pts vs 2020-25 -0.9 pts, trend p=0.27). So every watch rule below is REGISTERED with its exact
definition on FROZEN_ON; only games played on/after FREEZE_FROM are scored (none of them was used to find or tune a rule), at the PRICE
actually posted. A rule is promoted only if, with n >= N_MIN, its one-sided p vs break-even is < ALPHA/len(rules) (Bonferroni); it is
rejected when n >= N_MIN and the 90% interval sits below break-even. Everything in between stays WATCH and gets stake 0.

    python3 scripts/forward_tests.py          # fetch new final NFL games, update data/forward_ledger.json, print the scoreboard
"""
from __future__ import annotations

import datetime
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import fetch_espn_boxscores as fb  # noqa: E402

KG = Path("/tmp/kg")
DATA = Path(__file__).parent.parent / "data"
LEDGER = DATA / "forward_ledger.json"
FROZEN_ON, FREEZE_FROM = "2026-10-07", "2026-09-01"
N_MIN, ALPHA = 150, 0.05
OPENMETEO_EQ_15 = 13.2          # Open-Meteo mph with the same exceedance share (10.7%) as recorded 15 mph (data/wind_scale_map.json)
RULES = {
    "nfl_fade_backup_qb": "NFL, v2 definition (same-season): exactly one team starts a QB who is NOT the modal starter of its earlier games IN THE SAME SEASON (needs >=3) -> bet the OTHER team ATS at the posted spread. "
                          "v2 replaced v1 on 2026-10-07 because v1 flagged every new franchise QB in weeks 1-3 as a 'backup'; counted from 2026-10-08 so the sample that motivated the fix is excluded",
    "nfl_fade_backup_qb_heavy_fav": "same, |spread| >= 7 (kept only to confirm the subset story is noise: pooled v2 shows 56.9% for |line|>=7 vs 57.6% for <7)",
    "nfl_under_wind15": "NFL outdoor game, kickoff-hour Open-Meteo wind >= 13.2 mph (= recorded >= 15 mph: both are the top 10.7% of games; raw Open-Meteo and the recorded feed are NOT on the same scale, corr 0.72) -> bet the UNDER at the posted total",
}
RULE_FROM = {"nfl_fade_backup_qb": "2026-10-08", "nfl_fade_backup_qb_heavy_fav": "2026-10-08", "nfl_under_wind15": "2026-09-01"}
dec = lambda a: None if a is None else (1 + a / 100.0 if a > 0 else 1 + 100.0 / -a)


def j(u):
    return json.load(urllib.request.urlopen(u, timeout=40))


def new_events(start: str) -> list:
    d0, d1 = datetime.date.fromisoformat(start), datetime.date.today()
    out = []
    d = d0
    while d <= d1:
        sb = j(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d.strftime('%Y%m%d')}&limit=50")
        for e in sb.get("events", []):
            c = e["competitions"][0]
            if (e.get("season") or {}).get("type") == 2 and c["status"]["type"]["name"] == "STATUS_FINAL":
                tm = {x["homeAway"]: x for x in c["competitors"]}
                out.append({"id": int(e["id"]), "utc": e["date"], "hn": tm["home"]["team"]["displayName"], "an": tm["away"]["team"]["displayName"],
                            "hp": int(tm["home"]["score"]), "ap": int(tm["away"]["score"])})
        d += datetime.timedelta(1)
    return out


def starter(box_team: dict):
    best = None
    for p in box_team["players"]:
        if p.get("group") != "passing":
            continue
        try:
            att = float(str(p["stats"].get("completions/passingAttempts", "0/0")).split("/")[1])
        except Exception:
            continue
        if best is None or att > best[1]:
            best = (p["id"], att)
    return best[0] if best and best[1] >= 8 else None


def season_key(utc: str) -> int:
    t = datetime.datetime.fromisoformat(utc.replace("Z", "+00:00"))
    return t.year - (1 if t.month < 3 else 0)


def hist_starters() -> dict:
    """team -> chronological list of (season, starting-QB id) (2012-2025 from the study files)."""
    ev = {json.loads(l)["id"]: json.loads(l) for l in (KG / "espn_nfl_events.jsonl").open()}
    rows = []
    for l in (KG / "espn_nfl_box.jsonl").open():
        d = json.loads(l)
        for tm in d["teams"]:
            q = starter(tm)
            if q and d["id"] in ev:
                rows.append((ev[d["id"]]["utc"], tm["team"], q))
    rows.sort()
    h = {}
    for utc, team, q in rows:
        h.setdefault(team, []).append((season_key(utc), q))
    return h


def backup_flag(history: list, q: str, sk: int) -> bool:
    win = [x for (s_, x) in history if s_ == sk]               # earlier games of the SAME season only
    if len(win) < 3:
        return False
    return q != max(set(win), key=win.count)


def wind_mph(city: str, utc: str) -> float | None:
    try:
        g = j("https://geocoding-api.open-meteo.com/v1/search?name=%s&count=3&country_code=US" % urllib.request.quote(city))["results"][0]
        t = datetime.datetime.fromisoformat(utc.replace("Z", "+00:00"))
        day = t.strftime("%Y-%m-%d")
        w = j(f"https://archive-api.open-meteo.com/v1/archive?latitude={g['latitude']}&longitude={g['longitude']}&start_date={day}&end_date={day}&hourly=wind_speed_10m&wind_speed_unit=mph&timezone=UTC")
        hrs = w["hourly"]["time"]
        i = [k for k, x in enumerate(hrs) if x[:13] == t.strftime("%Y-%m-%dT%H")]
        return w["hourly"]["wind_speed_10m"][i[0]] if i else None
    except Exception:
        return None


def indoor_home_teams() -> set:
    """ESPN gives no reliable roof flag, so derive it: home teams whose games were indoor/closed-roof in >=70% of 2018+ games (spreadspoke weather_detail/stadium)."""
    import pandas as pd
    d = pd.read_csv(KG / "nfl_spreadspoke/spreadspoke_scores.csv")
    d = d[d.schedule_season >= 2018]
    ind = d.weather_detail.fillna("").str.contains("indoor|retractable \\(closed", case=False) | d.stadium.fillna("").str.contains("dome", case=False)
    share = ind.groupby(d.team_home).mean()
    return set(share[share >= 0.7].index)


def update() -> dict:
    led = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"frozen_on": FROZEN_ON, "freeze_from": FREEZE_FROM, "rules": RULES, "games": {}}
    led["rules"], led["rule_from"] = RULES, RULE_FROM
    seen = set(led["games"])
    ev = [e for e in new_events(FREEZE_FROM) if str(e["id"]) not in seen]
    hist = hist_starters()
    domes = indoor_home_teams()
    # replay already-ledgered 2026 games into the history so flags stay past-only and ordered
    for gid, g in sorted(led["games"].items(), key=lambda kv: kv[1]["utc"]):
        for team, q in g["starters"].items():
            if q:
                hist.setdefault(team, []).append((season_key(g["utc"]), q))
    for e in sorted(ev, key=lambda x: x["utc"]):
        box = fb.fetch("nfl", e["id"])
        if not box or len(box["teams"]) < 2:
            continue
        st = {t["team"]: starter(t) for t in box["teams"]}
        sk = season_key(e["utc"])
        flags = {t: (backup_flag(hist.get(t, []), q, sk) if q else False) for t, q in st.items()}
        pk, vn = box.get("pick") or {}, box.get("venue") or {}
        spread, ou = pk.get("spread"), pk.get("ou")
        rec = {"utc": e["utc"], "home": e["hn"], "away": e["an"], "hp": e["hp"], "ap": e["ap"], "starters": st, "backup": flags, "spread": spread, "ou": ou,
               "home_odds": dec(pk.get("home_spread_odds")), "away_odds": dec(pk.get("away_spread_odds")), "under_odds": dec(pk.get("under_odds")), "indoor": bool(vn.get("indoor")) or e["hn"] in domes, "city": vn.get("city")}
        res = {}
        if spread is not None:
            r = (e["hp"] - e["ap"]) + spread                       # >0 home covers
            hb, ab = flags.get(e["hn"], False), flags.get(e["an"], False)
            if hb != ab and r != 0:
                bet_home = ab                                       # bet the team whose opponent has the backup
                win = (r > 0) == bet_home
                od = rec["home_odds"] if bet_home else rec["away_odds"]
                res["nfl_fade_backup_qb"] = {"win": bool(win), "odds": od or 1.9091}
                if abs(spread) >= 7:
                    res["nfl_fade_backup_qb_heavy_fav"] = {"win": bool(win), "odds": od or 1.9091}
        if ou is not None and not rec["indoor"] and vn.get("city"):
            w = wind_mph(vn["city"], e["utc"])
            rec["wind_mph"] = w
            tot = e["hp"] + e["ap"]
            if w is not None and w >= OPENMETEO_EQ_15 and tot != ou:
                res["nfl_under_wind15"] = {"win": bool(tot < ou), "odds": rec["under_odds"] or 1.9091}
        rec["results"] = res
        led["games"][str(e["id"])] = rec
        for team, q in st.items():
            if q:
                hist.setdefault(team, []).append((sk, q))
    LEDGER.write_text(json.dumps(led, indent=1))
    return led


def scoreboard(led: dict) -> str:
    lines = [f"FORWARD LEDGER — frozen {led['frozen_on']}, scoring games from {led['freeze_from']}  |  {len(led['games'])} NFL games ingested", ""]
    k = len(led["rules"])
    for rule, desc in led["rules"].items():
        res = [g["results"][rule] for g in led["games"].values() if rule in g["results"] and g["utc"][:10] >= RULE_FROM[rule]]
        n = len(res)
        if n == 0:
            lines.append(f"{rule}: n=0 since {RULE_FROM[rule]} (no qualifying game yet) -> WATCH, stake 0")
            continue
        w = sum(r["win"] for r in res)
        roi = float(np.mean([(r["odds"] - 1) if r["win"] else -1 for r in res]) * 100)
        be = float(np.mean([1 / r["odds"] for r in res]))
        p = stats.binomtest(w, n, be, alternative="greater").pvalue
        lo, hi = stats.beta.ppf([0.05, 0.95], 1 + w, 1 + n - w)
        status = "WATCH"
        if n >= N_MIN and p < ALPHA / k:
            status = "VALIDATED"
        elif n >= N_MIN and hi < be:
            status = "REJECTED"
        lines.append(f"{rule}: n={n} wins={w} ({w / n:.1%}) break-even {be:.1%} ROI {roi:+.1f}% one-sided p={p:.3f} (Bonferroni threshold {ALPHA / k:.4f}) 90% CI {lo:.0%}-{hi:.0%} -> {status}"
                     + ("" if n >= N_MIN else f"  [need n>={N_MIN}]"))
    return "\n".join(lines)


if __name__ == "__main__":
    led = update()
    print(scoreboard(led))

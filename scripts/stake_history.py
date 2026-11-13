#!/usr/bin/env python3
"""stake_history.py — parse the Stake settled-bets dump (scripts/stake_history_extract.js style crawl, saved as JSON [{page, txt}]) into one row per bet,
and answer 'why do we lose on day X' with numbers instead of vibes.

  python3 scripts/stake_history.py parse DUMP.json            -> data/stake_history/bets.csv (one row per bet, legs kept)
  python3 scripts/stake_history.py weekday [--day Thu]        -> ROI by weekday + permutation test + mix decomposition for the chosen day

Weekday = date of the LAST leg (when the ticket is decided). ROI = (returned - staked) / staked. Cash-outs count at their payout.
"""
from __future__ import annotations
import json, re, sys, argparse
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "stake_history" / "bets.csv"
MON = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12}
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NFL = "Cardinals|Falcons|Ravens|Bills|Panthers|Bears|Bengals|Browns|Cowboys|Broncos|Lions|Packers|Texans|Colts|Jaguars|Chiefs|Raiders|Chargers|Rams|Dolphins|Vikings|Patriots|Saints|Giants|Jets|Eagles|Steelers|49ers|Seahawks|Buccaneers|Titans|Commanders"
NBA = "Hawks|Celtics|Nets|Hornets|Bulls|Cavaliers|Mavericks|Nuggets|Pistons|Warriors|Rockets|Pacers|Clippers|Lakers|Grizzlies|Heat|Bucks|Timberwolves|Pelicans|Knicks|Thunder|Magic|76ers|Suns|Trail Blazers|Kings|Spurs|Raptors|Jazz|Wizards"
WNBA = "Aces|Dream|Sky|Sun|Wings|Fever|Sparks|Lynx|Liberty|Mercury|Storm|Mystics|Valkyries|Tempo|Fire"
MLB = "Yankees|Red Sox|Dodgers|Mets|Cubs|Astros|Braves|Phillies|Padres|Mariners|Orioles|Guardians|Twins|Brewers|Diamondbacks|Royals|Tigers|Rangers|Blue Jays|Rays|Reds|Pirates|Marlins|Nationals|Athletics|White Sox|Angels|Rockies|Cardinals"
NCAAF_HINT = "State|University|Tech|College|Wolverines|Buckeyes|Crimson Tide|Bulldogs|Tigers|Longhorns|Aggies|Hurricanes|Gators|Seminoles|Trojans|Ducks|Huskies|Sooners|Wildcats|Badgers|Spartans|Hawkeyes|Volunteers|Gamecocks|Razorbacks|Cornhuskers"


def _num(s):
    s = str(s)
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)   # Stake: 15.205,79 = 15205.79


def parse_bet(t: str, year_hint=2026) -> dict | None:
    m = re.search(r"Cuotas \| ([0-9.,]+) \| Apuesta \| ([0-9.]+) \| Pago \| ([0-9.]+)", t)
    if not m: return None
    odds, stake, pay = _num(m.group(1)), float(m.group(2)), float(m.group(3))
    st = re.search(r"\| (Ganador|Perdida|Retirado|Anulad[ao]|Reembolsad[ao]|Empate) \|", t)
    status = st.group(1) if st else ("Ganador" if pay > 0 else "Perdida")
    sgm = re.match(r"\s*Multi apuesta del mismo partido \((\d+)", t); multi = re.match(r"\s*(\d+) Multi tramo", t)
    btype, legs = ("sgm", int(sgm.group(1))) if sgm else ("multi", int(multi.group(1))) if multi else ("single", 1)
    ds = []
    for d_, mon in re.findall(r"(?:lun|mar|mié|jue|vie|sáb|dom)\.?,? (\d{1,2}) (ene|feb|mar|abr|may|jun|jul|ago|sept|sep|oct|nov|dic)\b", t, flags=re.I):
        try: ds.append(date(year_hint, MON[mon.lower()], int(d_)))
        except ValueError: pass
    times = re.findall(r"\b(\d{1,2}):(\d{2})\b", t)
    last = max(ds) if ds else None
    sport = ("NFL" if re.search(rf"\b({NFL})\b", t) else "NBA" if re.search(rf"\b({NBA})\b", t) else
             "tennis" if re.search(r"\b[A-ZÁÉÍÓÚ][a-záéíóúñ'\-]+(?: [A-Z][a-z'\-]+)?, [A-Z][a-z]+", t) and re.search(r"Set|Juegos|Ganador", t) else
             "MLB" if re.search(rf"\b({MLB})\b", t) else "WNBA" if re.search(rf"\b({WNBA})\b", t) and "Ganador" in t else
             "soccer" if re.search(r"Empate|Ambos equipos|1X2|Resultado|Doble oportunidad|Córners|\bFC\b|\bCF\b|United|City|Real |Atlético|Inter|Milan|Madrid|Barcelona|Bayern|PSG|Juventus", t) else "other")
    sports = sorted({s for s, pat in (("NFL", NFL), ("NBA", NBA)) if re.search(rf"\b({pat})\b", t)})
    if len(sports) > 1: sport = "mixed"
    over = len(re.findall(r"\bSobre\b|más de", t)); under = len(re.findall(r"\bDebajo\b|menos de", t))
    hcp = len(re.findall(r"Hándicap", t)); ml = len(re.findall(r"Ganador \(incl", t)); props = len(re.findall(r"Yardas|Puntos|Rebotes|Asistencias|Recepciones|Touchdown|Tiros|Pases", t))
    return {"type": btype, "legs": legs, "odds": odds, "stake": stake, "payout": pay, "status": status, "date": last.isoformat() if last else None,
            "dow": DOW[last.weekday()] if last else None, "first_leg_date": min(ds).isoformat() if ds else None, "n_dates": len(set(ds)),
            "late_hour": int(any(int(h) >= 19 for h, _ in times)), "sport": sport, "over_legs": over, "under_legs": under, "hcp_legs": hcp, "ml_legs": ml, "prop_legs": props, "txt": t[:1500]}


def parse(dump: Path) -> pd.DataFrame:
    raw = json.loads(dump.read_text())
    rows, seen = [], set()
    for b in raw:
        t = b["txt"] if isinstance(b, dict) else b
        r = parse_bet(t)
        if not r: continue
        k = r["txt"][:400]
        if k in seen: continue
        seen.add(k); rows.append(r)
    df = pd.DataFrame(rows)
    # Stake lists newest first; rows without a parsable date inherit the neighbour's date (same page, same day order)
    df["date"] = df["date"].ffill().bfill(); df["dow"] = pd.to_datetime(df["date"]).dt.dayofweek.map(lambda i: DOW[i])
    OUT.parent.mkdir(parents=True, exist_ok=True); df.to_csv(OUT, index=False)
    return df


def roi(d): s = d.stake.sum(); return (d.payout.sum() - s) / s if s else float("nan")


def weekday_report(df: pd.DataFrame, day="Thu", n_perm=20000, seed=7):
    rng = np.random.default_rng(seed); df = df.copy(); df["net"] = df.payout - df.stake
    out = {"n": len(df), "range": [df.date.min(), df.date.max()], "overall_roi": roi(df)}
    tab = df.groupby("dow").apply(lambda d: pd.Series({"bets": len(d), "staked": d.stake.sum(), "net": d.net.sum(), "roi": roi(d), "hit": (d.payout > 0).mean(),
                                                       "avg_odds": d.odds.median(), "avg_legs": d.legs.mean(), "sgm_share": (d.type == "sgm").mean()})).reindex(DOW)
    out["by_dow"] = tab
    # permutation test: is the chosen day's ROI lower than random relabelling of the same bets would give?
    is_day = (df.dow == day).values; net, stake = df.net.values, df.stake.values
    obs = net[is_day].sum() / stake[is_day].sum(); k = is_day.sum(); sims = np.empty(n_perm)
    for i in range(n_perm):
        idx = rng.choice(len(df), size=k, replace=False); sims[i] = net[idx].sum() / stake[idx].sum()
    out["perm"] = {"obs_roi": obs, "p_value_lower": float((sims <= obs).mean()), "null_mean": float(sims.mean()), "null_p5": float(np.percentile(sims, 5))}
    # bootstrap CI for the day's ROI
    dd = df[is_day]; bs = [ (lambda s: s.net.sum() / s.stake.sum())(dd.sample(len(dd), replace=True, random_state=int(rng.integers(1e9)))) for _ in range(4000)]
    out["boot_ci"] = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
    # mix decomposition: expected ROI of the day's bets if each earned its cell's ROI on OTHER days
    def cell(d): return d.type + "|" + pd.cut(d.legs, [0, 1, 3, 5, 99], labels=["1", "2-3", "4-5", "6+"]).astype(str) + "|" + pd.cut(d.odds, [0, 1.5, 2, 3, 5, 10, 25, 1e9], labels=["<1.5", "1.5-2", "2-3", "3-5", "5-10", "10-25", "25+"]).astype(str)
    df["cell"] = cell(df); other = df[~is_day]; cr = other.groupby("cell").apply(lambda d: (d.net.sum(), d.stake.sum()))
    exp_net = 0.0
    for _, r in df[is_day].iterrows():
        n_, s_ = cr.get(r.cell, (0.0, 0.0)); exp_net += r.stake * (n_ / s_ if s_ > 0 else roi(other))
    out["mix"] = {"expected_roi_given_mix": exp_net / df[is_day].stake.sum(), "actual_roi": obs, "other_days_roi": roi(other)}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse"); p.add_argument("dump")
    w = sub.add_parser("weekday"); w.add_argument("--day", default="Thu"); w.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "parse":
        df = parse(Path(a.dump)); print("parsed", len(df), "bets", df.date.min(), "->", df.date.max(), "| saved", OUT); print(df.groupby(["type"]).size())
    else:
        df = pd.read_csv(OUT); r = weekday_report(df, a.day, n_perm=4000 if a.json else 20000)
        if a.json:
            df["net"] = df.payout - df.stake
            sp = df[df.dow == a.day].groupby("sport").apply(lambda d: {"n": int(len(d)), "roi": float(roi(d))}, include_groups=False).to_dict()
            print(json.dumps({"n": r["n"], "range": r["range"], "overall_roi": r["overall_roi"], "day": a.day,
                              "by_dow": [{"dow": k, **{c: (None if pd.isna(v) else float(v)) for c, v in row.items()}} for k, row in r["by_dow"].iterrows()],
                              "perm": {k: float(v) for k, v in r["perm"].items()}, "boot_ci": r["boot_ci"], "mix": {k: float(v) for k, v in r["mix"].items()}, "day_by_sport": sp}))
            sys.exit(0)
        print(f"bets {r['n']} {r['range']} overall ROI {r['overall_roi']*100:+.1f}%"); print(r["by_dow"].round(3).to_string())
        print("permutation:", {k: round(v, 4) for k, v in r["perm"].items()}, "| bootstrap 95% CI", [round(x, 3) for x in r["boot_ci"]]); print("mix:", {k: round(v, 4) for k, v in r["mix"].items()})

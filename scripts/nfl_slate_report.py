"""Print the slate report: sim score, win prob, modal score, market (ESPN/DraftKings) lines, cover/over probs, key player ranges.
Usage: python3 scripts/nfl_slate_report.py [--dir SLATE_DIR] [--game AWAY@HOME] [--players]"""
import sys, json, pickle, argparse
from collections import Counter
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_sim_service as ns

W_SIM = 0.3        # walk-forward 2026 (106 games): logloss sim .674, market .662, 50/50 .660, best 30/70 in logit space .659
DEF_DIR = "/private/tmp/claude-501/-Users-josetovar-Documents-APP-AI-BETS/d2188ef8-37ad-4cf1-b93d-e4a6e86121e4/scratchpad/slate"


def dk_lines(event_id: str) -> dict:
    d = ns._fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}")
    pc = (d.get("pickcenter") or [{}])[0]
    return {"spread": pc.get("spread"), "total": pc.get("overUnder"), "details": pc.get("details"),
            "home_ml": (pc.get("homeTeamOdds") or {}).get("moneyLine"), "away_ml": (pc.get("awayTeamOdds") or {}).get("moneyLine")}


def devig_ml(h, a):
    imp = lambda o: 100 / (o + 100) if o > 0 else -o / (-o + 100)
    ph, pa = imp(h), imp(a)
    return ph / (ph + pa)


def game_block(key, r, P, meta, line, show_players):
    away, home = key.split("@")
    H, A, M, T = P["H"], P["A"], P["M"], P["T"]
    pw = float((M > 0).mean() + 0.5 * (M == 0).mean())
    lgt = lambda p: float(np.log(p / (1 - p)))
    modal = Counter(zip(H.astype(int), A.astype(int))).most_common(1)[0]
    # score nearest the mean that is also a common winning scoreline of the favourite
    fav, p_fav = (home, pw) if pw >= 0.5 else (away, 1 - pw)
    s = f"{away} @ {home}  QB {r['qb_away']} / {r['qb_home']}\n"
    s += f"  SIM  {away} {A.mean():.1f} - {H.mean():.1f} {home}   total {T.mean():.1f}   margin(home) {M.mean():+.1f} sd {M.std():.1f}\n"
    s += f"  P(win) {home} {pw*100:.1f}%  {away} {(1-pw)*100:.1f}%   score mas repetido {away} {modal[0][1]}-{modal[0][0]} {home} ({modal[1]/len(H)*100:.1f}%)\n"
    if line and line.get("spread") is not None:
        sp, tot = line["spread"], line["total"]
        cover = float((M + sp > 0).mean()); over = float((T > tot).mean())
        mkt = devig_ml(line["home_ml"], line["away_ml"]) if line.get("home_ml") and line.get("away_ml") else None
        s += f"  DK   {line['details']} total {tot}  ML {home} {line['home_ml']} / {away} {line['away_ml']}  (mercado sin vig {home} {mkt*100:.1f}%)\n" if mkt else ""
        if mkt:
            pb = 1 / (1 + np.exp(-(W_SIM * lgt(pw) + (1 - W_SIM) * lgt(mkt))))
            s += f"  MI PROB (30% sim + 70% mercado, logit): {home} {pb*100:.1f}%  {away} {(1-pb)*100:.1f}%\n"
        s += f"  vs DK: P({home} cubre {sp:+g}) {cover*100:.1f}%   P(Over {tot}) {over*100:.1f}%\n"
    s += f"  baja: {home} {meta[home]['out']} | {away} {meta[away]['out']}  dudosos(Q): {meta[home]['questionable']} {meta[away]['questionable']}\n"
    if show_players:
        for tm in (home, away):
            rows = []
            for k, v in P.items():
                if not k.startswith(tm + "|") or k.endswith(("Others rec", "Others recY")):
                    continue
                nm = k.split("|", 1)[1]
                if nm.endswith((" passY", " recY", " rushY")) and v.mean() > 18:
                    rows.append((nm, float(v.mean()), float(np.median(v)), float(np.percentile(v, 10)), float(np.percentile(v, 90))))
            rows.sort(key=lambda x: -x[1])
            s += f"  {tm} props (yardas: media / mediana [p10-p90]):\n"
            for nm, mu, md, lo, hi in rows[:9]:
                s += f"     {nm:28s} {mu:6.1f} / {md:6.1f} [{lo:5.1f}-{hi:5.1f}]\n"
            atd = [(k.split('|', 1)[1][:-4], float(v.mean())) for k, v in P.items() if k.startswith(tm + "|") and k.endswith(" ATD")]
            atd.sort(key=lambda x: -x[1])
            s += "     TD cualquier momento: " + ", ".join(f"{n} {p*100:.0f}%" for n, p in atd[:5]) + "\n"
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEF_DIR)
    ap.add_argument("--game", default="")
    ap.add_argument("--players", action="store_true")
    a = ap.parse_args()
    sd = Path(a.dir)
    summary = {f"{r['away']}@{r['home']}": r for r in json.loads((sd / "slate_summary.json").read_text())}
    allp = pickle.load(open(sd / "slate_props.pkl", "rb"))
    fx = lambda t: ns._ABBR_ALIASES.get(t, t)
    sb = {f"{fx(e['competitions'][0]['competitors'][1]['team']['abbreviation'])}@{fx(e['competitions'][0]['competitors'][0]['team']['abbreviation'])}": e["id"]
          for e in ns._fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20261101")["events"]}
    for key, g in allp.items():
        if a.game and key != a.game:
            continue
        line = dk_lines(sb[key]) if key in sb else None
        print(game_block(key, summary[key], g["P"], g["meta"], line, a.players))

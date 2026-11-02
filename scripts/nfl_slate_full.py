"""Full RAW-sim report per game (no market tilt): win %, score, handicap ladder, total ladder, team box score, player props.
Everything comes from the same simulated games, so box score, props and handicap are mutually consistent.
Usage: python3 scripts/nfl_slate_full.py [--dir SLATE_DIR] [--game AWAY@HOME]"""
import sys, json, pickle, argparse
from collections import Counter
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_sim_service as ns
from nfl_slate_report import dk_lines, devig_ml, DEF_DIR

KEYS = ["att", "comp", "pyds", "rush", "ryds", "sacks", "ints", "td", "ptd", "fgm", "fga", "fum"]


def cover(M, line):
    """P(home covers handicap `line`) i.e. home margin + line > 0, push counted half"""
    d = M + line
    return float((d > 0).mean() + 0.5 * (d == 0).mean())


def rng_txt(v):
    return f"{np.mean(v):.0f} / {np.median(v):.0f} [{np.percentile(v, 10):.0f}-{np.percentile(v, 90):.0f}]"


def block(key, r, g, line):
    away, home = key.split("@")
    P = g["P"]; M, T, H, A = P["M"], P["T"], P["H"], P["A"]
    pw = float((M > 0).mean() + 0.5 * (M == 0).mean())
    top = Counter(zip(A.astype(int), H.astype(int))).most_common(3)
    s = [f"=== {away} @ {home}   QB {r['qb_away']} / {r['qb_home']}   (n={len(M)})"]
    s.append(f"  SIM PURA  {away} {A.mean():.1f} - {H.mean():.1f} {home}  | P(gana) {home} {pw*100:.1f}%  {away} {(1-pw)*100:.1f}% | margen medio {home} {M.mean():+.1f} (sd {M.std():.1f}) | total {T.mean():.1f}")
    s.append("  marcadores mas comunes: " + ", ".join(f"{away} {a}-{h} {home} ({n/len(M)*100:.1f}%)" for (a, h), n in top) +
             f" | gana por 10+: {home} {(M>=10).mean()*100:.0f}% / {away} {(M<=-10).mean()*100:.0f}%")
    if line and line.get("spread") is not None:
        sp, tot = line["spread"], line["total"]
        mk = devig_ml(line["home_ml"], line["away_ml"]) if line.get("home_ml") and line.get("away_ml") else None
        s.append(f"  MERCADO DK {line['details']} total {tot}" + (f" | prob sin vig {home} {mk*100:.0f}%" if mk else "") + "   (referencia, no entra en mi sim pura)")
        ladder = [sp - 3, sp - 1.5, sp, sp + 1.5, sp + 3]
        s.append("  HANDICAP (P que " + home + " cubra): " + " | ".join(f"{x:+g}: {cover(M, x)*100:.0f}%" for x in ladder) +
                 f"   Over {tot}: {(T > tot).mean()*100:.0f}% (sim total {T.mean():.1f}, corre ~+5 sobre DK)")
    s.append(f"  inactivos oficiales publicados: {r['inactives_posted']}")
    for si, tm in enumerate((home, away)):
        base = 3 + (0 if tm == home else 1) * len(KEYS)
        X = g["X"]
        c = lambda k: X[:, base + KEYS.index(k)]
        s.append(f"  BOX {tm}: pts {rng_txt(X[:, 0 if tm == home else 1])} | pase {c('comp').mean():.1f}/{c('att').mean():.1f} {c('pyds').mean():.0f} yds, {c('ptd').mean():.1f} TD, {c('ints').mean():.1f} INT, {c('sacks').mean():.1f} sacks recibidos | "
                 f"carrera {c('rush').mean():.1f} acarr {c('ryds').mean():.0f} yds | TD tot {c('td').mean():.1f} | FG {c('fgm').mean():.1f}/{c('fga').mean():.1f} | fumbles {c('fum').mean():.1f}")
        pr = {k.split("|", 1)[1]: v for k, v in P.items() if k.startswith(tm + "|")}
        qb = [(k, v) for k, v in pr.items() if k.endswith(" passY")]
        for k, v in qb:
            nm = k[:-6]
            s.append(f"     {nm} pase yds {rng_txt(v)} | comp {rng_txt(pr[nm + ' comp'])} | TD pase {pr[nm + ' passTD'].mean():.2f} | INT {pr[nm + ' INT'].mean():.2f}")
        recs = sorted([(k[:-5], v) for k, v in pr.items() if k.endswith(" recY") and "Others" not in k], key=lambda kv: -kv[1].mean())[:4]
        for nm, v in recs:
            s.append(f"     {nm} rec yds {rng_txt(v)} | recepciones {rng_txt(pr[nm + ' rec'])}")
        rush = sorted([(k[:-6], v) for k, v in pr.items() if k.endswith(" rushY") and "Others" not in k], key=lambda kv: -kv[1].mean())[:3]
        for nm, v in rush:
            s.append(f"     {nm} rush yds {rng_txt(v)} | acarreos {rng_txt(pr[nm + ' car'])}")
        atd = sorted([(k[:-4], v.mean()) for k, v in pr.items() if k.endswith(" ATD")], key=lambda kv: -kv[1])[:5]
        s.append("     TD cualquier momento: " + ", ".join(f"{n} {p*100:.0f}%" for n, p in atd))
    return "\n".join(s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEF_DIR)
    ap.add_argument("--game", default="")
    ap.add_argument("--date", default="20261101")
    a = ap.parse_args()
    sd = Path(a.dir)
    summary = {f"{r['away']}@{r['home']}": r for r in json.loads((sd / "slate_summary.json").read_text())}
    allp = pickle.load(open(sd / "slate_props.pkl", "rb"))
    fx = lambda t: ns._ABBR_ALIASES.get(t, t)
    sb = {f"{fx(e['competitions'][0]['competitors'][1]['team']['abbreviation'])}@{fx(e['competitions'][0]['competitors'][0]['team']['abbreviation'])}": e["id"]
          for e in ns._fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=" + a.date)["events"]}
    for key, g in allp.items():
        if a.game and key != a.game:
            continue
        g["X"] = np.load(sd / f"{key}.npy").astype(np.float64)
        print(block(key, summary[key], g, dk_lines(sb[key])), "\n")

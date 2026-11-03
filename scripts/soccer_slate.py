"""Soccer slate from OUR model only (no market prices): fitted Poisson ratings -> lambdas -> Dixon-Coles score matrix -> every market, plus timeline
simulation for the 1UP/2UP markets (a team leads by N at ANY moment). Usage: python3 scripts/soccer_slate.py [uefa.champions] [YYYYMMDD] [--n 300000]
Ratings come from fit_club_ratings.py (refit first: fetch_club_results.py, fetch_club_results_espn.py --uefa-only, fit_club_ratings.py)."""
import sys, json, argparse
import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import soccer_live as SL, soccer_markets as SM, nfl_sim_service as ns

LEAGUE = {"uefa.champions": "Champions League", "uefa.europa": "Europa League"}
K = 9


def rating_pool() -> dict:
    d = json.loads((HERE.parent / "data" / "soccer" / "club_ratings.json").read_text())["leagues"]
    return d["Europe"]["teams"]


def resolve(name: str, pool: dict) -> str | None:
    import edge_api as e
    return e.resolve_club(name, pool) or (name if name in pool else None)


def timeline(lh: float, la: float, n: int, rng) -> dict:
    nh, na = np.minimum(rng.poisson(lh, n), K), np.minimum(rng.poisson(la, n), K)
    ar = np.arange(K)[None, :]
    th = np.where(ar < nh[:, None], rng.random((n, K)), np.inf); ta = np.where(ar < na[:, None], rng.random((n, K)), np.inf)
    t = np.concatenate([th, ta], 1); s = np.concatenate([np.ones((n, K)), -np.ones((n, K))], 1)
    idx = np.argsort(t, 1); s = np.take_along_axis(s, idx, 1); t = np.take_along_axis(t, idx, 1); s = np.where(np.isinf(t), 0, s); cs = np.cumsum(s, 1)
    return dict(nh=nh, na=na, h1=cs.max(1) >= 1, a1=cs.min(1) <= -1, h2=cs.max(1) >= 2, a2=cs.min(1) <= -2)


def match(home_raw: str, away_raw: str, league: str, n: int, seed: int = 5) -> dict | None:
    pool = rating_pool(); h, a = resolve(home_raw, pool), resolve(away_raw, pool)
    if not h or not a:
        return {"error": f"sin rating: {home_raw if not h else away_raw}"}
    lh, la = SL.lambdas_from_ratings(league, h, a)
    mb = SM.derive_markets(SM.score_matrix(lh, la), total_lines=(1.5, 2.5, 3.5, 4.5))
    tl = timeline(lh, la, n, np.random.default_rng(seed))
    return {"home": h, "away": a, "lh": lh, "la": la, "book": mb, "tl": tl}


def report(m: dict) -> str:
    b, t = m["book"], m["tl"]
    cs = ", ".join(f"{x['score']} {x['prob']*100:.1f}%" for x in b.correct_score[:4])
    return (f"{m['home']} vs {m['away']}: goles esperados {m['lh']:.2f}-{m['la']:.2f} (total {b.expected_total_goals:.2f}) | 1X2 {b.home_win*100:.0f}/{b.draw*100:.0f}/{b.away_win*100:.0f} | "
            f"o1.5 {b.over_under[1.5]['over']*100:.0f}% o2.5 {b.over_under[2.5]['over']*100:.0f}% o3.5 {b.over_under[3.5]['over']*100:.0f}% | BTTS {b.btts_yes*100:.0f}% | marcadores: {cs} | "
            f"1UP casa {t['h1'].mean()*100:.0f}% visita {t['a1'].mean()*100:.0f}% | 2UP casa {t['h2'].mean()*100:.0f}% visita {t['a2'].mean()*100:.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slug", nargs="?", default="uefa.champions"); ap.add_argument("date", nargs="?", default=None); ap.add_argument("--n", type=int, default=300000)
    a = ap.parse_args(); date = a.date or __import__("datetime").date.today().strftime("%Y%m%d")
    for ev in ns._fetch(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{a.slug}/scoreboard?dates={date}")["events"]:
        c = ev["competitions"][0]["competitors"]; hn = next(x for x in c if x["homeAway"] == "home")["team"]["displayName"]; an = next(x for x in c if x["homeAway"] == "away")["team"]["displayName"]
        m = match(hn, an, LEAGUE[a.slug], a.n)
        print(f"{ev['date'][11:16]}Z {report(m) if 'error' not in m else hn + ' vs ' + an + ' -> ' + m['error']}")

"""Final slate card: market-anchored sim. The raw drive sim is re-weighted (exponential tilt on margin and total) so its win probability equals the
30/70 logit blend of sim and market (the weight that scored best walk-forward on 2026) and its total equals 85% market / 15% sim; every player prop is then
read from the SAME re-weighted games, so props stay correlated with the game script. Prints per game: projected score, modal scorelines, win prob, Stake
ML EV, key props. Usage: python3 scripts/nfl_slate_final.py [--dir SLATE_DIR] [--stake data/stake_nfl_ml_20261101.json]"""
import sys, json, pickle, argparse
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nfl_sim_service as ns
from nfl_slate_report import DEF_DIR, W_SIM, dk_lines, devig_ml

W_TOTAL_SIM = 0.15
SD_MARGIN = 13.2


def lgt(p):
    return float(np.log(p / (1 - p)))


def tilt(M, T, p_target, t_target, rounds=3):
    """weights w >= 0, sum 1, with P_w(M>0)=p_target and E_w[T]=t_target (alternating exponential tilts)."""
    w = np.full(len(M), 1.0 / len(M))
    win = (M > 0) + 0.5 * (M == 0)
    for _ in range(rounds):
        lo, hi = -3.0, 3.0
        for _ in range(60):
            c = (lo + hi) / 2
            ww = w * np.exp(c * (win - 0.5)); ww /= ww.sum()
            lo, hi = (c, hi) if (ww * win).sum() < p_target else (lo, c)
        w = w * np.exp(((lo + hi) / 2) * (win - 0.5)); w /= w.sum()
        lo, hi = -0.3, 0.3
        Tc = T - T.mean()
        for _ in range(60):
            c = (lo + hi) / 2
            ww = w * np.exp(c * Tc); ww /= ww.sum()
            lo, hi = (c, hi) if (ww * T).sum() < t_target else (lo, c)
        w = w * np.exp(((lo + hi) / 2) * Tc); w /= w.sum()
    return w


def wq(x, w, qs):
    i = np.argsort(x); cw = np.cumsum(w[i])
    return [float(x[i][np.searchsorted(cw, q)]) for q in qs]


def modal(H, A, w, k=3):
    d = defaultdict(float)
    for h, a, ww in zip(H.astype(int), A.astype(int), w):
        d[(h, a)] += ww
    return sorted(d.items(), key=lambda kv: -kv[1])[:k]


def card(key, r, g, line, stake_odds):
    away, home = key.split("@")
    P = g["P"]; M, T, H, A = P["M"], P["T"], P["H"], P["A"]
    pw_sim = float((M > 0).mean() + 0.5 * (M == 0).mean())
    mkt = devig_ml(line["home_ml"], line["away_ml"]) if line.get("home_ml") and line.get("away_ml") else pw_sim
    p = 1 / (1 + np.exp(-(W_SIM * lgt(pw_sim) + (1 - W_SIM) * lgt(mkt))))
    t_tgt = (1 - W_TOTAL_SIM) * line["total"] + W_TOTAL_SIM * float(T.mean()) if line.get("total") else float(T.mean())
    w = tilt(M, T, p, t_tgt)
    sc = modal(H, A, w)
    out = {"game": key, "p_home": p, "p_sim": pw_sim, "p_mkt": mkt, "score": (float((w * A).sum()), float((w * H).sum())), "total": float((w * T).sum()),
           "modal": [(int(a), int(b), float(pp)) for (b, a), pp in sc], "cover": None, "over": None, "ev": None, "props": {}}
    if line.get("spread") is not None:
        out["cover"] = float((w * (M + line["spread"] > 0)).sum()); out["over"] = float((w * (T > line["total"])).sum())
    if stake_odds:
        out["ev"] = (p * stake_odds[0] - 1, (1 - p) * stake_odds[1] - 1, stake_odds)
    for k, v in P.items():
        if k in ("M", "T", "H", "A") or "|" not in k:
            continue
        if k.endswith((" passY", " recY", " rushY", " rec", " comp", " car", " passTD", " ATD")) and "Others" not in k:
            if k.endswith(" ATD"):
                out["props"][k] = {"mean": float((w * v).sum())}
            elif v.mean() > 1.0:
                q = wq(v, w, (0.1, 0.5, 0.9))
                out["props"][k] = {"mean": float((w * v).sum()), "p10": q[0], "med": q[1], "p90": q[2]}
    return out


def fmt(o, meta, r):
    away, home = o["game"].split("@")
    s = [f"=== {away} @ {home}   QB {r['qb_away']} / {r['qb_home']}"]
    s.append(f"  MARCADOR proyectado {away} {o['score'][0]:.1f} - {o['score'][1]:.1f} {home}  (total {o['total']:.1f})   marcadores mas comunes: " +
             ", ".join(f"{away} {a}-{b} {home} ({pp*100:.1f}%)" for a, b, pp in o["modal"]))
    s.append(f"  P(gana) {home} {o['p_home']*100:.1f}% | {away} {(1-o['p_home'])*100:.1f}%   [sim {o['p_sim']*100:.0f}% / mercado {o['p_mkt']*100:.0f}%]" +
             (f"   P(cubre DK) {home} {o['cover']*100:.0f}%  Over {o['over']*100:.0f}%" if o["cover"] is not None else ""))
    if o["ev"]:
        eh, ea, od = o["ev"]
        s.append(f"  Stake ML {home} {od[0]} (EV {eh*100:+.0f}%) | {away} {od[1]} (EV {ea*100:+.0f}%)")
    for tm in (home, away):
        pr = {k.split("|", 1)[1]: v for k, v in o["props"].items() if k.startswith(tm + "|")}
        qb = [(k, v) for k, v in pr.items() if k.endswith(" passY")]
        recs = sorted([(k, v) for k, v in pr.items() if k.endswith(" recY")], key=lambda kv: -kv[1]["mean"])[:3]
        rush = sorted([(k, v) for k, v in pr.items() if k.endswith(" rushY") and "Others" not in k], key=lambda kv: -kv[1]["mean"])[:2]
        td = sorted([(k[:-4], v["mean"]) for k, v in pr.items() if k.endswith(" ATD")], key=lambda kv: -kv[1])[:3]
        parts = [f"{k[:-6]} pase {v['med']:.0f} [{v['p10']:.0f}-{v['p90']:.0f}]" for k, v in qb]
        parts += [f"{k[:-5]} rec {v['med']:.0f} [{v['p10']:.0f}-{v['p90']:.0f}]" for k, v in recs]
        parts += [f"{k[:-6]} carr {v['med']:.0f} [{v['p10']:.0f}-{v['p90']:.0f}]" for k, v in rush]
        s.append(f"  {tm}: " + "; ".join(parts))
        s.append(f"     TD: " + ", ".join(f"{n} {p*100:.0f}%" for n, p in td))
    return "\n".join(s)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEF_DIR)
    ap.add_argument("--stake", default=str(HERE.parent / "data" / "stake_nfl_ml_20261101.json"))
    ap.add_argument("--game", default="")
    a = ap.parse_args()
    sd = Path(a.dir)
    summary = {f"{r['away']}@{r['home']}": r for r in json.loads((sd / "slate_summary.json").read_text())}
    allp = pickle.load(open(sd / "slate_props.pkl", "rb"))
    stake = json.loads(Path(a.stake).read_text()) if Path(a.stake).exists() else {}
    fx = lambda t: ns._ABBR_ALIASES.get(t, t)
    sb = {f"{fx(e['competitions'][0]['competitors'][1]['team']['abbreviation'])}@{fx(e['competitions'][0]['competitors'][0]['team']['abbreviation'])}": e["id"]
          for e in ns._fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=20261101")["events"]}
    res = {}
    for key, g in allp.items():
        if a.game and key != a.game:
            continue
        o = card(key, summary[key], g, dk_lines(sb[key]), stake.get(key))
        res[key] = o
        print(fmt(o, g["meta"], summary[key]), "\n")
    pickle.dump(res, open(sd / "slate_final.pkl", "wb"))

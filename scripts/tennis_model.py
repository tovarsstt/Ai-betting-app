#!/usr/bin/env python3
"""tennis_model.py — the engine's calibrated tennis win-probability model (v4), built from real results with POINT-IN-TIME features.

Why it exists (2026-11-09): the points-logistic in edge_api ran ~6-12 pts BELOW the market on favourites (Sabalenka 59.5% vs ~65%; scale 0.9 on log-points was hand-set,
never fitted) and the previous v3 model lived in /tmp files that no longer exist. This module fits the scale on data, keeps every artifact in data/tennis/, and is
rebuilt by one command, so nothing depends on a temp directory.

  python3 scripts/tennis_model.py refresh              download current-season tennis-data.co.uk files, rebuild state + walk-forward report
  python3 scripts/tennis_model.py rebuild              rebuild from data/tennis/raw/*.xlsx (no download)
  python3 scripts/tennis_model.py predict "Sabalenka, Aryna" "Muchova, Karolina" [--surface Hard] [--odds 1.48 2.65]
  python3 scripts/tennis_model.py report               print data/tennis/model_v4_report.json

Features (all A-B differences, antisymmetric, no intercept): log ranking points, log rank, overall Elo, surface Elo, recent form (last 10), rest days, 14-day load,
shrunk head-to-head, and Elo x best-of-5. Elo/form/h2h are computed sequentially BEFORE each match is applied (no look-ahead).
Source: tennis-data.co.uk (closing odds included, used ONLY to evaluate and to fit the market anchor weight).
"""
from __future__ import annotations
import json, re, sys, math, argparse, urllib.request, unicodedata
from collections import deque, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "tennis"
RAW = DATA / "raw"
MODEL = DATA / "model_v4.json"
STATE = DATA / "state_v4.json"
REPORT = DATA / "model_v4_report.json"
URL = "https://tennis-data.co.uk/hrjk-85HytOjkhth76j_ygh4jf7/{y}{w}/{y}.xlsx"
FEATS = ["lpts", "lrank", "elo", "selo", "form", "rest", "load", "h2h", "elo_bo5"]
SURF = {"hard": "Hard", "clay": "Clay", "grass": "Grass", "carpet": "Hard"}


def key(name: str) -> list[str]:
    """Candidate lookup keys for any tennis name format: 'Sabalenka, Aryna' / 'Sabalenka A.' / 'Aryna Sabalenka' -> 'sabalenka a'."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"[^a-z ,.\-']", "", s).replace("-", " ").replace("'", "")
    out = []
    if "," in s:
        sur, first = [x.strip() for x in s.split(",", 1)]
        if sur and first: out.append(f"{sur} {first[0]}")
    else:
        t = s.replace(".", " ").split()
        if len(t) >= 2:
            if len(s.split()[-1]) <= 2 and s.endswith("."):      # 'Sabalenka A.' / 'De Minaur A.'
                out.append(" ".join(t[:-1]) + " " + t[-1][0])
            else:                                                 # 'Aryna Sabalenka' / 'Alex De Minaur'
                out.append(" ".join(t[1:]) + " " + t[0][0]); out.append(t[-1] + " " + t[0][0])
    return out or [s]


def _pk(name: str) -> str:
    return key(name)[0]


# ───────────────────────────────────────────────────────────────── data
def download(years=None):
    RAW.mkdir(parents=True, exist_ok=True)
    years = years or [pd.Timestamp.now().year]
    for y in years:
        for tour, w in (("atp", ""), ("wta", "w")):
            u = URL.format(y=y, w=w)
            try:
                b = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
                if b[:2] == b"PK": (RAW / f"{tour}_{y}.xlsx").write_bytes(b); print("downloaded", tour, y, len(b) // 1024, "KB")
                else: print("not an xlsx:", u)
            except Exception as e:
                print("download failed", u, repr(e)[:80])


def load_matches() -> pd.DataFrame:
    fr = []
    for f in sorted(RAW.glob("*_*.xlsx")):
        tour = f.name.split("_")[0]
        d = pd.read_excel(f); d["tour"] = tour
        for c in ("WPts", "LPts", "WRank", "LRank", "Best of", "PSW", "PSL", "AvgW", "AvgL", "B365W", "B365L"):
            if c not in d: d[c] = np.nan
        fr.append(d[["tour", "Date", "Tournament", "Surface", "Round", "Best of", "Winner", "Loser", "WRank", "LRank", "WPts", "LPts", "Comment", "PSW", "PSL", "AvgW", "AvgL", "B365W", "B365L"]])
    d = pd.concat(fr, ignore_index=True)
    d = d[d.Date.notna() & d.Winner.notna() & d.Loser.notna()].copy()
    d["Date"] = pd.to_datetime(d.Date)
    d = d.sort_values(["Date", "tour"], kind="stable").reset_index(drop=True)
    d["surf"] = d.Surface.astype(str).str.lower().map(SURF).fillna("Hard")
    d["bo"] = pd.to_numeric(d["Best of"], errors="coerce").fillna(3)
    d["completed"] = d.Comment.astype(str).str.lower().str.contains("complet")
    return d


def _pts(pts, rank):
    if pts is not None and not (isinstance(pts, float) and math.isnan(pts)) and pts > 0: return float(pts)
    if rank is not None and not (isinstance(rank, float) and math.isnan(rank)) and rank > 0: return 12000.0 * float(rank) ** -0.85
    return 300.0


def _rk(rank):
    return float(rank) if rank is not None and not (isinstance(rank, float) and math.isnan(rank)) and rank > 0 else 150.0


# ───────────────────────────────────────────────────────────────── state (Elo, surface Elo, form, rest, h2h) updated match by match
class State:
    def __init__(self):
        self.elo = defaultdict(lambda: [1500.0, 0]); self.selo = defaultdict(lambda: [1500.0, 0])
        self.form = defaultdict(lambda: deque(maxlen=10)); self.dates = defaultdict(lambda: deque(maxlen=12)); self.h2h = defaultdict(lambda: [0, 0])
        self.rank = {}; self.pts = {}

    @staticmethod
    def _k(n): return 250.0 / ((n + 5) ** 0.4)

    def feats(self, a, b, surf, bo, date):
        ea, eb = self.elo[a][0], self.elo[b][0]; sa, sb = self.selo[(a, surf)][0], self.selo[(b, surf)][0]
        fa = (sum(self.form[a]) + 2.5) / (len(self.form[a]) + 5); fb = (sum(self.form[b]) + 2.5) / (len(self.form[b]) + 5)
        def rest(p):
            ds = self.dates[p]; return min((date - ds[-1]).days, 14) if ds else 14
        def load(p): return sum(1 for d in self.dates[p] if (date - d).days <= 14)
        h = self.h2h[(a, b)]; hh = (h[0] - h[1]) / (h[0] + h[1] + 3.0)
        return ea - eb, sa - sb, fa - fb, rest(a) - rest(b), load(a) - load(b), hh

    def update(self, w, l, surf, date):
        for tbl, kw, kl in ((self.elo, w, l), (self.selo, (w, surf), (l, surf))):
            rw, rl = tbl[kw], tbl[kl]; exp = 1 / (1 + 10 ** ((rl[0] - rw[0]) / 400))
            tbl[kw] = [rw[0] + self._k(rw[1]) * (1 - exp), rw[1] + 1]; tbl[kl] = [rl[0] - self._k(rl[1]) * (1 - exp), rl[1] + 1]
        self.form[w].append(1); self.form[l].append(0); self.dates[w].append(date); self.dates[l].append(date)
        self.h2h[(w, l)][0] += 1; self.h2h[(l, w)][1] += 1

    def dump(self):
        return {"elo": {k: v for k, v in self.elo.items()}, "selo": {f"{k[0]}|{k[1]}": v for k, v in self.selo.items()},
                "form": {k: list(v) for k, v in self.form.items()}, "dates": {k: [d.strftime("%Y-%m-%d") for d in v] for k, v in self.dates.items()},
                "h2h": {f"{k[0]}|{k[1]}": v for k, v in self.h2h.items() if v[0] + v[1] > 0}, "rank": self.rank, "pts": self.pts}

    @classmethod
    def load(cls, d):
        s = cls()
        for k, v in d["elo"].items(): s.elo[k] = v
        for k, v in d["selo"].items(): a, b = k.rsplit("|", 1); s.selo[(a, b)] = v
        for k, v in d["form"].items(): s.form[k] = deque(v, maxlen=10)
        for k, v in d["dates"].items(): s.dates[k] = deque([pd.Timestamp(x) for x in v], maxlen=12)
        for k, v in d["h2h"].items(): a, b = k.split("|"); s.h2h[(a, b)] = v
        s.rank, s.pts = d.get("rank", {}), d.get("pts", {})
        return s


def build_dataset(d: pd.DataFrame):
    """Sequential pass -> rows (random orientation) with features, label, market prob; also returns the final State."""
    st = State(); rng = np.random.default_rng(11); rows = []
    for r in d.itertuples(index=False):
        w, l = _pk(r.Winner), _pk(r.Loser); date = r.Date
        pw, pl = _pts(r.WPts, r.WRank), _pts(r.LPts, r.LRank); kw, kl = _rk(r.WRank), _rk(r.LRank)
        st.rank[w], st.rank[l] = kw, kl; st.pts[w], st.pts[l] = pw, pl
        ed, sd, fd, rd, ld, hd = st.feats(w, l, r.surf, r.bo, date)               # from the WINNER's point of view
        if r.completed:
            flip = rng.random() < 0.5; sgn = -1.0 if flip else 1.0               # flip => A is the loser
            elo_d = sgn * ed
            x = [sgn * (math.log(pw) - math.log(pl)), sgn * (math.log(kl) - math.log(kw)), elo_d / 100.0, sgn * sd / 100.0, sgn * fd, sgn * rd / 14.0, sgn * ld / 4.0, sgn * hd, (elo_d / 100.0) * (1.0 if r.bo >= 5 else 0.0)]
            mk = np.nan
            for a_, b_ in (("PSW", "PSL"), ("AvgW", "AvgL"), ("B365W", "B365L")):
                ow, ol = getattr(r, a_), getattr(r, b_)
                if ow and ol and ow > 1 and ol > 1: mk = (1 / ow) / (1 / ow + 1 / ol); break
            rows.append((date, r.tour, r.surf, r.bo, 0.0 if flip else 1.0, (1 - mk) if flip and not np.isnan(mk) else mk, *x))
        st.update(w, l, r.surf, date)
    cols = ["date", "tour", "surf", "bo", "y", "mkt"] + FEATS
    return pd.DataFrame(rows, columns=cols), st


# ───────────────────────────────────────────────────────────────── fit / evaluate
def _sg(x): return 1 / (1 + np.exp(-x))
def _lg(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def fit_logit(X, y, l2=1.0, intercept=False, iters=60):
    X = np.asarray(X, float); y = np.asarray(y, float)
    if intercept: X = np.c_[np.ones(len(X)), X]
    b = np.zeros(X.shape[1]); R = np.eye(X.shape[1]) * l2
    if intercept: R[0, 0] = 0
    for _ in range(iters):
        p = _sg(X @ b); W = p * (1 - p); H = (X * W[:, None]).T @ X + R; g = X.T @ (y - p) - R @ b
        b = b + np.linalg.solve(H, g)
    return b


def logloss(p, y): p = np.clip(p, 1e-4, 1 - 1e-4); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
def brier(p, y): return float(np.mean((p - y) ** 2))
def slope(p, y):
    b = fit_logit(_lg(p).reshape(-1, 1), y, l2=1e-6, intercept=True); return float(b[1]), float(b[0])


def evaluate(ds: pd.DataFrame) -> dict:
    """Walk-forward by season: fit on all earlier seasons (>=2022 so Elo has a year of burn-in), test on the next."""
    ds = ds.copy(); ds["yr"] = pd.to_datetime(ds.date).dt.year; out = {"by_year": {}, "feats": FEATS}
    allp = []
    for ty in (2024, 2025, 2026):
        tr = ds[(ds.yr >= 2022) & (ds.yr < ty)]; te = ds[ds.yr == ty]
        if len(te) < 200: continue
        b = fit_logit(tr[FEATS].values, tr.y.values, l2=3.0)
        te = te.assign(p=_sg(te[FEATS].values @ b))
        base = 0.9 * te.lpts.values                                               # the engine's old points-logistic (scale 0.9, no fit)
        res = {"n": int(len(te)), "model_ll": logloss(te.p.values, te.y.values), "model_brier": brier(te.p.values, te.y.values), "model_slope": slope(te.p.values, te.y.values)[0],
               "old_points_ll": logloss(_sg(base), te.y.values), "old_points_brier": brier(_sg(base), te.y.values), "old_points_slope": slope(_sg(base), te.y.values)[0],
               "mean_fav_prob_model": float(np.maximum(te.p, 1 - te.p).mean()), "mean_fav_prob_old": float(np.maximum(_sg(base), 1 - _sg(base)).mean())}
        m = te.dropna(subset=["mkt"])
        if len(m) > 200:
            res.update({"n_mkt": int(len(m)), "market_ll": logloss(m.mkt.values, m.y.values), "market_brier": brier(m.mkt.values, m.y.values), "market_slope": slope(m.mkt.values, m.y.values)[0],
                        "model_ll_same_rows": logloss(m.p.values, m.y.values), "mean_fav_prob_market": float(np.maximum(m.mkt, 1 - m.mkt).mean()),
                        "mean_fav_prob_model_same_rows": float(np.maximum(m.p, 1 - m.p).mean())})
        out["by_year"][str(ty)] = res; allp.append(te.assign(p=te.p))
    # market-anchor weight: fit logit(y) = a*logit(model) + b*logit(market) on 2024+2025, check 2026
    mm = ds.dropna(subset=["mkt"]); tr = mm[(mm.yr >= 2023) & (mm.yr <= 2025)]; te = mm[mm.yr == 2026]
    bm = fit_logit(tr[FEATS].values, tr.y.values, l2=3.0)
    for frame in (tr, te): frame["pm"] = _sg(frame[FEATS].values @ bm)
    ab = fit_logit(np.c_[_lg(tr.pm.values), _lg(tr.mkt.values)], tr.y.values, l2=1e-3)
    out["anchor"] = {"coef_model": float(ab[0]), "coef_market": float(ab[1]), "fit_years": "2023-2025", "test_2026_ll_blend": logloss(_sg(np.c_[_lg(te.pm.values), _lg(te.mkt.values)] @ ab), te.y.values),
                     "test_2026_ll_market": logloss(te.mkt.values, te.y.values), "test_2026_ll_model": logloss(te.pm.values, te.y.values), "n_test": int(len(te))}
    return out


def rebuild(verbose=True):
    d = load_matches(); ds, st = build_dataset(d)
    rep = evaluate(ds); rep["n_matches"] = int(len(d)); rep["data_through"] = str(d.Date.max().date()); rep["built"] = str(pd.Timestamp.now().date())
    final = ds[pd.to_datetime(ds.date).dt.year >= 2022]
    b = fit_logit(final[FEATS].values, final.y.values, l2=3.0)
    rep["coef"] = dict(zip(FEATS, [round(float(x), 4) for x in b])); rep["n_train"] = int(len(final))
    DATA.mkdir(parents=True, exist_ok=True)
    MODEL.write_text(json.dumps({"feats": FEATS, "coef": [float(x) for x in b], "anchor": rep["anchor"], "data_through": rep["data_through"], "built": rep["built"]}, indent=1))
    STATE.write_text(json.dumps(st.dump())); REPORT.write_text(json.dumps(rep, indent=1))
    if verbose: print_report(rep)
    return rep


def print_report(rep):
    print(f"tennis v4 | matches {rep['n_matches']} through {rep['data_through']} | train rows {rep.get('n_train')}")
    print("coef:", rep.get("coef"))
    print(f"{'year':6s} {'n':>5s} | model ll  old-pts ll  market ll | slope model/old/mkt | avg fav prob model/old/market")
    for y, r in rep["by_year"].items():
        print(f"{y:6s} {r['n']:5d} | {r['model_ll']:.4f}    {r['old_points_ll']:.4f}     {r.get('market_ll', float('nan')):.4f}   | {r['model_slope']:.2f} / {r['old_points_slope']:.2f} / {r.get('market_slope', float('nan')):.2f} | {r['mean_fav_prob_model']:.3f} / {r['mean_fav_prob_old']:.3f} / {r.get('mean_fav_prob_market', float('nan')):.3f}")
    a = rep["anchor"]; print(f"anchor (fit 2023-25): logit(p)= {a['coef_model']:.2f}*logit(model) + {a['coef_market']:.2f}*logit(market) | 2026 ll blend {a['test_2026_ll_blend']:.4f} vs market {a['test_2026_ll_market']:.4f} vs model {a['test_2026_ll_model']:.4f} (n={a['n_test']})")


# ───────────────────────────────────────────────────────────────── inference (used by edge_api)
class TennisV4:
    _inst = None

    def __init__(self):
        m = json.loads(MODEL.read_text()); self.coef = np.array(m["coef"]); self.anchor = m["anchor"]; self.through = m["data_through"]
        self.st = State.load(json.loads(STATE.read_text()))
        self.known = set(self.st.elo)

    @classmethod
    def get(cls):
        if cls._inst is None:
            try: cls._inst = cls()
            except Exception: cls._inst = False
        return cls._inst or None

    def resolve(self, name):
        for k in key(name):
            if k in self.known: return k
        return None

    def predict(self, a_name, b_name, surface="Hard", best_of=3, market_odds=None, today=None):
        """P(A wins). market_odds=(dec_a, dec_b) optional -> anchored blend with the backtested weights. Returns dict or None if a player is unknown."""
        a, b = self.resolve(a_name), self.resolve(b_name)
        if not a or not b: return None
        surf = SURF.get(str(surface).lower(), "Hard"); date = pd.Timestamp(today) if today else pd.Timestamp.now().normalize()
        ed, sd, fd, rd, ld, hd = self.st.feats(a, b, surf, best_of, date)
        pa, pb = self.st.pts.get(a, 300.0), self.st.pts.get(b, 300.0); ra, rb = self.st.rank.get(a, 150.0), self.st.rank.get(b, 150.0)
        x = np.array([math.log(pa) - math.log(pb), math.log(rb) - math.log(ra), ed / 100.0, sd / 100.0, fd, rd / 14.0, ld / 4.0, hd, (ed / 100.0) * (1.0 if best_of >= 5 else 0.0)])
        p = float(_sg(float(x @ self.coef)))
        out = {"p_model": p, "elo_diff": round(ed, 1), "surface_elo_diff": round(sd, 1), "form_diff": round(fd, 3), "h2h": self.st.h2h[(a, b)], "rank": (ra, rb), "data_through": self.through}
        if market_odds and market_odds[0] > 1 and market_odds[1] > 1:
            pm = (1 / market_odds[0]) / (1 / market_odds[0] + 1 / market_odds[1])
            z = self.anchor["coef_model"] * _lg(p) + self.anchor["coef_market"] * _lg(pm)
            out.update({"p_market": pm, "p_anchored": float(_sg(z))})
        return out


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("refresh"); sub.add_parser("rebuild"); sub.add_parser("report")
    p = sub.add_parser("predict"); p.add_argument("a"); p.add_argument("b"); p.add_argument("--surface", default="Hard"); p.add_argument("--best-of", type=int, default=3); p.add_argument("--odds", nargs=2, type=float)
    a = ap.parse_args()
    if a.cmd == "refresh":
        cur = pd.Timestamp.now().year
        download(sorted({cur} | {y for y in range(2021, cur + 1) if not (RAW / f"atp_{y}.xlsx").exists() or not (RAW / f"wta_{y}.xlsx").exists()}))   # current season always, missing seasons on a fresh clone
        rebuild()
    elif a.cmd == "rebuild": rebuild()
    elif a.cmd == "report": print_report(json.loads(REPORT.read_text()))
    else:
        m = TennisV4.get()
        if not m: print("model not built: run `tennis_model.py rebuild`"); return
        print(json.dumps(m.predict(a.a, a.b, a.surface, a.best_of, tuple(a.odds) if a.odds else None), indent=1, default=str))


if __name__ == "__main__":
    main()

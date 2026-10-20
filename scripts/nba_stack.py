"""
nba_stack.py — stacked NBA win-probability ensemble + walk-forward backtest.

Three independent base models feed a logistic meta-model:
  A strength : margin-aware Elo
  B form     : mean margin of each team's last 5 games
  C context  : rest-day differential + back-to-backs (small logistic fit)
The meta-model sees logit(A), logit(B), logit(C) and the same terms x early_season,
so weights shift with context instead of a fixed average.

HONESTY: scored against Elo, not the closing line. ENGINE_V2.md found rest/B2B
not significant vs the closing line, so a gain here does NOT imply betting edge.
`market_logit` is an optional 4th feature: with closing lines it can be
validated for real; without them the ensemble is a ratings model only.

    python3 scripts/nba_stack.py            # walk-forward backtest on data/*.csv
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

DATA = Path(__file__).parent.parent / "data"
K, HOME_ELO, CARRY, SIGMA, FORM_N = 20.0, 70.0, 0.75, 12.0, 5


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _ncdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


@dataclass
class Team:
    elo: float = 1500.0
    recent: list = field(default_factory=list)
    last: date | None = None
    gp: int = 0


class State:
    def __init__(self) -> None:
        self.teams: dict[str, Team] = {}
        self.season = -1
        self.as_of = ""

    def t(self, name: str) -> Team:
        return self.teams.setdefault(name, Team())

    def new_season(self, season: int, gap: int = 1) -> None:
        for t in self.teams.values():
            t.elo = 1500 + (t.elo - 1500) * CARRY ** gap
            t.recent, t.gp, t.last = [], 0, None
        self.season = season

    def features(self, home: str, away: str, d: date, market_logit: float | None = None) -> dict:
        """Pre-game features; call BEFORE update() so nothing leaks."""
        h, a = self.t(home), self.t(away)
        rest = lambda t: 3 if t.last is None else min(max((d - t.last).days - 1, 0), 4)
        form = lambda t: sum(t.recent) / len(t.recent) if t.recent else 0.0
        hr, ar = rest(h), rest(a)
        return {"elo_diff": h.elo - a.elo, "form_diff": form(h) - form(a),
                "rest_diff": max(-3, min(3, hr - ar)), "h_b2b": float(hr == 0), "a_b2b": float(ar == 0),
                "early": float(min(h.gp, a.gp) < 15), "market_logit": market_logit}

    def update(self, home: str, away: str, hs: int, as_: int, d: date) -> None:
        h, a = self.t(home), self.t(away)
        m = hs - as_
        exp = 1 / (1 + 10 ** (-(h.elo + HOME_ELO - a.elo) / 400))
        sign = 1 if m > 0 else -1
        mov = (abs(m) + 3) ** 0.8 / (7.5 + 0.006 * abs(h.elo + HOME_ELO - a.elo) * sign)
        delta = K * mov * ((1 if m > 0 else 0) - exp)
        h.elo += delta; a.elo -= delta
        h.recent = (h.recent + [m])[-FORM_N:]; a.recent = (a.recent + [-m])[-FORM_N:]
        h.last = a.last = d; h.gp += 1; a.gp += 1
        self.as_of = d.isoformat()


def base_a(f: dict) -> float:
    return 1 / (1 + 10 ** (-(f["elo_diff"] + HOME_ELO) / 400))


def base_b(f: dict) -> float:
    return _ncdf((2.8 + 0.5 * f["form_diff"]) / SIGMA)


def _ctx_x(f: dict) -> list[float]:
    return [f["rest_diff"], f["h_b2b"], f["a_b2b"]]


class Stacker:
    def __init__(self, c_ctx: float = 0.5, c_meta: float = 0.2) -> None:
        self.ctx = LogisticRegression(C=c_ctx, max_iter=500)
        self.meta = LogisticRegression(C=c_meta, max_iter=500)
        self.use_market = False

    def _meta_x(self, feats: list[dict]) -> np.ndarray:
        pc = self.ctx.predict_proba(np.array([_ctx_x(f) for f in feats]))[:, 1]
        rows = []
        for f, p in zip(feats, pc):
            a, b, c = _logit(base_a(f)), _logit(base_b(f)), _logit(float(p))
            e = f["early"]
            row = [a, b, c, a * e, b * e, c * e]
            if self.use_market:
                row.append(f["market_logit"])
            rows.append(row)
        return np.array(rows)

    def fit(self, feats: list[dict], y: list[int]) -> "Stacker":
        self.use_market = all(f.get("market_logit") is not None for f in feats)
        self.ctx.fit(np.array([_ctx_x(f) for f in feats]), y)
        self.meta.fit(self._meta_x(feats), y)
        return self

    def predict(self, feats: list[dict]) -> np.ndarray:
        return self.meta.predict_proba(self._meta_x(feats))[:, 1]


def load_games(*paths: Path) -> list[dict]:
    rows = []
    for p in paths:
        if not p.exists():
            continue
        with p.open() as fh:
            for r in csv.DictReader(fh):
                rows.append({"date": date.fromisoformat(r["date"]), "home": r["home_team"], "away": r["away_team"],
                             "hs": int(r["home_score"]), "as": int(r["away_score"]), "season": int(r["season"])})
    return sorted(rows, key=lambda g: g["date"])


def log_loss(p, y) -> float:
    p = np.clip(np.asarray(p), 1e-9, 1 - 1e-9); y = np.asarray(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def backtest(games: list[dict], test_season: int, warmup: int = 300, refit_every: int = 100) -> dict:
    """Walk-forward: every prediction uses only games strictly before it."""
    st, feats, ys = State(), [], []
    stacker: Stacker | None = None
    since = 0
    preds = {"home_rate": [], "elo": [], "form": [], "stacked": []}
    yt: list[int] = []
    for g in games:
        if g["season"] != st.season:
            st.new_season(g["season"], 0 if st.season < 0 else g["season"] - st.season)
        f = st.features(g["home"], g["away"], g["date"])
        y = int(g["hs"] > g["as"])
        if g["season"] == test_season and stacker is not None:
            preds["home_rate"].append(float(np.mean(ys)))
            preds["elo"].append(base_a(f)); preds["form"].append(base_b(f))
            preds["stacked"].append(float(stacker.predict([f])[0])); yt.append(y)
        feats.append(f); ys.append(y)
        st.update(g["home"], g["away"], g["hs"], g["as"], g["date"])
        since += 1
        if len(feats) >= warmup and g["season"] >= test_season - 1 and (stacker is None or since >= refit_every):
            stacker = Stacker().fit(feats[warmup // 3:], ys[warmup // 3:]); since = 0
    res = {k: log_loss(v, yt) for k, v in preds.items()}
    d = np.array([-(y * math.log(s) + (1 - y) * math.log(1 - s)) + (y * math.log(e) + (1 - y) * math.log(1 - e))
                  for y, s, e in zip(yt, preds["stacked"], preds["elo"])])
    rng = np.random.default_rng(0)
    boots = np.sort([d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)])
    return {"n": len(yt), "logloss": res, "diff_vs_elo": float(d.mean()),
            "ci95": (float(boots[50]), float(boots[1949]))}


def main() -> None:
    games = load_games(DATA / "nba_historical.csv", DATA / "nba_games_2526.csv")
    counts: dict[int, int] = {}
    for g in games:
        counts[g["season"]] = counts.get(g["season"], 0) + 1
    seasons = sorted(counts)
    full = [s for s in seasons if counts[s] >= 800]   # a test season needs a real sample
    test = full[-1]
    r = backtest(games, test_season=test)
    print(f"games={len(games)} per-season={counts} test_season={test} n={r['n']}")
    for k, v in r["logloss"].items():
        print(f"  {k:10s} logloss {v:.4f}")
    print(f"  stacked - elo = {r['diff_vs_elo']:+.4f}  95% CI [{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}]")
    print("  NOTE: scored vs Elo, not the closing line — not proof of betting edge.")


if __name__ == "__main__":
    main()

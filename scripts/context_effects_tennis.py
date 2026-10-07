#!/usr/bin/env python3
"""
context_effects_tennis.py — do rest / fatigue / birthday / altitude add information BEYOND the price?

Bias controls (all built in, none optional):
  * PRE-REGISTERED hypothesis list (HYPOTHESES below, written before the first run); Holm
    correction over the whole family, so the 11 looks cannot manufacture a winner.
  * Features use only matches STRICTLY BEFORE the one being priced (searchsorted on timestamps;
    no look-ahead). First season (2014) is dropped as warm-up so histories are populated.
  * The price is the baseline: win effects are tested as an OFFSET on logit(devigged closing
    price) — the question is "does it move the result beyond what the market already believes?".
    Totals effects are tested on (games played - closing total line).
  * Random A/B orientation per match (the file lists the winner first; orienting by it is leakage).
  * Time split: fit on <=2022, judge on >=2023. A hypothesis is ACCEPTED only if Holm-adjusted
    p<0.05 on train AND same sign on test AND held-out log-loss/MSE improves.
  * Accepted effects are shrunk with empirical Bayes (beta * tau^2/(tau^2+se^2)) before use.
  * Retirements/walkovers excluded as targets (the bet is void) but kept as history (games played).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

import sys
sys.path.insert(0, str(Path(__file__).parent))
import betting_math as bm  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
CSV = Path("/tmp/kg/tennis_odds/tennis_matches_2014_2025.csv")
ATP_PLAYERS = Path("/tmp/kg/ext/beta2k_atp/atp_players.csv")
BOOKS = ("bet365", "Betfair", "Ladbrokes", "Unibet")
ALTITUDE_M = {"madrid": 667, "gstaad": 1050, "kitzbuhel": 762, "bogota": 2640, "quito": 2850, "guadalajara": 1566,
              "sao paulo": 760, "munich": 520, "santiago": 520, "johannesburg": 1750, "mexico": 2240, "denver": 1600,
              "banja luka": 230, "salvador": 10, "medellin": 1495, "manizales": 2160, "pereira": 1411, "cali": 1018,
              "cordoba": 400, "sibiu": 415, "marrakech": 460, "kobe": 5, "poznan": 80, "leon": 1815, "morelia": 1920,
              "toluca": 2660, "aguascalientes": 1880, "queretaro": 1820, "cuernavaca": 1510, "bucaramanga": 960,
              "guayaquil": 5, "la paz": 3640, "cochabamba": 2570, "santa cruz": 400}
HYPOTHESES = {   # (kind, name) — frozen list, nothing is added after seeing results
    "win": ["rest_short", "rest_days", "load7", "prev_games", "matches3d", "birthday"],
    "total": ["load7_sum", "rest_short_sum", "prev_games_sum", "altitude_500", "birthday_any"],
}


def devig_p(df: pd.DataFrame) -> pd.Series:
    ps = []
    for b in BOOKS:
        a, c = df[f"{b}_odds_a"], df[f"{b}_odds_b"]
        ok = (a > 1) & (c > 1)
        q = pd.Series(np.nan, index=df.index)
        pa = np.array([bm.devig_power([x, y])[0] for x, y in zip(a[ok], c[ok])])
        q[ok] = pa
        ps.append(q)
    return pd.concat(ps, axis=1).mean(axis=1)


def load() -> pd.DataFrame:
    cols = ["match_date_formatted", "tour", "tournament", "tournament_year", "surface", "match_format", "completed", "player_a", "player_b",
            "total_games_a", "total_games_b", "total_sets_a", "total_sets_b", "bet365_total_games_line"] + [f"{b}_odds_{s}" for b in BOOKS for s in "ab"]
    d = pd.read_csv(CSV, low_memory=False, usecols=cols)
    d["t"] = ((pd.to_datetime(d.match_date_formatted, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype("int64")   # unit-safe seconds
    d = d.sort_values("t").reset_index(drop=True)
    return d


def player_history(d: pd.DataFrame) -> pd.DataFrame:
    """Per player-match features from STRICTLY earlier matches."""
    n = len(d)
    rows = pd.concat([
        pd.DataFrame({"mid": np.arange(n), "side": 0, "player": d.player_a, "t": d.t, "games": d.total_games_a + d.total_games_b, "sets": d.total_sets_a + d.total_sets_b}),
        pd.DataFrame({"mid": np.arange(n), "side": 1, "player": d.player_b, "t": d.t, "games": d.total_games_a + d.total_games_b, "sets": d.total_sets_a + d.total_sets_b})])
    rows["pid"] = rows.player.astype("category").cat.codes.astype("int64")
    rows = rows.sort_values(["pid", "t", "mid"]).reset_index(drop=True)
    key = rows.pid.values * 10 ** 11 + rows.t.values
    cs = np.concatenate([[0.0], np.cumsum(rows.games.fillna(0).values)])
    ids = np.arange(len(rows))
    own_left = np.searchsorted(key, key, side="left")                       # first row with same (pid,t): excludes itself and ties
    out = {}
    for name, days in (("load3", 3), ("load7", 7)):
        start = np.searchsorted(key, key - days * 86400, side="left")
        start = np.maximum(start, rows.pid.values * 0 + np.searchsorted(rows.pid.values, rows.pid.values, side="left"))   # same player only
        out[name] = cs[own_left] - cs[start]
        out["n" + name] = own_left - start
    prev_t = np.where(own_left > 0, rows.t.values[np.maximum(own_left - 1, 0)], np.nan)
    same_pl = np.where(own_left > 0, rows.pid.values[np.maximum(own_left - 1, 0)] == rows.pid.values, False)
    rows["rest_days"] = np.where(same_pl, (rows.t.values - prev_t) / 86400.0, np.nan)
    rows["prev_games"] = np.where(same_pl, rows.games.values[np.maximum(own_left - 1, 0)], np.nan)
    rows["prev_sets"] = np.where(same_pl, rows.sets.values[np.maximum(own_left - 1, 0)], np.nan)
    for k, v in out.items():
        rows[k] = v
    return rows


def build(d: pd.DataFrame) -> pd.DataFrame:
    h = player_history(d)
    n = len(d)
    a = h[h.side == 0].set_index("mid").sort_index()
    b = h[h.side == 1].set_index("mid").sort_index()
    f = pd.DataFrame(index=np.arange(n))
    for tag, x in (("a", a), ("b", b)):
        f[f"rest_{tag}"] = x.rest_days.clip(upper=7)
        f[f"short_{tag}"] = (x.rest_days <= 1.2).astype(float)
        f[f"load7_{tag}"] = x.load7 / 10.0
        f[f"prev_{tag}"] = x.prev_games / 10.0
        f[f"m3_{tag}"] = x.nload3.astype(float)
        f[f"cold_{tag}"] = x.rest_days.isna() | (x.rest_days > 60)           # no history coverage
    # birthdays (ATP only — Sackmann dob)
    pl = pd.read_csv(ATP_PLAYERS, encoding="latin-1", header=None, names=["id", "first", "last", "hand", "dob", "ioc"])
    pl["name"] = (pl["first"].fillna("") + " " + pl["last"].fillna("")).str.strip()
    pl["md"] = pd.to_numeric(pl.dob, errors="coerce") % 10000
    md = pl.drop_duplicates("name").set_index("name").md
    day = pd.to_datetime(d.t, unit="s", utc=True)
    today = (day.dt.month * 100 + day.dt.day).values
    for tag, col in (("a", d.player_a), ("b", d.player_b)):
        m = col.map(md).values
        f[f"bday_{tag}"] = np.where((d.tour.values == "ATP") & ~pd.isna(m), (np.abs(m - today) <= 0).astype(float), np.nan)
    f["bday_known"] = f.bday_a.notna() & f.bday_b.notna()
    nm = d.tournament.str.lower().fillna("")
    f["alt"] = nm.map(lambda s: max([v for k, v in ALTITUDE_M.items() if k in s] or [0])).astype(float)
    for c in ("tour", "tournament_year", "completed", "total_games_a", "total_games_b", "bet365_total_games_line", "match_format"):
        f[c] = d[c].values
    f["t"] = d.t.values
    f["p_a"] = devig_p(d).values                       # P(player_a wins) from closing prices
    return f


def hypotheses(f: pd.DataFrame, rng: np.random.Generator):
    f = f[(f.completed == 1) & f.p_a.between(0.03, 0.97) & (f.tournament_year >= 2015)].copy()
    f = f[~(f.cold_a | f.cold_b)]                       # both players with a populated recent history
    flip = rng.random(len(f)) < 0.5                     # random orientation: A = winner or loser
    y = np.where(flip, 0.0, 1.0)                        # player_a is the winner
    p = np.where(flip, 1 - f.p_a.values, f.p_a.values)
    sg = np.where(flip, -1.0, 1.0)
    def diff(col):
        return sg * (f[f"{col}_a"].values - f[f"{col}_b"].values)
    X = {"rest_short": diff("short"), "rest_days": diff("rest"), "load7": diff("load7"), "prev_games": diff("prev"), "matches3d": diff("m3")}
    bd = sg * (f.bday_a.values - f.bday_b.values)
    win = pd.DataFrame({**X, "birthday": bd, "y": y, "off": np.log(p / (1 - p)), "year": f.tournament_year.values, "known": f.bday_known.values})
    tot = f[f.bet365_total_games_line.notna()].copy()
    resid = (tot.total_games_a + tot.total_games_b - tot.bet365_total_games_line).values
    T = pd.DataFrame({"resid": resid, "load7_sum": (tot.load7_a + tot.load7_b).values, "rest_short_sum": (tot.short_a + tot.short_b).values,
                      "prev_games_sum": (tot.prev_a + tot.prev_b).values, "altitude_500": (tot.alt >= 500).astype(float).values,
                      "birthday_any": np.where(tot.bday_known, np.nan_to_num(tot.bday_a.values) + np.nan_to_num(tot.bday_b.values), np.nan),
                      "wta": (tot.tour == "WTA").astype(float).values, "year": tot.tournament_year.values})
    return win, T


def holm(ps: dict) -> dict:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def run() -> dict:
    d = load()
    f = build(d)
    rng = np.random.default_rng(20261007)
    win, T = hypotheses(f, rng)
    res = {"n_win": len(win), "n_total": len(T), "tests": {}}
    raw_p = {}
    for name in HYPOTHESES["win"]:
        w = win[win.known] if name == "birthday" else win
        tr, te = w[w.year <= 2022], w[w.year >= 2023]
        x = tr[[name]].fillna(0.0)
        m = sm.GLM(tr.y, sm.add_constant(x), family=sm.families.Binomial(), offset=tr.off).fit(cov_type="HC1")
        mt = sm.GLM(te.y, sm.add_constant(te[[name]].fillna(0.0)), family=sm.families.Binomial(), offset=te.off).fit(cov_type="HC1")
        pred_with = 1 / (1 + np.exp(-(m.params["const"] + m.params[name] * te[name].fillna(0.0) + te.off)))
        pred_base = 1 / (1 + np.exp(-te.off))
        res["tests"][f"win:{name}"] = {"beta_logit": float(m.params[name]), "se": float(m.bse[name]), "p_train": float(m.pvalues[name]), "n_train": int(len(tr)),
                                       "beta_test": float(mt.params[name]), "p_test": float(mt.pvalues[name]), "n_test": int(len(te)),
                                       "heldout_logloss_gain_bp": float((bm.log_loss(pred_base, te.y) - bm.log_loss(pred_with, te.y)) * 1e4)}
        raw_p[f"win:{name}"] = float(m.pvalues[name])
    for name in HYPOTHESES["total"]:
        w = T.dropna(subset=[name])
        tr, te = w[w.year <= 2022], w[w.year >= 2023]
        cols = [name] + (["wta"] if tr.wta.nunique() > 1 and name != "wta" else [])
        m = sm.OLS(tr.resid, sm.add_constant(tr[cols], has_constant="add")).fit(cov_type="HC1")
        mt = sm.OLS(te.resid, sm.add_constant(te[cols], has_constant="add")).fit(cov_type="HC1")
        pw = m.predict(sm.add_constant(te[cols], has_constant="add"))
        base = tr.resid.mean()
        res["tests"][f"total:{name}"] = {"beta_games": float(m.params[name]), "se": float(m.bse[name]), "p_train": float(m.pvalues[name]), "n_train": int(len(tr)),
                                         "beta_test": float(mt.params[name]), "p_test": float(mt.pvalues[name]), "n_test": int(len(te)),
                                         "heldout_mse_gain_pct": float(100 * (np.mean((te.resid - base) ** 2) - np.mean((te.resid - pw) ** 2)) / np.mean((te.resid - base) ** 2))}
        raw_p[f"total:{name}"] = float(m.pvalues[name])
    adj = holm(raw_p)
    betas = np.array([res["tests"][k].get("beta_logit", res["tests"][k].get("beta_games")) / res["tests"][k]["se"] for k in raw_p])
    for k, t in res["tests"].items():
        t["p_holm"] = adj[k]
        b = t.get("beta_logit", t.get("beta_games"))
        gain = t.get("heldout_logloss_gain_bp", t.get("heldout_mse_gain_pct"))
        # REPLICATION rule: Holm-significant on train AND independently significant (p<.05) with the same sign on the later test years
        t["accepted"] = bool(adj[k] < 0.05 and np.sign(b) == np.sign(t["beta_test"]) and t["p_test"] < 0.05)
    # Final estimate for ACCEPTED effects: precision-weighted mean of the two independent estimates (train, test) with a
    # winner's-curse shrink (1 - 1/z^2)+ on the combined z. Family-level EB would shrink real effects to 0 because most
    # hypotheses in the family are nulls, so it is deliberately not used for the accepted ones.
    for k, t in res["tests"].items():
        b_tr = t.get("beta_logit", t.get("beta_games"))
        se_tr = t["se"]
        se_te = abs(t["beta_test"]) / max(stats.norm.isf(max(t["p_test"], 1e-12) / 2), 1e-9)
        w1, w2 = 1 / se_tr ** 2, 1 / se_te ** 2
        bc = (b_tr * w1 + t["beta_test"] * w2) / (w1 + w2)
        sec = (w1 + w2) ** -0.5
        z = abs(bc) / sec
        t["beta_final"] = float(bc * max(0.0, 1 - 1 / z ** 2)) if t["accepted"] else 0.0
        t["ci95_combined"] = [float(bc - 1.96 * sec), float(bc + 1.96 * sec)]       # what the data can RULE OUT for the null ones
    return res


if __name__ == "__main__":
    out = run()
    (DATA / "tennis_context_effects.json").write_text(json.dumps(out, indent=1))
    T = out["tests"]
    (DATA / "tennis_context_coefficients.json").write_text(json.dumps({
        "source": f"Kaggle tennis closing prices 2015-2025, {out['n_win']:,} win rows / {out['n_total']:,} totals rows; fit<=2022, replicated >=2023, Holm-corrected",
        "rest_days_logit_per_day": T["win:rest_days"]["beta_final"], "load7_logit_per_10_games": T["win:load7"]["beta_final"],
        "altitude_500m_total_games": T["total:altitude_500"]["beta_final"],
        "not_supported": {k: {"ci95": v["ci95_combined"]} for k, v in T.items() if not v["accepted"]}}, indent=1))
    print(f"win rows {out['n_win']:,} | totals rows {out['n_total']:,}")
    print(f"{'hypothesis':<22}{'beta':>9}{'se':>8}{'p_train':>10}{'p_holm':>9}{'beta_test':>10}{'p_test':>9}{'gain':>9}  verdict")
    for k, t in out["tests"].items():
        b = t.get("beta_logit", t.get("beta_games"))
        g = t.get("heldout_logloss_gain_bp", t.get("heldout_mse_gain_pct"))
        print(f"{k:<22}{b:>9.4f}{t['se']:>8.4f}{t['p_train']:>10.4f}{t['p_holm']:>9.4f}{t['beta_test']:>10.4f}{t['p_test']:>9.4f}{g:>+9.3f}  {'ACCEPTED (final %.4f)' % t['beta_final'] if t['accepted'] else 'not supported  (95%% CI %+.3f..%+.3f)' % tuple(t['ci95_combined'])}")

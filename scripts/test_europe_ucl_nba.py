"""Tests for fetch_europe_data / ucl_model / nba_stack. No network, ever."""
import math
from datetime import date

import numpy as np

import fetch_europe_data as fe
import nba_stack as ns
import ucl_model as um

CLUBELO = """Rank,Club,Country,Level,Elo,From,To
1,Man City,ENG,1,2050.5,2026-10-19,2026-10-25
2,Slavia Praha,CZE,1,1710.2,2026-10-19,2026-10-25
3,Broken,XXX,1,notanumber,2026-10-19,2026-10-25
"""


def test_parse_clubelo_skips_bad_rows():
    d = fe.parse_clubelo_csv(CLUBELO)
    assert set(d) == {"Man City", "Slavia Praha"} and d["Man City"]["elo"] == 2050.5


def _ev(id_, completed, hs, as_, date_="2025-10-22T00:30Z"):
    return {"id": id_, "date": date_, "status": {"type": {"completed": completed}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "score": hs, "team": {"displayName": "New York Knicks"}},
                {"homeAway": "away", "score": as_, "team": {"displayName": "Boston Celtics"}}]}]}


def test_espn_parse_only_finished_and_utc_shift():
    out = fe.parse_espn_scoreboard({"events": [_ev("1", True, "110", "104"), _ev("2", False, "0", "0"),
                                               {"id": "3"}]})
    assert len(out) == 1
    g = out[0]
    assert g["home_score"] == 110 and g["away_score"] == 104
    assert g["date"] == "2025-10-21" and g["season"] == 2025   # 00:30Z = previous US evening


def test_season_label():
    assert fe.season_start_year(date(2026, 1, 5)) == 2025 and fe.season_start_year(date(2026, 10, 20)) == 2026


def test_calibrate_recovers_known_params():
    rng = np.random.default_rng(1)
    elo = {f"T{i}": 1500 + rng.normal(0, 150) for i in range(40)}
    names = list(elo)
    a, h, b = math.log(1.4), 0.15, 0.45
    rows = []
    for _ in range(6000):
        x, y = rng.choice(names, 2, replace=False)
        d = (elo[x] - elo[y]) / 400
        rows.append({"home_team": x, "away_team": y, "neutral": "FALSE",
                     "home_score": rng.poisson(math.exp(a + h + b * d)), "away_score": rng.poisson(math.exp(a - b * d))})
    m = um.calibrate(rows, elo)
    assert m.calibrated and m.n_matches == 6000
    assert abs(m.b - b) < 0.05 and abs(m.a - a) < 0.05 and abs(m.h - h) < 0.05


def test_calibrate_falls_back_when_data_thin():
    assert not um.calibrate([], {}).calibrated


def test_price_match_probs_and_order():
    elo = {"A": 1900.0, "B": 1600.0}
    r = um.price_match("A", "B", elo, market_odds=(1.5, 4.5, 7.0))
    p = r["p_win"]
    assert abs(sum(p.values()) - 1) < 1e-9 and p["home"] > p["away"]
    assert r["calibrated"] is False and "ev_per_unit" in r
    assert abs(sum(r["market_fair"].values()) - 1) < 1e-9
    assert list(r)[:3] == ["lambda_home", "lambda_away", "calibrated"]  # no EV before P(win) keys exist
    assert p["home"] > r["market_fair"]["home"] * 0.6  # blend sits between model and market


def test_price_match_never_imputes_missing_club():
    assert "error" in um.price_match("A", "Unknown", {"A": 1800.0})


def test_neutral_symmetry():
    m = um.EloGoalModel()
    lh, la = um.lambdas(m, 1700, 1700, neutral=True)
    assert abs(lh - la) < 1e-12


def _games(n=900):
    rng = np.random.default_rng(3)
    teams = [f"T{i}" for i in range(12)]
    skill = {t: rng.normal(0, 4) for t in teams}
    out, d0 = [], date(2023, 10, 20).toordinal()
    for i in range(n):
        h, a = rng.choice(teams, 2, replace=False)
        margin = skill[h] - skill[a] + 2.8 + rng.normal(0, 11)
        out.append({"date": date.fromordinal(d0 + i // 6), "home": h, "away": a,
                    "hs": 110 + int(max(margin, 0)) + 1, "as": 110 + int(max(-margin, 0)), "season": 2023 if i < 450 else 2024})
    return out


def test_features_before_update_no_leak():
    st = ns.State()
    st.new_season(2024, 0)
    f = st.features("A", "B", date(2024, 10, 22))
    assert f["elo_diff"] == 0 and f["form_diff"] == 0 and f["early"] == 1
    st.update("A", "B", 120, 100, date(2024, 10, 22))
    assert st.features("A", "B", date(2024, 10, 23))["elo_diff"] > 0


def test_backtest_runs_walk_forward_and_beats_constant():
    r = ns.backtest(_games(), test_season=2024, warmup=150, refit_every=50)
    assert r["n"] > 100
    assert r["logloss"]["stacked"] < r["logloss"]["home_rate"]
    assert r["ci95"][0] <= r["diff_vs_elo"] <= r["ci95"][1]


def test_stacker_probabilities_valid():
    g = _games(400)
    st, feats, ys = ns.State(), [], []
    for x in g:
        if x["season"] != st.season:
            st.new_season(x["season"], 0 if st.season < 0 else 1)
        feats.append(st.features(x["home"], x["away"], x["date"])); ys.append(int(x["hs"] > x["as"]))
        st.update(x["home"], x["away"], x["hs"], x["as"], x["date"])
    p = ns.Stacker().fit(feats, ys).predict(feats)
    assert ((p > 0) & (p < 1)).all()


def test_write_csv_does_not_overwrite_with_empty(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("a\n1\n")
    assert fe.write_csv([], p, ["a"]) == 0
    assert p.read_text() == "a\n1\n"


def test_normalize_bridges_spellings():
    import calibrate_ucl as cu
    assert cu.normalize("Ath Madrid") == "atletico" and cu.normalize("Atlético") == "atletico"
    assert cu.normalize("FC Porto") == "porto" and cu.normalize("Paris SG") == "paris sg"


def test_run_drops_unmatched_and_lists_them(tmp_path):
    import calibrate_ucl as cu
    (tmp_path / "e.csv").write_text("Club,elo\nTeam A,1700\nTeam B,1600\n")
    (tmp_path / "r.csv").write_text("home_team,away_team,home_score,away_score,neutral\nTeam A,Team B,2,1,FALSE\nTeam A,Ghost FC,1,0,FALSE\n")
    res = cu.run(tmp_path / "e.csv", [tmp_path / "r.csv"], tmp_path / "o.json")
    assert res["unmatched_clubs"] == ["Ghost FC"] and res["calibrated"] is False  # too few matches -> priors

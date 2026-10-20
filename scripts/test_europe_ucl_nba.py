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
    assert cu.normalize("Atletico Madrid") == cu.normalize("Ath Madrid") == "ath madrid"
    assert cu.normalize("Paris Saint-Germain") == cu.normalize("Paris SG") == "paris sg"
    assert cu.normalize("Manchester City") == cu.normalize("Man City")


def test_build_elo_links_leagues_via_uefa_and_has_no_lookahead():
    import ucl_model as um
    rows = []
    d = 1
    for _ in range(12):  # league A strong team beats weak; league B likewise
        for lg, t1, t2 in (("A", "A1", "A2"), ("B", "B1", "B2")):
            rows.append({"date": f"2026-01-{d:02d}", "home_team": t1, "away_team": t2, "home_score": 2,
                         "away_score": 0, "neutral": "FALSE", "league": lg}); d += 1
    for i in range(6):  # A1 repeatedly beats B1 in Europe
        rows.append({"date": f"2026-02-{i+1:02d}", "home_team": "A1", "away_team": "B1", "home_score": 3,
                     "away_score": 0, "neutral": "FALSE", "league": "UEFA Champions League"})
    elo, samples = um.build_elo(rows, burn_in=5)
    assert elo["A1"] > elo["B1"]
    first = samples[0]
    assert first["eh"] == first["eh"] and abs(first["eh"] - 1500) < 200   # pre-match, not final


def test_run_reports_unlinked_uefa_clubs(tmp_path):
    import calibrate_ucl as cu
    (tmp_path / "u.csv").write_text("date,home_team,away_team,home_score,away_score,neutral,league\n"
                                    "2026-01-01,Slavia Praha,Porto,1,1,FALSE,UEFA Champions League\n")
    (tmp_path / "c.csv").write_text("date,home_team,away_team,home_score,away_score,neutral,league\n"
                                    "2026-01-01,Porto,Benfica,1,0,FALSE,Primeira Liga\n")
    res = cu.run([tmp_path / "c.csv", tmp_path / "u.csv"], tmp_path)
    assert "slavia praha" in res["uefa_clubs_without_domestic_data"] and res["calibrated"] is False


def test_parse_espn_soccer_only_finished():
    def ev(done, h, a):
        return {"date": "2026-10-20T19:00Z", "status": {"type": {"completed": done}},
                "competitions": [{"competitors": [{"homeAway": "home", "score": str(h), "team": {"displayName": "Liverpool"}},
                                                  {"homeAway": "away", "score": str(a), "team": {"displayName": "Villarreal"}}]}]}
    out = fe.parse_espn_soccer({"events": [ev(True, 2, 0), ev(False, 0, 0), {"x": 1}]}, "UEFA Champions League")
    assert len(out) == 1 and out[0]["home_score"] == 2 and out[0]["league"].startswith("UEFA")


def test_fixtures_parse_and_pricing_skips_unknown_clubs():
    import price_today as pt
    ev = {"date": "2026-10-20T19:00Z", "status": {"type": {"completed": False, "state": "pre"}},
          "competitions": [{"competitors": [{"homeAway": "home", "team": {"displayName": "Liverpool"}},
                                            {"homeAway": "away", "team": {"displayName": "Villarreal"}}]}]}
    fx = fe.parse_espn_fixtures({"events": [ev, {"bad": 1}]})
    assert len(fx) == 1 and fx[0]["home"] == "Liverpool"
    out = pt.price_fixtures(fx, {"liverpool": 1800.0}, um.EloGoalModel())
    assert "error" in out[0] and "villarreal" in out[0]["error"]


def test_fetch_uefa_queries_single_days_tue_to_thu_only(monkeypatch):
    import json
    urls = []

    def fake_get(url, *a, **k):
        urls.append(url)
        return json.dumps({"events": []})

    monkeypatch.setattr(fe, "_get", fake_get)
    fe.fetch_uefa(date(2026, 10, 12), date(2026, 10, 18), workers=1)   # Mon..Sun
    assert len(urls) == 3 * 3                                          # Tue/Wed/Thu x 3 competitions
    assert all("dates=2026101" in u and "-" not in u.split("dates=")[1] for u in urls)  # no ranges


def test_low_sample_flag():
    import price_today as pt
    fx = [{"home": "Liverpool", "away": "Slovan Bratislava", "kickoff": "x"}]
    out = pt.price_fixtures(fx, {"liverpool": 1800.0, "slovan bratislava": 1500.0}, um.EloGoalModel(),
                            {"liverpool": 120, "slovan bratislava": 6})
    assert out[0]["low_sample"] == ["Slovan Bratislava"]


def test_validate_ucl_walk_forward_runs_on_synthetic():
    import validate_ucl as vu
    rng = np.random.default_rng(5)
    teams = {lg: [f"{lg}{i}" for i in range(6)] for lg in "AB"}
    skill = {t: rng.normal(0, 0.4) for ts in teams.values() for t in ts}
    rows, day = [], 0
    def match(h, a, lg):
        nonlocal day
        day += 1
        lh = np.exp(0.2 + 0.15 + skill[h] - skill[a]); la = np.exp(0.2 + skill[a] - skill[h])
        rows.append({"date": f"2025-{1 + day // 300:02d}-{1 + day % 28:02d}", "home_team": h, "away_team": a,
                     "home_score": int(rng.poisson(lh)), "away_score": int(rng.poisson(la)), "neutral": "FALSE", "league": lg})
    for _ in range(40):
        for lg in "AB":
            for i in range(6):
                match(teams[lg][i], teams[lg][(i + 1) % 6], lg)
        match(rng.choice(teams["A"]), rng.choice(teams["B"]), "UEFA Champions League")
    res = vu.evaluate(rows, cutoff="2025-02-01", min_games=4)
    assert res["n_test"] > 0 and res["logloss_model"] is not None


def _fx(name):
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).parent / "fixtures" / name).read_text())
    evs = []
    for e in d["events"]:
        evs.append({"name": e["name"], "date": e["date"], "status": {"type": {"state": e["status"]}},
                    "competitions": [{"odds": e["odds"], "competitors": [
                        {"homeAway": c["homeAway"], "team": {"displayName": c["team"]}} for c in e["competitors"]]}]})
    return {"events": evs}


def test_parse_real_espn_soccer_moneyline():
    import value_picks as vp
    evs = {e["home"]: e for e in vp.events_from_scoreboard(_fx("espn_ucl_odds_2026-10-20.json"))}
    ml = vp.parse_moneyline(evs["Liverpool"]["odds"])
    assert ml["home"] == -200 and ml["away"] == 500 and ml["draw"] == 370 and ml["provider"] == "DraftKings"


def test_parse_real_espn_nba_moneyline_two_way():
    import value_picks as vp
    evs = {e["home"]: e for e in vp.events_from_scoreboard(_fx("espn_nba_odds_2026-10-20.json"))}
    ml = vp.parse_moneyline(evs["New York Knicks"]["odds"])
    assert ml["home"] == -180 and ml["away"] == 150 and "draw" not in ml


def test_parse_moneyline_missing_returns_none():
    import value_picks as vp
    assert vp.parse_moneyline(None) is None and vp.parse_moneyline([{"moneyline": {"home": {}}}]) is None


def test_build_rows_ev_and_devig_math():
    import value_picks as vp
    rows = vp.build_rows({"home": 0.60, "away": 0.40}, {"home": -110, "away": -110}, {"home": "H", "away": "A"}, "m", w=1.0)
    h = [r for r in rows if r["pick"] == "H"][0]
    assert abs(h["p_market"] - 0.5) < 1e-9 and abs(h["ev"] - (0.6 * (100 / 110 + 1) - 1)) < 1e-9


def test_ranking_is_pwin_first_and_longshots_never_recommended():
    import value_picks as vp
    rows = vp.build_rows({"home": 0.30, "draw": 0.25, "away": 0.45}, {"home": 300, "draw": 280, "away": -110}, {"home": "H", "draw": "D", "away": "A"}, "m", w=1.0)
    ranked = vp.rank(rows)
    assert [r["pick"] for r in ranked][0] == "A"                       # likeliest winner first
    assert all(vp.reject_reason(r) for r in rows if r["p_win"] < 0.5)  # longshots rejected even if +EV


def test_big_model_market_gap_is_flagged_not_recommended():
    import value_picks as vp
    r = vp.build_rows({"home": 0.80, "away": 0.20}, {"home": 120, "away": -140}, {"home": "H", "away": "A"}, "m", w=1.0)
    home = [x for x in r if x["pick"] == "H"][0]
    assert home["ev"] > 0 and "gap" in vp.reject_reason(home)


def test_nba_predict_fixture_unknown_team_is_none():
    st = ns.State()
    st.new_season(2025, 0)
    st.update("A", "B", 100, 90, date(2025, 11, 1))
    stk = ns.Stacker()
    assert ns.predict_fixture(st, stk, "A", "Nobody", date(2025, 11, 5)) is None

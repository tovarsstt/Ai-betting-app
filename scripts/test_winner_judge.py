"""Tests for the winner-first Judge (winner_judge.py). No network, no edge_api
load — the ratings lens is fed directly via game['ratings_margin']."""
import winner_judge as wj

SIMS = 200_000


def _game(**kw):
    g = {"sport": "NFL", "home": "Home", "away": "Away",
         "moneyline": {"home": 265, "away": -330}, "spread": {"home_line": 6.5},
         "total": {"points": 44.5}, "ratings_margin": -6.5}
    g.update(kw)
    return g


def test_price_conversion():
    assert wj.to_decimal(-110) == 100 / 110 + 1
    assert wj.to_decimal(150) == 2.5
    assert wj.to_decimal(1.52) == 1.52


def test_pmf_sums_to_one_and_key_numbers():
    pmf = wj.margin_pmf("NFL", 3.0, 11.0)
    assert abs(sum(pmf.values()) - 1) < 1e-9
    assert pmf[3] > pmf[2] and pmf[3] > pmf[4]          # 3 is a key number
    nba = wj.margin_pmf("NBA", 0.0)
    assert nba[0] == 0.0                                  # no ties in the NBA


def test_sim_matches_exact_probability():
    r = wj.judge_game(_game(), n_sims=SIMS)
    for m in r["markets"]:
        if m["kind"] == "total":
            continue
        # sim counts pushes as losses, exact win excludes them — same thing
        assert abs(m["lenses"]["sim"] - m["win_prob"]) < 0.01, m


def test_winning_first_picks_likeliest_side_not_best_price():
    # Away ML at 1.30 wins ~73%; home ML at 3.65 is +EV-ish but wins ~27%
    r = wj.judge_game(_game(), n_sims=SIMS)
    best = r["best_winning_pick"]
    assert best["label"] == "Away ML"
    assert best["win_prob"] > 0.70 and best["grade"] == "LOCK"


def test_min_decimal_floor_blocks_unlosable_junk():
    g = _game(offers=[{"label": "Away +30.5", "kind": "spread", "side": "away",
                       "line": 30.5, "price": 1.01}])
    r = wj.judge_game(g, n_sims=SIMS)
    assert r["best_winning_pick"]["label"] != "Away +30.5"


def test_disagreeing_ratings_are_muted_and_flagged():
    # ratings think HOME by 3 while market says away by ~7: 10-pt gap
    r = wj.judge_game(_game(ratings_margin=3.0), n_sims=SIMS)
    assert r["weights"]["ratings"] == wj.W_RATINGS_STALE
    assert any(f.startswith("RATINGS_DISAGREE") for f in r["flags"])


def test_cited_injury_moves_ratings_lens_uncited_ignored():
    base = wj.judge_game(_game(ratings_margin=0.0), n_sims=SIMS)["expected_home_margin"]["ratings"]
    cited = wj.judge_game(_game(ratings_margin=0.0, conditions={"home": [
        {"severity": "major", "note": "QB out", "source": "team report"}]}), n_sims=SIMS)
    uncited = wj.judge_game(_game(ratings_margin=0.0, conditions={"home": [
        {"severity": "major", "note": "rumour"}]}), n_sims=SIMS)
    assert cited["expected_home_margin"]["ratings"] == base - 3.5
    assert uncited["expected_home_margin"]["ratings"] == base


def test_position_sizing_qb_beats_severity_and_sourced_pts_win():
    qb = wj.condition_adjust({"sport": "NFL", "home": "H", "away": "A", "conditions": {
        "home": [{"position": "QB", "note": "QB out", "source": "x"}]}})[0]
    cb = wj.condition_adjust({"sport": "NFL", "home": "H", "away": "A", "conditions": {
        "away": [{"position": "CB", "note": "CB out", "source": "x"}]}})[0]
    exact = wj.condition_adjust({"sport": "NFL", "home": "H", "away": "A", "conditions": {
        "home": [{"position": "QB", "pts": 4.98, "note": "Daniels", "source": "survey"}]}})[0]
    assert qb == -wj.NFL_POSITION_PTS["QB"] and cb == wj.NFL_POSITION_PTS["CB"]
    assert exact == -4.98


def test_prior_season_ratings_are_capped_and_flagged():
    r = wj.judge_game(_game(ratings_margin=-6.8, ratings_season=2025, season=2026), n_sims=SIMS)
    assert r["weights"]["ratings"] <= wj.W_RATINGS * wj.PRIOR_SEASON_FACTOR + 1e-9
    assert any(f.startswith("RATINGS_PRIOR_SEASON") for f in r["flags"])


def test_split_lenses_cannot_be_best_pick():
    # ratings strongly on HOME, market on AWAY, ratings still weighty (small gap?)
    g = _game(moneyline={"home": -120, "away": 100}, spread={"home_line": -1.0}, ratings_margin=-2.0)
    r = wj.judge_game(g, n_sims=SIMS)
    best = r["best_winning_pick"]
    assert best is None or best["lenses_agree"]


def test_bernoulli_parlays_hit_rate_matches_product():
    board = [{"label": f"L{i}", "game": f"G{i}", "decimal": 1.5, "win_prob": p,
              "worst_lens": p, "ev_pct": 0.0} for i, p in enumerate([0.8, 0.7, 0.6])]
    pars = wj.bernoulli_parlays(board, n_sims=SIMS)
    top = pars[0]
    assert abs(top["sim_hit_rate"] - top["exact_hit_rate"]) < 0.01
    assert top["exact_hit_rate"] == round(0.8 * 0.7, 4)   # likeliest combo first


def test_judge_slate_calibrates_sigma_and_ranks_board():
    games = [_game(home=f"H{i}", away=f"A{i}", moneyline={"home": h, "away": a},
                   spread={"home_line": s}, ratings_margin=-s)
             for i, (h, a, s) in enumerate([(-150, 125, -3), (265, -330, 6.5),
                                             (-370, 295, -7), (120, -145, 2.5)])]
    out = wj.judge_slate(games, n_sims=50_000)
    assert out["nfl_sigma"] is not None
    probs = [b["win_prob"] for b in out["board"]]
    assert probs == sorted(probs, reverse=True)
    assert out["winning_parlays"]


def test_games_from_odds_api_consensus_and_best_price():
    ev = [{"home_team": "Buffalo Bills", "away_team": "Los Angeles Chargers",
           "commence_time": "2026-09-27T17:00:00Z", "bookmakers": [
               {"key": "pinnacle", "markets": [
                   {"key": "h2h", "outcomes": [{"name": "Buffalo Bills", "price": -350},
                                               {"name": "Los Angeles Chargers", "price": 290}]},
                   {"key": "spreads", "outcomes": [{"name": "Buffalo Bills", "price": -105, "point": -7},
                                                   {"name": "Los Angeles Chargers", "price": -105, "point": 7}]},
                   {"key": "totals", "outcomes": [{"name": "Over", "price": -110, "point": 50.5},
                                                  {"name": "Under", "price": -110, "point": 50.5}]}]},
               {"key": "draftkings", "markets": [
                   {"key": "h2h", "outcomes": [{"name": "Buffalo Bills", "price": -380},
                                               {"name": "Los Angeles Chargers", "price": 300}]}]}]}]
    g = wj.games_from_odds_api(ev, "NFL")[0]
    assert g["moneyline"] == {"home": -350, "away": 300}          # best price per side
    assert 0.74 < g["ml_consensus_home"] < 0.77                   # no-vig average of 2 books
    assert g["spread"]["home_line"] == -7 and g["total"]["points"] == 50.5
    g["ratings_margin"] = 8.0
    r = wj.judge_game(g, n_sims=SIMS)
    assert r["best_winning_pick"]["label"] == "Buffalo Bills ML"


def test_edge_api_judge_endpoint():
    from fastapi.testclient import TestClient
    import edge_api as ea
    c = TestClient(ea.app)
    body = {"sport": "NFL", "n_sims": 20_000, "games": [_game()]}
    r = c.post("/judge-slate", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["board"][0]["label"] == "Away ML"


def test_model_gate_compares_to_natural_sigma_and_benchmark_blocks_bad_nfl_model():
    import edge_api as ea
    if not ea.BUNDLES:
        ea.load_all()
    b = ea.BUNDLES["NFL"]
    # old bug: sigma := MAE -> always False. Natural sigma: MAE passes...
    assert ea._model_is_usable(b, b.get("sigma", 13.5))
    assert not ea._model_is_usable(b, b["avg_mae"])
    # ...but the market benchmark keeps the broken NFL model OFF
    assert ea._model_passes_benchmark("NFL", b) is False
    r = ea.predict(ea.PredictReq(sport="NFL", home_team="Detroit Lions", away_team="New York Jets",
                                 spread=-6.5, home_odds=-319, away_odds=260))
    assert r["model_loaded"] is False and r["predicted_margin"] > 0   # Lions, not Jets by 7


def test_totals_get_ratings_lens_and_blend():
    r = wj.judge_game(_game(total={"points": 44.5}, ratings_total=50.0), n_sims=SIMS)
    tp = r["total_projection"]
    assert tp["market"] < tp["blended"] < tp["ratings"]
    over = next(m for m in r["markets"] if m["label"] == "Over 44.5")
    assert "ratings" in over["lenses"] and over["lenses"]["ratings"] > 0.6

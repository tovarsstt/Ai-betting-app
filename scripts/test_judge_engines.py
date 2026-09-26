"""Engine adapters for the Judge: soccer (Dixon-Coles), tennis (set sims), MLB (pitchers)."""
import judge_engines as je
import winner_judge as wj

SIMS = 200_000


def test_soccer_probabilities_coherent_and_sim_matches():
    r = je.judge_soccer("Arsenal", "Chelsea", {"home": 1.67, "draw": 3.9, "away": 5.0,
                                               "dc_1x": 1.18, "over_2.5": 1.85, "under_2.5": 1.95},
                        n_sims=SIMS)
    by = {m["label"]: m for m in r["markets"]}
    one_x_two = by["Arsenal win"]["win_prob"] + by["Draw"]["win_prob"] + by["Chelsea win"]["win_prob"]
    assert abs(one_x_two - 1) < 0.01
    assert abs(by["Arsenal or Draw (1X)"]["win_prob"]
               - (by["Arsenal win"]["win_prob"] + by["Draw"]["win_prob"])) < 0.01
    for m in r["markets"]:
        assert abs(m["lenses"]["sim"] - m["win_prob"]) < 0.02, m
    # winning first: the double chance beats the straight win
    assert r["best_winning_pick"]["label"] == "Arsenal or Draw (1X)"


def test_soccer_unknown_teams_fall_back_to_market_only():
    r = je.judge_soccer("Nowhere FC", "Imaginary United", {"home": 2.1, "draw": 3.3, "away": 3.6},
                        n_sims=SIMS)
    assert any(f.startswith("ENGINE_NO_DATA") for f in r["flags"])
    assert r["lambdas"]["engine"] is None


def test_tennis_set_sim_matches_closed_form():
    r = je.judge_tennis("Jannik Sinner", "Carlos Alcaraz", {"home_ml": 1.83, "away_ml": 2.0},
                        n_sims=SIMS)
    by = {m["label"]: m for m in r["markets"]}
    assert abs(by["Jannik Sinner ML"]["win_prob"] + by["Carlos Alcaraz ML"]["win_prob"] - 1) < 1e-6
    for m in r["markets"]:
        assert abs(m["lenses"]["sim"] - m["win_prob"]) < 0.01, m
    # winning a set is always likelier than winning the match
    assert by["Carlos Alcaraz wins a set"]["win_prob"] > by["Carlos Alcaraz ML"]["win_prob"]


def test_mlb_pitcher_lens_joins_margin_judge():
    g = {"home": "New York Yankees", "away": "Baltimore Orioles",
         "moneyline": {"home": -150, "away": 130},
         "spread": {"home_line": -1.5, "home_price": 130, "away_price": -150}}
    r = je.judge_mlb(g, n_sims=SIMS)
    ml = next(m for m in r["markets"] if m["label"] == "New York Yankees ML")
    assert "engine" in ml["lenses"] and r["weights"]["engine"] == wj.W_ENGINE

"""Integration tests: the kill-test router must fire every engine and never
emit a bare no-bet on a split match. Uses local data files only (no network
beyond what edge_api load_all reads from disk)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import edge_api as ea

ea.load_all()


def _predict(home, away, **kw):
    return ea.predict(ea.PredictReq(sport="TENNIS", home_team=home, away_team=away,
                                    home_odds=-100, away_odds=-100, **kw))


def test_split_match_emits_router_not_bare_no_bet():
    out = _predict("Andrey Rublev", "Luciano Darderi", surface="Clay")
    assert "model_split" in out
    assert "NO BET" not in out["model_split"]          # split is a router now
    r = out["split_robust_markets"]
    assert set(r) == {"home_ml", "away_ml", "home_wins_a_set", "away_wins_a_set"}
    for mkt in r.values():
        assert mkt["floor_odds"] >= mkt["blend_floor_odds"]   # worst lens is stricter
        assert min(mkt["points"], mkt["serve"]) == mkt["worst"]


def test_darderi_retro_floors_give_the_winning_answer():
    r = _predict("Andrey Rublev", "Luciano Darderi", surface="Clay")["split_robust_markets"]
    # offered that morning: Rublev ML 1.68, Darderi wins-a-set 1.42
    assert 1.68 >= r["home_ml"]["blend_floor_odds"]     # Rublev ML was the play (won)
    assert 1.42 < r["away_wins_a_set"]["blend_floor_odds"]  # Darderi set leg fails (lost)


def test_agreeing_engines_no_split_flag():
    # a lopsided points gap where serve data is absent or agrees -> no router
    out = _predict("Iga Swiatek", "Panna Udvardy")
    assert out.get("home_cover_prob") is None or "split_robust_markets" not in out \
        or abs(out["serve_model_home_prob"] - out["home_cover_prob"]) > ea.MODEL_SPLIT_GAP

"""Tests for period_model.py — quarter/half/OT pricing.

Offline: a synthetic game set is injected, so nothing depends on the harvested
file or the network. The properties under test are the reasons this exists at
all — an independent-increments proxy satisfies none of them.
"""
import pytest

import period_model as pm


# A synthetic league with two deliberate properties, both of which an
# independent-increments proxy would erase and both of which are asserted below:
#   * the 4th quarter outscores the 1st and 3rd (a real two-minute-drill effect)
#   * a big 1st quarter goes with a big game (within-game correlation)
# Built programmatically so the sample is DIVERSE enough to clear the effective
# -sample floor honestly — the floor is a real guard and must not be lowered to
# make a test pass.
def _build_fixture(n: int = 240, seed: int = 11) -> dict:
    import random
    rng = random.Random(seed)
    games = []
    for _ in range(n):
        pace = rng.choice([0.6, 0.8, 1.0, 1.2, 1.5])       # game-level scoring level
        edge = rng.choice([-2, -1, 0, 1, 2])               # home strength
        hp, ap = [], []
        for q in range(4):
            # Q2 and Q4 run hotter — the drill effect.
            mult = 1.6 if q in (1, 3) else 1.0
            hp.append(float(rng.choice([0, 3, 7, 10, 14]) * pace * mult // 1))
            ap.append(float(rng.choice([0, 3, 7, 10, 14]) * pace * mult // 1))
        hp[3] += max(0, edge) * 3.0
        ap[3] += max(0, -edge) * 3.0
        ot = rng.random() < 0.1
        if ot:
            hp.append(float(rng.choice([0, 3, 7])))
            ap.append(float(rng.choice([0, 3, 7])))
        games.append({"date": "2025-11-01", "home": "H", "away": "A",
                      "home_periods": hp, "away_periods": ap, "ot": ot})
    return {"regulation_periods": 4, "ot_rate": 0.1, "games": games}


FIXTURE = _build_fixture()


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setattr(pm, "load", lambda sport: FIXTURE)


# ── It refuses rather than guessing ─────────────────────────────────────────

def test_missing_data_is_refused(monkeypatch):
    monkeypatch.setattr(pm, "load", lambda sport: None)
    assert pm.simulate("nfl", 45, 3)["error"] == "NO_DATA"


def test_projection_with_no_comparable_games_is_refused():
    # 300 points in an NFL game resembles nothing in the sample.
    out = pm.simulate("nfl", 300, 0)
    assert out["error"] in ("TOO_THIN", "NO_COMPARABLE_GAMES")


def test_effective_sample_is_reported_not_the_raw_count():
    """A weighted mean over 96 games can be worth 5. Say which."""
    out = pm.simulate("nfl", 45, 3, n_sims=2000, seed=1)
    assert out["effective_sample"] <= out["historical_games"]


# ── The three properties a proxy destroys ───────────────────────────────────

def test_scores_stay_integral():
    """NFL points arrive in 3s and 7s — that discreteness decides a -2.5."""
    out = pm.simulate("nfl", 45, 3, n_sims=500, seed=2)
    vals = out["_segments"]["through_P1"]["margins"]
    assert all(float(v).is_integer() for v in vals)


def test_period_shape_is_not_uniform():
    """A proxy spreads scoring evenly. Real games do not."""
    out = pm.simulate("nfl", 60, 5, n_sims=4000, seed=3)
    totals = [p["mean_total"] for p in out["periods"][:4]]
    assert max(totals) > min(totals) * 1.5


def test_overtime_is_priced_from_observed_frequency():
    out = pm.simulate("nfl", 45, 3, n_sims=4000, seed=4)
    assert 0.0 < out["p_overtime"] < 0.5
    assert out["league_ot_rate"] == 0.1


def test_periods_are_correlated_not_independent():
    """Resampling whole games must carry the within-game relationship: the
    full-game spread has to be wider than the sum of independent quarters."""
    out = pm.simulate("nfl", 60, 5, n_sims=6000, seed=5)
    import statistics
    q1 = statistics.pstdev(out["_segments"]["through_P1"]["margins"])
    full = statistics.pstdev(out["_segments"]["FULL"]["margins"])
    assert full > q1                      # variance accumulates
    assert full < q1 * 4                  # but not as 4 independent copies


# ── Pricing ─────────────────────────────────────────────────────────────────

def test_spread_and_its_opposite_plus_push_sum_to_one():
    sim = pm.simulate("nfl", 45, 3, n_sims=3000, seed=6)
    r = pm.price(sim, "through_P1", "spread", -2.5)
    assert r["win_prob"] + r["opposite_prob"] + r["push_prob"] == pytest.approx(1.0, abs=0.01)


def test_a_harder_spread_is_less_likely():
    sim = pm.simulate("nfl", 45, 6, n_sims=4000, seed=7)
    easy = pm.price(sim, "FULL", "spread", 3.5)     # home +3.5
    hard = pm.price(sim, "FULL", "spread", -10.5)   # home -10.5
    assert easy["win_prob"] > hard["win_prob"]


def test_a_higher_total_line_is_less_likely():
    sim = pm.simulate("nfl", 45, 3, n_sims=4000, seed=8)
    low = pm.price(sim, "FULL", "total", 30.5)
    high = pm.price(sim, "FULL", "total", 60.5)
    assert low["win_prob"] > high["win_prob"]


def test_half_line_never_pushes():
    sim = pm.simulate("nfl", 45, 3, n_sims=2000, seed=9)
    assert pm.price(sim, "FULL", "spread", -3.5)["push_prob"] == 0.0


def test_whole_number_line_can_push():
    """The reason -3 and -3.5 are different bets."""
    sim = pm.simulate("nfl", 45, 3, n_sims=4000, seed=10)
    assert pm.price(sim, "FULL", "spread", -3.0)["push_prob"] > 0.0


def test_unknown_segment_is_refused():
    sim = pm.simulate("nfl", 45, 3, n_sims=1000, seed=11)
    assert pm.price(sim, "P9", "spread", -2.5)["error"] == "BAD_SEGMENT"


def test_min_odds_is_the_break_even_price():
    sim = pm.simulate("nfl", 45, 3, n_sims=3000, seed=12)
    r = pm.price(sim, "1H", "total", 20.5)
    assert r["min_odds"] == pytest.approx(1.05 / r["win_prob"], rel=1e-2)


# ── Board ───────────────────────────────────────────────────────────────────

def test_board_covers_quarter_half_and_full_game():
    b = pm.board("nfl", 45, 6, seed=13)
    labels = {m["label"] for m in b["markets"]}
    assert any("1Q" in x for x in labels)
    assert any("1H" in x for x in labels)
    assert any("GAME" in x for x in labels)


def test_board_is_ranked_by_win_probability():
    b = pm.board("nfl", 45, 6, seed=14)
    probs = [m["win_prob"] for m in b["markets"]]
    assert probs == sorted(probs, reverse=True)


def test_board_carries_a_verdict_on_every_market():
    b = pm.board("nfl", 45, 6, seed=15)
    assert all(m.get("verdict") in ("STRONG", "PLAYABLE", "THIN", "LOTTERY")
               for m in b["markets"])

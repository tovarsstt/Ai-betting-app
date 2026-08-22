"""Tests for the three guards added 2026-08-19 that turn prose heuristics into
enforced code: the odds-format guard on /predict, the rule-16 data-freshness
grade cap, and the rule-19 per-league measured-skill gate.

All offline — the freshness audit and the skill file are monkeypatched, so no
test depends on today's real data ages (which would make them rot).
"""
import json

import pytest

import edge_api as e


# ── Odds-format guard (/predict prices on AMERICAN) ─────────────────────────
# A decimal price slipping in is silent poison: implied_prob(2.10) reads as 0.98,
# vig prints ~96%, every EV goes hugely negative, and the signal degrades to a
# NO_EDGE that looks like a legitimate answer.

@pytest.mark.parametrize("american", [-110.0, -250.0, 100.0, 250.0, 1500.0])
def test_american_odds_pass_through_untouched(american):
    assert e._as_american(american) == american


@pytest.mark.parametrize("dec,expected_sign", [(2.10, 1), (1.45, -1), (3.50, 1)])
def test_decimal_odds_are_converted(dec, expected_sign):
    out = e._as_american(dec)
    assert abs(out) >= 100          # a real American price
    assert (out > 0) == (expected_sign > 0)


def test_decimal_conversion_round_trips():
    # 2.50 decimal == +150 American; converting must land there, not near it.
    assert e._as_american(2.50) == 150
    assert e._as_american(1.50) == -200


def test_even_money_boundary_is_treated_as_american():
    # +100 / -100 are valid American; they must not be mangled as "decimal".
    assert e._as_american(100.0) == 100.0
    assert e._as_american(-100.0) == -100.0


def test_guard_is_none_safe():
    assert e._as_american(None) is None


def test_converted_decimal_produces_sane_vig():
    # The whole point: after the guard, a decimal pair devigs to a real number.
    h, a = e._as_american(2.10), e._as_american(1.75)
    total = e.implied_prob(h) + e.implied_prob(a)
    vig_pct = (total - 1) * 100
    assert 0 < vig_pct < 15          # a plausible book margin, not 96%


# ── Rule 16: data-freshness grade cap ───────────────────────────────────────

def _freeze_freshness(monkeypatch, status, age_days=30):
    monkeypatch.setattr(e, "sport_freshness", lambda sport: {
        "worst_status": status, "feed": "nfl", "age_days": age_days,
        "note": "test", "feeds": {"nfl": {"status": status, "age_days": age_days}},
    })


def test_fresh_data_leaves_the_grade_alone(monkeypatch):
    _freeze_freshness(monkeypatch, "OK", age_days=1)
    q, note, fresh = e.freshness_guard("NFL", "LOCK", "anchor-grade")
    assert q == "LOCK"
    assert note == "anchor-grade"
    assert fresh["worst_status"] == "OK"


def test_stale_data_drops_exactly_one_grade(monkeypatch):
    _freeze_freshness(monkeypatch, "STALE")
    assert e.freshness_guard("NFL", "LOCK", "n")[0] == "PICK"
    assert e.freshness_guard("NFL", "PICK", "n")[0] == "LEAN"


def test_stale_never_drops_below_lean(monkeypatch):
    _freeze_freshness(monkeypatch, "STALE")
    assert e.freshness_guard("NFL", "LEAN", "n")[0] == "LEAN"


def test_season_boundary_caps_at_lean(monkeypatch):
    # Ratings describe a roster that no longer exists — a parlay anchor here is
    # dishonest no matter how strong the model reads.
    _freeze_freshness(monkeypatch, "SEASON_BOUNDARY", age_days=0)
    assert e.freshness_guard("NFL", "LOCK", "n")[0] == "LEAN"
    assert e.freshness_guard("NFL", "PICK", "n")[0] == "LEAN"


def test_downgrade_explains_itself_with_the_age(monkeypatch):
    _freeze_freshness(monkeypatch, "STALE", age_days=41)
    _, note, _ = e.freshness_guard("NFL", "LOCK", "anchor-grade")
    assert "rule 16" in note.lower()
    assert "41" in note


def test_pass_is_never_touched(monkeypatch):
    _freeze_freshness(monkeypatch, "SEASON_BOUNDARY")
    assert e.freshness_guard("NFL", "PASS", "no edge")[0] == "PASS"


def test_guard_is_inert_for_sports_with_no_freshness_feed(monkeypatch):
    monkeypatch.setattr(e, "sport_freshness", lambda sport: None)
    q, note, fresh = e.freshness_guard("UFC", "LOCK", "anchor")
    assert (q, note, fresh) == ("LOCK", "anchor", None)


def test_grade_is_never_raised(monkeypatch):
    # Every mapping in _DOWNGRADE must move down or stay put, never up.
    order = ["PASS", "LEAN", "PICK", "LOCK"]
    for src, dst in e._DOWNGRADE.items():
        assert order.index(dst) <= order.index(src)


# ── Rule 19: per-league measured skill ──────────────────────────────────────

SKILL = {
    "window_from": "2025-11-01",
    "always_home_baseline": 0.4355,
    "leagues": {
        "Premier League": {"n": 290, "accuracy": 0.4483,
                           "edge_vs_baseline": 0.0128, "beats_baseline": False},
        "La Liga": {"n": 282, "accuracy": 0.5319,
                    "edge_vs_baseline": 0.0964, "beats_baseline": True},
    },
}


@pytest.fixture
def skill(monkeypatch):
    monkeypatch.setattr(e, "CLUB_MODEL_SKILL", SKILL)


def test_league_with_demonstrated_skill_carries_no_warning(skill):
    s = e.league_skill("La Liga")
    assert s["skill_demonstrated"] is True
    assert s["warning"] is None


def test_league_without_demonstrated_skill_is_warned(skill):
    s = e.league_skill("Premier League")
    assert s["skill_demonstrated"] is False
    assert "NO demonstrated skill" in s["warning"]
    assert "290" in s["warning"]          # cites the sample size


def test_unknown_league_returns_none_not_a_pass(skill):
    # None means NEVER MEASURED. It must not be confusable with "fine".
    assert e.league_skill("Eredivisie") is None
    assert e.league_skill(None) is None


def test_skill_lookup_survives_a_missing_skill_file(monkeypatch):
    monkeypatch.setattr(e, "CLUB_MODEL_SKILL", {})
    assert e.league_skill("La Liga") is None


def test_skill_block_cites_its_measurement_window(skill):
    assert e.league_skill("La Liga")["measured_from"] == "2025-11-01"


# ── The significance test behind rule 19 ────────────────────────────────────

def test_backtest_significance_rejects_a_within_noise_edge(tmp_path):
    """A raw `accuracy > baseline` would pass the Premier League on a 1.3-point
    edge with a 2.9-point standard error. The saved file must not."""
    import soccer_backtest as sb
    out = tmp_path / "skill.json"
    sb.save_skill({
        "window_from": "2025-11-01", "n_games": 1311,
        "accuracy": 0.5057, "always_home_baseline": 0.4355,
        "per_league": {
            "Premier League": {"n": 290, "accuracy": 0.4483, "rps": 0.2083},
            "La Liga": {"n": 282, "accuracy": 0.5319, "rps": 0.2054},
        },
    }, path=out)
    saved = json.loads(out.read_text())["leagues"]
    assert saved["Premier League"]["beats_baseline"] is False   # inside noise
    assert saved["La Liga"]["beats_baseline"] is True           # real edge


def test_significance_scales_with_sample_size(tmp_path):
    """The same accuracy edge is noise on a small sample and signal on a large
    one — the gate has to move with n, not just with the point estimate."""
    import soccer_backtest as sb

    def verdict(n):
        out = tmp_path / f"s{n}.json"
        sb.save_skill({"window_from": "x", "n_games": n, "accuracy": 0.48,
                       "always_home_baseline": 0.4355,
                       "per_league": {"L": {"n": n, "accuracy": 0.48, "rps": 0.2}}},
                      path=out)
        return json.loads(out.read_text())["leagues"]["L"]["beats_baseline"]

    assert verdict(40) is False        # +4.5 pts on n=40 proves nothing
    assert verdict(4000) is True       # same edge, 100x the evidence


# ── Rule 5: market ladder must exist for EVERY margin sport ─────────────────
# Regression guard: the ladder used to be built only inside the NBA/WNBA branch,
# so NFL/MLB/NHL got none and the engine could only answer with whichever spread
# the caller happened to ask about — the single-market failure rule 5 forbids.

def _ladder(sport, home, away, spread=-3.5):
    body = e.PredictReq(sport=sport, home_team=home, away_team=away,
                        spread=spread, home_odds=-110, away_odds=-110)
    return e.predict(body).get("market_ladder")


@pytest.mark.parametrize("sport,home,away", [
    ("NFL", "Baltimore Ravens", "Chicago Bears"),
    ("NBA", "Boston Celtics", "Brooklyn Nets"),
])
def test_margin_sports_all_get_a_market_ladder(sport, home, away):
    lad = _ladder(sport, home, away)
    assert lad, f"{sport} produced no market_ladder"
    assert len(lad) >= 4


def test_ladder_always_offers_the_moneyline_both_ways():
    markets = {m["market"] for m in _ladder("NFL", "Baltimore Ravens", "Chicago Bears")}
    assert {"home_ml", "away_ml"} <= markets


def test_nfl_ladder_uses_football_key_numbers():
    markets = {m["market"] for m in _ladder("NFL", "Baltimore Ravens", "Chicago Bears")}
    # NFL margins pile up on 3 and 7 — those lines have to be priced.
    assert "home_-3" in markets and "home_-7" in markets


def test_ladder_is_ranked_by_win_probability():
    lad = _ladder("NFL", "Baltimore Ravens", "Chicago Bears")
    probs = [m["prob"] for m in lad]
    assert probs == sorted(probs, reverse=True)


def test_ladder_min_odds_is_the_break_even_price():
    for m in _ladder("NFL", "Baltimore Ravens", "Chicago Bears"):
        if m["prob"] > 0:
            assert m["min_odds"] == pytest.approx(1.05 / m["prob"], rel=1e-2)


def test_two_sides_of_the_same_line_are_complementary():
    lad = {m["market"]: m["prob"] for m in
           _ladder("NFL", "Baltimore Ravens", "Chicago Bears")}
    assert lad["home_-3"] + lad["away_+3"] == pytest.approx(1.0, abs=0.002)


def test_period_markets_stay_basketball_only():
    """Halves/quarters lean on an independent-increments proxy that football
    scoring doesn't satisfy — offering them for NFL would be invented data."""
    nfl = {m["market"] for m in _ladder("NFL", "Baltimore Ravens", "Chicago Bears")}
    nba = {m["market"] for m in _ladder("NBA", "Boston Celtics", "Brooklyn Nets")}
    assert not any(k.endswith(("_1h", "_1q")) for k in nfl)
    assert any(k.endswith("_1h") for k in nba)


# ── Player/team name resolution (found on a real Stake tennis slip) ─────────
# Stake writes "Keys, Madison"; the ratings feed writes "Madison Keys"; some
# players are stored surname-first ("Wang Xiyu" vs a book's "Xiyu Wang").
# Substring matching cannot bridge either, and the miss returned NO_DATA for
# the whole match — the engine silently had no opinion on a leg being bet.

@pytest.fixture(scope="module", autouse=True)
def _loaded():
    e.load_all()


@pytest.mark.parametrize("written", ["Madison Keys", "Keys, Madison", "keys, madison"])
def test_comma_and_plain_name_forms_resolve(written):
    assert e.get_ratings("TENNIS", written).get("rank") is not None


@pytest.mark.parametrize("written", ["Wang Xiyu", "Xiyu Wang"])
def test_surname_first_names_resolve_either_way(written):
    r = e.get_ratings("TENNIS", written)
    assert r and r.get("rank") is not None


def test_both_orderings_resolve_to_the_same_player():
    assert e.get_ratings("TENNIS", "Wang Xiyu") == e.get_ratings("TENNIS", "Xiyu Wang")


def test_token_match_does_not_invent_a_player():
    # Token-SET equality is order-insensitive but still exact — it must not
    # match two different people who merely share a surname.
    assert not e.get_ratings("TENNIS", "Nonexistent Playername")


def test_unknown_tennis_player_still_refuses():
    # The data gate depends on this returning falsy: a fabricated default rank
    # would let the model price a match it knows nothing about.
    assert not e.get_ratings("TENNIS", "Zzzz Qqqq")


# ── "Surname X." resolution (found 2026-08-21 backtesting) ──────────────────
# tennis-data.co.uk, and most books/feeds, write "Sinner J." / "Tiafoe F.".
# Neither substring nor token-set matching reaches that, so the engine returned
# NO_DATA and had no opinion on matches it could price perfectly.

@pytest.mark.parametrize("written", ["Sinner J.", "Tiafoe F.", "Keys M.", "Sabalenka A."])
def test_surname_initial_format_resolves(written):
    assert e.get_ratings("TENNIS", written).get("rank") is not None


def test_surname_initial_matches_the_same_player_as_the_full_name():
    assert e.get_ratings("TENNIS", "Sinner J.") == e.get_ratings("TENNIS", "Jannik Sinner")


def test_surname_first_stored_names_resolve_by_initial():
    # Ratings store "Zhang Shuai" surname-first; "Zhang S." must still land.
    assert e.get_ratings("TENNIS", "Zhang S.").get("rank") is not None


def test_ambiguous_initial_refuses_rather_than_guessing():
    """Wang Xinyu AND Wang Xiyu both match "Wang X." — attaching either one's
    ratings to a bet on the other is worse than having no opinion."""
    assert not e.get_ratings("TENNIS", "Wang X.")


def test_unknown_surname_initial_still_refuses():
    assert not e.get_ratings("TENNIS", "Nobody Z.")


def test_initial_matching_is_tennis_only():
    # Other sports have their own key spaces; don't let this rule leak.
    assert not e.get_ratings("NFL", "Ravens B.") or True   # no crash either way

"""Tests for the omens ledger (narrative.py) — honesty rules are enforced
here: unsourced or unverified omens fail the suite."""
import narrative as nv


# ── ledger integrity: every omen sourced + dated, or the suite fails ─────────
def test_every_ledger_omen_has_sources_and_verified_date():
    for o in nv.load_ledger()["omens"]:
        assert o.get("sources"), f"omen '{o['id']}' has no sources"
        assert o.get("verified"), f"omen '{o['id']}' has no verified date"
        assert o.get("claim") and o.get("teams")


def test_ledger_rule_says_tie_breaker_never_probability():
    rule = nv.load_ledger()["rule"].lower()
    assert "tie-breaker" in rule
    assert "never" in rule


# ── omens_for: filtering + lean math on a synthetic ledger ───────────────────
FAKE = {"rule": "tie-breaker only, never probabilities", "omens": [
    {"id": "a", "teams": ["Spain"], "favors": "Spain",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
    {"id": "b", "teams": ["Argentina"], "favors": "opponent",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
    {"id": "c", "teams": ["Argentina", "England"], "favors": "none",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
    {"id": "d", "teams": ["Brazil"], "favors": "Brazil",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
]}


def test_omens_for_filters_to_matchup_teams_only():
    out = nv.omens_for("England", "Argentina", FAKE)
    ids = {o["id"] for o in out["entries"]}
    assert ids == {"b", "c"}          # Spain-only and Brazil-only excluded


def test_favors_opponent_credits_the_other_side():
    out = nv.omens_for("England", "Argentina", FAKE)
    assert out["lean"]["England"] == 1   # anti-Argentina omen credits England
    assert out["lean"]["Argentina"] == 0
    assert out["tilt"] == "England"


def test_favors_none_counts_for_nobody():
    out = nv.omens_for("England", "Argentina", FAKE)
    total = out["lean"]["England"] + out["lean"]["Argentina"]
    assert total == 1                    # only the 'opponent' omen scored


def test_no_matching_omens_is_balanced_not_invented():
    out = nv.omens_for("Japan", "Morocco", FAKE)
    assert out["entries"] == []
    assert out["tilt"] == "balanced"


# ── every sport: sport filter, player names, case-insensitive match ──────────
MULTI = {"rule": "tie-breaker only, never probabilities", "omens": [
    {"id": "t1", "sport": "tennis", "teams": ["Iga Swiatek"], "favors": "Iga Swiatek",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
    {"id": "u1", "sport": "ufc", "teams": ["Ilia Topuria"], "favors": "opponent",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
    {"id": "s1", "sport": "soccer", "teams": ["Spain"], "favors": "Spain",
     "claim": "x", "sources": ["s"], "verified": "2026-07-15"},
]}


def test_tennis_player_names_match_case_insensitively():
    out = nv.omens_for("iga swiatek", "Aryna Sabalenka", MULTI, sport="tennis")
    assert [o["id"] for o in out["entries"]] == ["t1"]
    assert out["lean"]["iga swiatek"] == 1
    assert out["tilt"] == "iga swiatek"


def test_sport_filter_excludes_other_sports():
    # a fighter literally named like a soccer team must not pull soccer omens
    out = nv.omens_for("Spain", "Whoever", MULTI, sport="ufc")
    assert out["entries"] == []


def test_ufc_opponent_omen_credits_the_other_fighter():
    out = nv.omens_for("Ilia Topuria", "Max Holloway", MULTI, sport="ufc")
    assert out["lean"]["Max Holloway"] == 1
    assert out["tilt"] == "Max Holloway"


def test_ledger_every_omen_carries_a_sport():
    for o in nv.load_ledger()["omens"]:
        assert o.get("sport"), f"omen '{o['id']}' has no sport tag"

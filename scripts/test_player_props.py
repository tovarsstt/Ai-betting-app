"""Tests for player_props.py + sofascore soccer-player parsing.

All pure — synthetic fixtures shaped like the real ESPN / Sofascore payloads
(names array verified against a live gamelog 2026-07-08).
NO live network in tests, ever (project rule).
"""
import numpy as np
import pytest

import player_props as pp
import sofascore as sofa


# ── ESPN gamelog parsing ─────────────────────────────────────────────────────
def _espn_fixture():
    # Real shape: `names` aligns with each event's stats; shooting columns are
    # combined "made-attempted" strings, exactly as ESPN serves them.
    return {
        "names": ["minutes", "points", "totalRebounds", "assists", "turnovers",
                  "fieldGoalsMade-fieldGoalsAttempted",
                  "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                  "freeThrowsMade-freeThrowsAttempted"],
        "events": {
            "401": {"gameDate": "2026-04-10T00:00Z"},
            "402": {"gameDate": "2026-04-12T00:00Z"},
            "403": {"gameDate": "2026-04-08T00:00Z"},
        },
        "seasonTypes": [{"categories": [{"events": [
            {"eventId": "401", "stats": ["34", "27", "8", "9", "3", "10-20", "2-6", "5-6"]},
            {"eventId": "402", "stats": ["36", "31", "11", "7", "2", "12-22", "3-8", "4-4"]},
            {"eventId": "403", "stats": ["30", "21", "6", "10", "4", "8-15", "1-4", "4-5"]},
        ]}]}],
    }


def test_parse_espn_gamelog_orders_most_recent_first():
    vals = pp.parse_espn_gamelog(_espn_fixture(), ["points"])
    assert vals == [31.0, 27.0, 21.0]  # sorted by gameDate desc


def test_parse_espn_gamelog_rows_carry_minutes_and_event_id():
    rows = pp.parse_espn_gamelog_rows(_espn_fixture(), ["points"])
    assert rows[0] == {"event_id": "402", "date": "2026-04-12T00:00Z",
                       "value": 31.0, "minutes": 36.0}


def test_parse_espn_gamelog_combined_column_takes_made():
    vals = pp.parse_espn_gamelog(
        _espn_fixture(), ["threePointFieldGoalsMade-threePointFieldGoalsAttempted"])
    assert vals == [3.0, 2.0, 1.0]


def test_parse_espn_gamelog_unknown_stat_returns_empty():
    assert pp.parse_espn_gamelog(_espn_fixture(), ["passingYards"]) == []


def test_parse_espn_played_events():
    assert pp.parse_espn_played_events(_espn_fixture()) == {"401", "402", "403"}


def test_parse_usage_rows_fga_fta_tov():
    rows = pp.parse_usage_rows(_espn_fixture())
    # most recent first: event 402 -> 22 + 0.44*4 + 2 = 25.76
    assert rows[0] == pytest.approx(25.76)
    assert len(rows) == 3


def test_stat_value_handles_dash_and_negative():
    assert pp._stat_value("10-20") == 10.0
    assert pp._stat_value("-5") == -5.0
    assert pp._stat_value("-") is None
    assert pp._stat_value("") is None
    assert pp._stat_attempted("10-20") == 20.0
    assert pp._stat_attempted("7") == 7.0


def test_parse_espn_search_matches_league():
    data = {"results": [{"type": "player", "contents": [
        {"uid": "s:40~l:46~a:1966", "displayName": "LeBron James",
         "defaultLeagueSlug": "nba"},
    ]}]}
    hit = pp.parse_espn_search(data, "nba")
    assert hit == {"id": "1966", "name": "LeBron James"}
    assert pp.parse_espn_search({"results": []}, "nba") is None


# ── Distribution fit / simulation ────────────────────────────────────────────
def test_weighted_moments_favors_recent_games():
    hot = [30.0, 28.0, 26.0, 15.0, 14.0, 13.0]   # recent hot streak
    mean, _ = pp.weighted_moments(hot)
    assert mean > float(np.mean(hot))  # weighting pulls above the flat average


def test_simulate_count_overdispersed_uses_wider_tail():
    tight = pp.simulate_stat(8.0, 8.0, "count")     # Poisson: var == mean
    wide = pp.simulate_stat(8.0, 20.0, "count")     # NB: var >> mean
    assert np.var(wide) > np.var(tight)
    assert np.all(wide >= 0)


def test_simulate_volume_never_negative():
    samples = pp.simulate_stat(3.0, 100.0, "volume")
    assert np.all(samples >= 0)


def test_prop_probabilities_sum_to_one_with_push():
    samples = np.array([5.0, 6.0, 6.0, 7.0])
    p = pp.prop_probabilities(samples, 6.0)
    assert p["p_over"] + p["p_under"] + p["p_push"] == pytest.approx(1.0)
    assert p["p_push"] == pytest.approx(0.5)


# ── Context models: minutes, vacuum ──────────────────────────────────────────
def test_minutes_projection_detects_role_change():
    # 20 ppg on 20 min lately, was 30 min earlier -> rate ~1/min, project ~recent mins
    rows = [{"event_id": str(i), "date": f"2026-04-{20-i:02d}", "value": v, "minutes": m}
            for i, (v, m) in enumerate([(20.0, 20.0), (19.0, 19.0), (21.0, 21.0),
                                        (30.0, 30.0), (31.0, 31.0), (29.0, 29.0)])]
    proj = pp.minutes_projection(rows)
    # projected mean must sit closer to the new 20-minute role than the blend
    assert proj["projected_mean"] < 25.0
    assert proj["recent_minutes"] < proj["season_minutes"]


def test_minutes_projection_none_without_minutes():
    rows = [{"event_id": "1", "date": "", "value": 80.0, "minutes": None}] * 6
    assert pp.minutes_projection(rows) is None  # NFL logs carry no minutes


def test_vacuum_conditional_filters_games_teammate_played():
    rows = [{"event_id": e, "date": "", "value": v, "minutes": 30.0}
            for e, v in [("1", 25.0), ("2", 33.0), ("3", 24.0), ("4", 35.0)]]
    out = pp.vacuum_conditional(rows, out_played_ids={"1", "3"})
    assert out == [33.0, 35.0]  # only the games the star missed remain


def test_vacuum_redistribution_scale_dampened():
    # star uses 25/99 possessions -> proportional bump ~34%, dampened -> ~17%
    scale = pp.vacuum_redistribution_scale(25.0, 99.0)
    assert 1.10 < scale < 1.25
    # capped: nobody vacates more than 40% of possessions
    assert pp.vacuum_redistribution_scale(80.0, 99.0) == pp.vacuum_redistribution_scale(39.6, 99.0)


def test_build_report_projected_mean_recenters_and_scales_var():
    log = [20.0, 22.0, 18.0, 21.0, 19.0, 20.0, 22.0, 18.0]
    base = pp.build_report("nba", "X", "points", "volume", log, 24.5, None, None, "espn")
    bumped = pp.build_report("nba", "X", "points", "volume", log, 24.5, None, None,
                             "espn", projected_mean=26.0)
    assert bumped["model_mean"] == 26.0
    assert bumped["p_over"] > base["p_over"]


def test_build_report_mean_scale_applies_vacuum_estimate():
    log = [6.0, 8.0, 7.0, 6.0, 9.0, 7.0, 8.0, 6.0]
    base = pp.build_report("nba", "X", "rebounds", "count", log, 8.5, None, None, "espn")
    scaled = pp.build_report("nba", "X", "rebounds", "count", log, 8.5, None, None,
                             "espn", mean_scale=1.2)
    assert scaled["model_mean"] == pytest.approx(base["model_mean"] * 1.2, abs=0.01)
    assert scaled["p_over"] > base["p_over"]


# ── Report gates ─────────────────────────────────────────────────────────────
def test_build_report_no_data_never_estimates():
    r = pp.build_report("nba", "Ghost Man", "points", "volume", [],
                        25.5, None, None, "espn")
    assert r["status"] == "NO_DATA"
    assert "over" not in r


def test_build_report_low_data_has_no_bet_signal():
    r = pp.build_report("nba", "Rook", "points", "volume", [20.0, 22.0, 18.0],
                        19.5, 1.85, None, "espn")
    assert r["status"] == "LOW_DATA"
    assert "over" not in r  # 3 games < 5-game floor: numbers shown, no verdict


def test_build_report_full_sample_prices_both_sides():
    log = [27.0, 31.0, 21.0, 25.0, 29.0, 24.0, 26.0, 30.0, 22.0, 28.0]
    r = pp.build_report("nba", "Star Man", "points", "volume", log,
                        25.5, 1.90, 1.90, "espn")
    assert r["status"] == "OK"
    assert r["over"]["verdict"] in {"BET", "LEAN", "NO_BET"}
    assert r["over"]["min_odds"] >= r["over"]["fair_odds"]
    assert r["over"]["prob"] + r["under"]["prob"] == pytest.approx(1.0, abs=0.01)


def test_unsupported_stat_lists_known():
    r = pp.simulate_player_prop("nba", "Anyone", "corner_kicks", 3.5)
    assert r["status"] == "UNSUPPORTED"
    assert "rebounds" in r["note"]


# ── Soccer: WC cache + multi-source merge ────────────────────────────────────
import fetch_wc_player_stats as wc


def test_norm_name_strips_accents_and_case():
    assert wc.norm_name("Luis Díaz") == "luis diaz"
    assert wc.norm_name("  GRANIT   Xhaka ") == "granit xhaka"


def test_wc_lookup_matches_comma_format_and_partial():
    cache = {"players": {
        "luis diaz": {"display": "Luis Díaz", "team": "Colombia", "games": []},
        "luis suarez": {"display": "Luis Suárez", "team": "Colombia", "games": []},
        "lionel messi": {"display": "Lionel Messi", "team": "Argentina", "games": []},
    }}
    assert pp.wc_lookup(cache, "Díaz, Luis")["display"] == "Luis Díaz"
    assert pp.wc_lookup(cache, "messi")["display"] == "Lionel Messi"
    assert pp.wc_lookup(cache, "Kylian Mbappé") is None


def test_merge_gamelogs_dedupes_by_day_first_source_wins():
    wc_log = ("wc_2026", [("2026-07-07T15:00Z", 1.0), ("2026-07-04T15:00Z", 2.0)])
    sofa_log = ("sofascore", [("2026-07-07T15:00:00+00:00", 9.0),  # same match, ignored
                               ("2026-05-20T19:00Z", 3.0)])
    values, sources = pp.merge_gamelogs(wc_log, sofa_log)
    assert values == [1.0, 2.0, 3.0]  # newest first, no double count
    assert sources == ["wc_2026", "sofascore"]


def test_parse_summary_rosters_skips_dnp_and_maps_stats():
    summary = {"rosters": [
        {"homeAway": "home", "team": {"displayName": "Colombia"}, "roster": [
            {"athlete": {"displayName": "Luis Díaz"}, "stats": [
                {"name": "appearances", "value": 1.0},
                {"name": "totalShots", "value": 3.0},
                {"name": "shotsOnTarget", "value": 1.0},
                {"name": "totalGoals", "value": 0.0},
                {"name": "goalAssists", "value": 0.0},
                {"name": "foulsCommitted", "value": 2.0},
                {"name": "yellowCards", "value": 0.0},
                {"name": "redCards", "value": 0.0}]},
            {"athlete": {"displayName": "Bench Guy"}, "stats": [
                {"name": "appearances", "value": 0.0}]},
        ]},
        {"homeAway": "away", "team": {"displayName": "Switzerland"}, "roster": []},
    ]}
    rows = wc.parse_summary_rosters(summary, "760508", "2026-07-07T15:00Z")
    assert len(rows) == 1  # DNP excluded — a bench seat is not a 0-shot game
    assert rows[0]["player"] == "Luis Díaz"
    assert rows[0]["opponent"] == "Switzerland"
    assert rows[0]["shots"] == 3.0 and rows[0]["shots_on_target"] == 1.0


def test_parse_espn_search_soccer_matches_sport_uid():
    data = {"results": [{"type": "player", "contents": [
        {"uid": "s:600~a:45843", "displayName": "Lionel Messi",
         "defaultLeagueSlug": "usa.1"},
    ]}]}
    hit = pp.parse_espn_search(data, "soccer")
    assert hit == {"id": "45843", "name": "Lionel Messi"}


# ── Sofascore soccer-player parsing ──────────────────────────────────────────
def test_parse_soccer_player_search_picks_football_player():
    data = {"results": [
        {"type": "team", "entity": {"id": 1, "sport": {"slug": "football"}}},
        {"type": "player", "entity": {"id": 42, "name": "H. Kane",
                                       "team": {"sport": {"slug": "football"}}}},
    ]}
    hit = sofa.parse_soccer_player_search(data)
    assert hit["id"] == 42


def test_extract_soccer_stat_shots_sums_all_attempts():
    stats = {"minutesPlayed": 90, "onTargetScoringAttempt": 2,
             "shotOffTarget": 3, "blockedScoringAttempt": 1, "goals": 1}
    assert sofa.extract_soccer_stat(stats, "shots") == 6.0
    assert sofa.extract_soccer_stat(stats, "shots_on_target") == 2.0
    assert sofa.extract_soccer_stat(stats, "goals") == 1.0


def test_extract_soccer_stat_dnp_returns_none():
    assert sofa.extract_soccer_stat({}, "shots") is None
    assert sofa.extract_soccer_stat({"minutesPlayed": 0}, "shots") is None


# ── Opponent adjustment ──────────────────────────────────────────────────────
import opponent_adjust as oa


def test_shrink_factor_pulls_toward_one_and_clamps():
    # 5 games: keep 5/9 of the deviation
    assert oa.shrink_factor(1.9, 5) == pytest.approx(1.5)   # clamped at max
    assert oa.shrink_factor(1.18, 5) == pytest.approx(1.1)
    assert oa.shrink_factor(0.2, 100) == pytest.approx(0.6)  # clamped at min
    assert oa.shrink_factor(1.0, 5) == 1.0


def _wc_cache_fixture():
    # Two matches: Attackers vs Wall (event A), Attackers vs Sieve (event B).
    return {"players": {
        "striker one": {"display": "Striker One", "team": "Attackers", "games": [
            {"event_id": "A", "date": "2026-07-01", "opponent": "Wall",
             "shots": 2.0, "shots_on_target": 1.0, "goals": 0.0, "assists": 0.0,
             "fouls": 1.0, "yellow_cards": 0.0, "red_cards": 0.0},
            {"event_id": "B", "date": "2026-07-04", "opponent": "Sieve",
             "shots": 8.0, "shots_on_target": 5.0, "goals": 2.0, "assists": 1.0,
             "fouls": 1.0, "yellow_cards": 0.0, "red_cards": 0.0},
        ]},
    }}


def test_wc_defense_table_allowed_is_what_opponents_produced():
    table = oa.wc_defense_table(_wc_cache_fixture())
    assert table["teams"]["wall"]["allowed"]["shots_on_target"] == 1.0
    assert table["teams"]["sieve"]["allowed"]["shots_on_target"] == 5.0
    assert table["league_avg"]["shots_on_target"] == pytest.approx(3.0)


def test_soccer_factor_shrinks_and_flags_unknown():
    cache = _wc_cache_fixture()
    wall = oa.soccer_factor("Wall", "shots_on_target", cache)
    sieve = oa.soccer_factor("Sieve", "shots_on_target", cache)
    assert wall["factor"] < 1.0 < sieve["factor"]
    assert wall["basis"] == "wc_2026_allowed"
    ghost = oa.soccer_factor("Atlantis", "shots_on_target", cache)
    assert ghost["factor"] == 1.0 and ghost["basis"] == "no_data"


def test_basketball_factor_partial_name_and_pace_proxy_half():
    cache = {"teams": {
        "las vegas aces": {"display": "Las Vegas Aces", "points_allowed": 95.0, "games": 20},
        "golden state valkyries": {"display": "Golden State Valkyries", "points_allowed": 85.0, "games": 20},
    }}
    pts = oa.basketball_factor("wnba", "Aces", "points", cache)
    reb = oa.basketball_factor("wnba", "Aces", "rebounds", cache)
    assert pts["factor"] > 1.0
    # rebounds get HALF the deviation of the points factor (pace proxy)
    assert (reb["factor"] - 1.0) == pytest.approx((pts["factor"] - 1.0) * 0.5)
    assert reb["basis"] == "points_allowed_pace_proxy_half"


def test_nfl_factor_routes_pass_vs_rush_and_neutral_stats():
    cache = {"season": 2025, "teams": {
        "steel curtain": {"display": "Steel Curtain", "games": 17,
                          "pass_allowed": 180.0, "rush_allowed": 80.0},
        "swiss cheese": {"display": "Swiss Cheese", "games": 17,
                         "pass_allowed": 260.0, "rush_allowed": 150.0},
    }}
    rec = oa.nfl_factor("Steel Curtain", "receiving_yards", cache)
    rush = oa.nfl_factor("Swiss Cheese", "rushing_yards", cache)
    assert rec["basis"] == "pass_defense" and rec["factor"] < 1.0
    assert rush["basis"] == "rush_defense" and rush["factor"] > 1.0
    tackles = oa.nfl_factor("Steel Curtain", "tackles", cache)
    assert tackles["factor"] == 1.0 and tackles["basis"] == "no_data"


def test_parse_nfl_boxscore_teams():
    summary = {"boxscore": {"teams": [
        {"team": {"displayName": "A"}, "statistics": [
            {"name": "netPassingYards", "displayValue": "191"},
            {"name": "rushingYards", "displayValue": "42"}]},
        {"team": {"displayName": "B"}, "statistics": [
            {"name": "netPassingYards", "displayValue": "250"},
            {"name": "rushingYards", "displayValue": "120"}]},
    ]}}
    sides = oa.parse_nfl_boxscore_teams(summary)
    assert sides[0] == {"team": "A", "pass_yards": 191.0, "rush_yards": 42.0}
    assert oa.parse_nfl_boxscore_teams({"boxscore": {"teams": []}}) is None


def test_opponent_factor_dispatcher_never_raises():
    r = oa.opponent_factor("cricket", "Anyone", "runs")
    assert r["factor"] == 1.0 and r["basis"] == "no_data"


# ── Team off/def ratings ─────────────────────────────────────────────────────
import team_off_def as tod


def test_finish_table_normalizes_vs_league_avg():
    teams = {"hot": {"display": "Hot", "games": 10, "scored_pg": 120.0, "allowed_pg": 100.0},
             "cold": {"display": "Cold", "games": 10, "scored_pg": 80.0, "allowed_pg": 100.0}}
    t = tod.finish_table(teams, 2026)
    assert t["league_avg"] == 100.0
    assert t["teams"]["hot"]["off_rating"] == 1.2
    assert t["teams"]["cold"]["off_rating"] == 0.8
    assert t["teams"]["hot"]["def_rating"] == 1.0


def test_finish_table_unweighted_when_no_games_metadata():
    teams = {"a": {"display": "A", "games": 0, "scored_pg": 3.0, "allowed_pg": 2.0},
             "b": {"display": "B", "games": 0, "scored_pg": 1.0, "allowed_pg": 2.0}}
    t = tod.finish_table(teams, 2026)
    assert t["league_avg"] == 2.0  # unweighted mean, table never comes back empty


def test_extract_mlb_runs_scored_vs_allowed():
    fixture = {"splits": {"categories": [
        {"name": "batting", "stats": [{"name": "gamesPlayed", "value": 90},
                                       {"name": "runs", "value": 450}]},
        {"name": "pitching", "stats": [{"name": "gamesPlayed", "value": 90},
                                        {"name": "runs", "value": 360}]}]}}
    r = tod.extract_mlb(fixture)
    assert r == {"scored_pg": 5.0, "allowed_pg": 4.0, "games": 90}


def test_extract_nhl_derives_games_from_totals():
    fixture = {"splits": {"categories": [
        {"name": "offensive", "stats": [{"name": "avgGoals", "value": 3.2},
                                         {"name": "goals", "value": 262.4}]},
        {"name": "defensive", "stats": [{"name": "avgGoalsAgainst", "value": 2.9}]}]}}
    r = tod.extract_nhl(fixture)
    assert r["games"] == 82  # NHL core stats carry no gamesPlayed

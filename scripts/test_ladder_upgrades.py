"""Tests for the 2026-07-20 ladder-rebuild upgrades: tennis engine fusion,
MLB pitcher shrinkage, WNBA schedule context pricing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import edge_api as ea
from mlb_game_model import SHRINK_STARTS, pitcher_defense_factor

ea.load_all()


# ── Tennis fusion ─────────────────────────────────────────────────────────────
def test_tennis_headline_prob_is_the_fuse_when_serve_stats_exist():
    out = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Andrey Rublev",
                                   away_team="Luciano Darderi",
                                   home_odds=-100, away_odds=-100, surface="Clay"))
    pts, srv = out["points_model_home_prob"], out["serve_model_home_prob"]
    assert abs(out["home_cover_prob"] - (pts + srv) / 2) < 1e-3  # fields rounded to 3dp
    assert "+ServeFused" in out["method"]


def test_tennis_split_router_still_fires_on_raw_lens_gap():
    out = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Andrey Rublev",
                                   away_team="Luciano Darderi",
                                   home_odds=-100, away_odds=-100, surface="Clay"))
    assert "split_robust_markets" in out          # raw gap 0.53 vs 0.69 > 0.12
    r = out["split_robust_markets"]["home_ml"]
    assert r["points"] != r["serve"]              # lenses stay distinct post-fusion


# ── MLB pitcher shrinkage ─────────────────────────────────────────────────────
def test_small_sample_starter_keeps_only_a_fraction_of_deviation():
    team_ra = 4.5
    bad_4_starts = {"name": "X", "ra9": 7.6, "ip_per_start": 5.4, "starts": 4}
    factor, det = pitcher_defense_factor(bad_4_starts, team_ra)
    # 4 starts vs 8-start prior -> keeps 1/3 of the (7.6 - 4.5) deviation
    expected_shrunk = (4 * 7.6 + SHRINK_STARTS * 4.5) / (4 + SHRINK_STARTS)
    assert abs(det["ra9_shrunk"] - expected_shrunk) < 1e-3  # field rounded to 3dp
    assert factor < 7.6 / 4.5                     # far tamer than raw

def test_veteran_starter_barely_shrinks():
    team_ra = 4.5
    ace_25_starts = {"name": "Y", "ra9": 2.8, "ip_per_start": 6.0, "starts": 25}
    _, det = pitcher_defense_factor(ace_25_starts, team_ra)
    assert det["ra9_shrunk"] < 3.3                # 25 starts keeps ~76% of deviation

def test_no_starter_still_neutral():
    factor, det = pitcher_defense_factor(None, 4.5)
    assert factor == 1.0 and det is None


# ── WNBA schedule context ─────────────────────────────────────────────────────
def test_wnba_adj_is_capped_and_directional():
    teams = (ea.WNBA_FORM.get("teams") or {})
    names = list(teams.keys())
    if len(names) < 2:
        return                                    # no form file in this checkout
    adj, _ = ea._wnba_margin_adj(names[0], names[1])
    assert -ea.WNBA_ADJ_CAP <= adj <= ea.WNBA_ADJ_CAP

def test_wnba_unknown_team_is_neutral():
    adj, detail = ea._wnba_margin_adj("Cave Rocks", "Stone Hurlers")
    assert adj == 0.0 and detail is None


# ── Period markets (2026-07-20 round 2) ───────────────────────────────────────
def test_tennis_set1_markets_present_and_consistent():
    import tennis_games_model as tgm
    out = tgm.predict("Aryna Sabalenka", "Maria Sakkari")
    s1 = out["set1"]
    ka = out["player_a"]
    # set-1 favorite prob sits between 0.5 and full match prob (less time = closer)
    assert 0.5 < s1["winner"][ka] < out["match_prob"][ka]
    assert abs(s1["games_over_9_5"] + s1["games_under_9_5"] - 1.0) < 1e-6

def test_wnba_stub_ratings_replaced_by_real_point_diff():
    teams = ea.WNBA_FORM.get("teams") or {}
    if len(teams) < 2:
        return
    srt = sorted(teams.items(), key=lambda kv: -float(kv[1].get("avg_margin", 0)))
    best, worst = srt[0][0], srt[-1][0]
    out = ea.predict(ea.PredictReq(sport="WNBA", home_team=best, away_team=worst,
                                   home_odds=-110, away_odds=-110))
    assert out["home_cover_prob"] > 0.75          # best vs worst is NOT a coin flip
    assert "wnba_margin_source" in out
    p = out["periods"]
    # shorter period -> prob compresses toward 0.5, ordering must hold
    assert 0.5 < p["p_home_wins_1q"] < p["p_home_wins_1h"] < out["home_cover_prob"]


# ── Day-of condition layer (all sports, cited facts only) ─────────────────────
def test_condition_without_citation_is_ignored():
    out = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Andrey Rublev",
                                   away_team="Luciano Darderi", home_odds=-100,
                                   away_odds=-100, surface="Clay",
                                   condition_home="major"))     # no note!
    base = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Andrey Rublev",
                                    away_team="Luciano Darderi", home_odds=-100,
                                    away_odds=-100, surface="Clay"))
    assert out["home_cover_prob"] == base["home_cover_prob"]
    assert "ignored" in out["day_of_condition"]

def test_cited_condition_moves_the_line_against_the_hurt_side():
    base = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Andrey Rublev",
                                    away_team="Luciano Darderi", home_odds=-100,
                                    away_odds=-100, surface="Clay"))
    out = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Andrey Rublev",
                                   away_team="Luciano Darderi", home_odds=-100,
                                   away_odds=-100, surface="Clay",
                                   condition_home="major",
                                   condition_note="ATP: treated for illness overnight (example)"))
    assert out["home_cover_prob"] < base["home_cover_prob"]

def test_wnba_cited_condition_moves_margin():
    teams = list((ea.WNBA_FORM.get("teams") or {}).keys())
    if len(teams) < 2:
        return
    base = ea.predict(ea.PredictReq(sport="WNBA", home_team=teams[0], away_team=teams[1],
                                    home_odds=-110, away_odds=-110))
    out = ea.predict(ea.PredictReq(sport="WNBA", home_team=teams[0], away_team=teams[1],
                                   home_odds=-110, away_odds=-110,
                                   condition_away="major",
                                   condition_note="team injury report: starter OUT (example)"))
    assert out["home_cover_prob"] > base["home_cover_prob"]


def test_retirement_tracking_aggregates_from_comment_column():
    import datetime as dt
    from fetch_tennis_form import aggregate
    rows = []
    base_day = dt.datetime(2026, 7, 1)
    # 6 completed matches so both players clear MIN_MATCHES, then a retirement
    for i in range(6):
        rows.append({"Winner": "Player One", "Loser": "Player Two",
                     "Date": base_day + dt.timedelta(days=i), "Surface": "Hard",
                     "Best of": 3, "Comment": "Completed", "__wt": 1.0, "__h2h_wt": 1.0})
        rows.append({"Winner": "Player Two", "Loser": "Player One",
                     "Date": base_day + dt.timedelta(days=i), "Surface": "Hard",
                     "Best of": 3, "Comment": "Completed", "__wt": 1.0, "__h2h_wt": 1.0})
    rows.append({"Winner": "Player One", "Loser": "Player Two",
                 "Date": base_day + dt.timedelta(days=10), "Surface": "Hard",
                 "Best of": 3, "Comment": "Retired", "__wt": 1.0, "__h2h_wt": 1.0})
    out = aggregate(rows)
    two = out["players"]["two|p"]
    assert two["ret_recent"] == 1 and two["ret_last"] == "2026-07-11"
    assert "ret_recent" not in out["players"]["one|p"]


def test_market_ladder_always_present_and_ranked():
    out = ea.predict(ea.PredictReq(sport="TENNIS", home_team="Antonia Ruzic",
                                   away_team="Dominika Salkova", home_odds=-100,
                                   away_odds=-100, surface="Clay"))
    lad = out["market_ladder"]
    probs = [r["prob"] for r in lad]
    assert probs == sorted(probs, reverse=True)       # win-prob ranked
    assert {"home_ml", "away_ml", "home_wins_a_set", "away_wins_a_set"} <= {r["market"] for r in lad}
    top = lad[0]
    assert abs(top["min_odds"] - round(1.05 / top["prob"], 2)) < 0.01

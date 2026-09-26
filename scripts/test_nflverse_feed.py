"""nflverse feed — offline tests on tiny synthetic files (never touches the network)."""
import pandas as pd
import pytest

import nflverse_feed as nf


@pytest.fixture
def feed(tmp_path, monkeypatch):
    monkeypatch.setattr(nf, "DATA", tmp_path)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    rows = []
    # 2025: AAA dominant, DDD weak; 2026 weeks 1-2 played, week 3 upcoming
    for season, weeks in ((2025, range(1, 9)), (2026, range(1, 3))):
        for w in weeks:
            for h, a, hs, as_ in (("AAA", "DDD", 30, 10), ("BBB", "CCC", 20, 17)) if w % 2 else \
                                 (("CCC", "AAA", 14, 27), ("DDD", "BBB", 13, 20)):
                rows.append(dict(season=season, game_type="REG", week=w, gameday="2026-09-13",
                                 gametime="13:00", away_team=a, home_team=h, away_score=as_,
                                 home_score=hs, location="Home", result=hs - as_,
                                 home_qb_name=f"{h} QB1", away_qb_name=f"{a} QB1"))
    for h, a in (("AAA", "BBB"), ("DDD", "CCC")):
        rows.append(dict(season=2026, game_type="REG", week=3, gameday="2026-09-27", gametime="13:00",
                         away_team=a, home_team=h, away_score=None, home_score=None, location="Home",
                         result=None, home_qb_name=f"{h} QB1", away_qb_name=f"{a} QB1",
                         spread_line=6.5, total_line=44.5, home_moneyline=-300, away_moneyline=250,
                         home_spread_odds=-110, away_spread_odds=-110, over_odds=-110, under_odds=-110,
                         roof="outdoors", home_rest=7, away_rest=7, div_game=0))
    pd.DataFrame(rows).to_csv(tmp_path / "games.csv", index=False)
    depth = []
    for t in teams:
        depth += [dict(dt="2026-09-25T12:00:00Z", team=t, player_name=f"{t} QB1", gsis_id=f"{t}-qb1",
                       pos_abb="QB", pos_rank=1),
                  dict(dt="2026-09-25T12:00:00Z", team=t, player_name=f"{t} QB2", gsis_id=f"{t}-qb2",
                       pos_abb="QB", pos_rank=2),
                  dict(dt="2026-09-25T12:00:00Z", team=t, player_name=f"{t} CB1", gsis_id=f"{t}-cb1",
                       pos_abb="CB", pos_rank=1),
                  dict(dt="2026-09-25T12:00:00Z", team=t, player_name=f"{t} CB3", gsis_id=f"{t}-cb3",
                       pos_abb="CB", pos_rank=3)]
    pd.DataFrame(depth).to_csv(tmp_path / "depth_charts_2026.csv", index=False)
    inj = [dict(week=3, team="AAA", gsis_id="AAA-qb1", position="QB", full_name="AAA QB1",
                report_primary_injury="Elbow", report_status="Out", practice_status="Did Not Participate In Practice"),
           dict(week=3, team="AAA", gsis_id="AAA-cb3", position="CB", full_name="AAA CB3",
                report_primary_injury="Knee", report_status="Out", practice_status="Did Not Participate In Practice"),
           dict(week=3, team="BBB", gsis_id="BBB-cb1", position="CB", full_name="BBB CB1",
                report_primary_injury="Hamstring", report_status="Doubtful", practice_status="Limited"),
           dict(week=3, team="DDD", gsis_id="DDD-cb1", position="CB", full_name="DDD CB1",
                report_primary_injury="Toe", report_status=None, practice_status="Did Not Participate In Practice")]
    pd.DataFrame(inj).to_csv(tmp_path / "injuries_2026.csv", index=False)
    return tmp_path


def test_ratings_are_walk_forward_and_rank_teams(feed):
    r = nf.team_ratings(2026, 3, current_qb={t: f"{t} QB1" for t in "AAA BBB CCC DDD".split()})
    t = r["teams"]
    assert t["AAA"]["net"] > t["BBB"]["net"] > t["DDD"]["net"]
    assert t["AAA"]["games_this_season"] == 2 and r["through_week"] == 2
    m, total = nf.predict(r, "AAA", "BBB")
    assert m > 0 and 20 < total < 60


def test_qb_change_halves_the_prior(feed):
    same = nf.team_ratings(2026, 3, current_qb={"AAA": "AAA QB1"})["teams"]["AAA"]
    new = nf.team_ratings(2026, 3, current_qb={"AAA": "Someone New"})["teams"]["AAA"]
    assert same["prior_weight_games"] == nf.PRIOR_GAMES and not same["qb_changed"]
    assert new["prior_weight_games"] == nf.PRIOR_GAMES * nf.QB_CHANGE_PRIOR and new["qb_changed"]


def test_injuries_price_starters_only_and_watch_dnp(feed):
    cond, watch = nf.injury_conditions(2026, 3)
    players = {c["player"] for cs in cond.values() for c in cs}
    assert "AAA QB1" in players and "BBB CB1" in players
    assert "AAA CB3" not in players                    # backup: not priced
    assert next(c for c in cond["BBB"] if c["player"] == "BBB CB1")["weight"] == 0.75   # doubtful
    assert watch["DDD"] and "DNP" in watch["DDD"][0]


def test_override_adds_news_not_in_report_once(feed):
    ov = {"CCC": [{"player": "CCC QB1", "position": "QB", "status": "Out", "pts": 4.5, "source": "x"}],
          "AAA": [{"player": "AAA QB1", "position": "QB", "status": "Out", "source": "dup"}]}
    cond, _ = nf.injury_conditions(2026, 3, overrides=ov)
    assert [c["player"] for c in cond["CCC"]] == ["CCC QB1"]
    assert sum(c["player"] == "AAA QB1" for c in cond["AAA"]) == 1      # no double count


def test_week_slate_uses_backup_qb_and_no_double_qb_penalty(feed):
    sl = nf.week_slate(2026, 3)
    g = next(x for x in sl["games"] if x["id"] == "BBB@AAA")
    assert g["context"]["qb"]["home"] == "AAA QB2"                        # QB1 out -> QB2
    assert g["context"]["ratings"]["home"]["qb_changed"] is False         # injury != offseason change
    assert any(c["position"] == "QB" for c in g["conditions"]["home"])    # priced once, here
    assert g["spread"]["home_line"] == -6.5 and g["ratings_margin"] is not None
    assert nf.current_week(2026) == 3


def test_merge_live_prices_keeps_context(feed):
    sl = nf.week_slate(2026, 3)
    live = [{"home": sl["games"][0]["home"], "away": sl["games"][0]["away"],
             "moneyline": {"home": -500, "away": 400}, "ml_consensus_home": 0.8,
             "spread": {"home_line": -9.5}, "total": {"points": 41.5}}]
    merged = nf.merge_live_prices(sl["games"], live)
    assert merged[0]["moneyline"]["home"] == -500 and merged[0]["conditions"] == sl["games"][0]["conditions"]
    assert merged[1] == sl["games"][1]


def test_week_slate_is_json_safe_with_missing_fields(feed):
    import json
    g = pd.read_csv(feed / "games.csv")
    g.loc[g.week == 3, "roof"] = None                       # gaps in the real feed
    g.to_csv(feed / "games.csv", index=False)
    sl = nf.week_slate(2026, 3)
    json.dumps(sl["games"], allow_nan=False)                 # raises on NaN
    assert sl["games"][0]["context"]["roof"] is None


def test_override_skips_depth_chart_backups(feed):
    ov = {"AAA": [{"player": "AAA CB3", "position": "CB", "status": "Out", "source": "x"}],
          "BBB": [{"player": "BBB CB1", "position": "CB", "status": "Out", "source": "x"}]}
    cond, _ = nf.injury_conditions(2026, 3, overrides=ov)
    assert "AAA CB3" not in {c["player"] for c in cond.get("AAA", [])}   # backup (rank 3)

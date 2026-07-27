"""Tests for cricket fetch parsing + comparison model — fixture data, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cricket_model as cm
from fetch_cricket_rankings import parse_rankings_table

FIXTURE = {
    "meta": {"source": "test", "source_dates": {"t20i": "11 July 2026"},
             "fits": {"t20i": {"k": 0.017, "n": 932, "favorite_accuracy": 0.686,
                               "window_since": "2025-01-01", "draw_or_nr_rate": 0.05}}},
    "t20i": {"England": {"matches": 38, "points": 10186, "rating": 268, "rank": 1},
             "India": {"matches": 58, "points": 15532, "rating": 268, "rank": 2},
             "Australia": {"matches": 38, "points": 9868, "rating": 260, "rank": 3}},
    "odi": {"India": {"matches": 40, "points": 5000, "rating": 125, "rank": 1},
            "England": {"matches": 40, "points": 4800, "rating": 120, "rank": 2}},
    "test": {},
}

TABLE_HTML = """
<table class="wikitable" style="x">
<tr><th>Team</th><th>Matches</th><th>Points</th><th>Rating</th></tr>
<tr><td><a>England</a></td><td>38</td><td>10,186</td><td>268</td></tr>
<tr><td><a>India</a></td><td>58</td><td>15,532</td><td>268</td></tr>
<tr><td><a>Australia</a></td><td>38</td><td>9,868</td><td>260</td></tr>
<tr><td><a>New Zealand</a></td><td>50</td><td>12,348</td><td>247</td></tr>
<tr><td><a>West Indies</a></td><td>44</td><td>10,510</td><td>239</td></tr>
<tr><td><a>South Africa</a></td><td>40</td><td>9,300</td><td>232</td></tr>
<tr><td><a>Pakistan</a></td><td>45</td><td>10,100</td><td>224</td></tr>
<tr><td><a>Sri Lanka</a></td><td>42</td><td>9,000</td><td>214</td></tr>
<tr><td><a>Bangladesh</a></td><td>39</td><td>8,000</td><td>205</td></tr>
<tr><td><a>Afghanistan</a></td><td>35</td><td>7,000</td><td>200</td></tr>
<tr><td><a>Ireland</a></td><td>33</td><td>6,300</td><td>191</td></tr>
</table>
<p>Source: ICC Men's T20I Team Rankings, 11 July 2026</p>
"""


def test_parse_rankings_table_extracts_teams_and_order_rank():
    teams, _ = parse_rankings_table(TABLE_HTML)
    assert len(teams) == 11
    assert teams["England"] == {"matches": 38, "points": 10186, "rating": 268, "rank": 1}
    assert teams["Ireland"]["rank"] == 11


def test_compare_emits_fitted_probability_when_fit_exists(monkeypatch):
    monkeypatch.setattr(cm, "load", lambda: FIXTURE)
    out = cm.compare("England", "India", "t20i")
    assert out["icc_rating"]["England"] == 268
    assert out["edge_lean"] == "even"                     # 268 vs 268
    assert out["probability"] == {"England": 0.5, "India": 0.5}
    assert out["calibration"]["n"] == 932
    assert "a result" in out["probability_is"]            # draw-excluded semantics


def test_fitted_probability_follows_rating_gap(monkeypatch):
    monkeypatch.setattr(cm, "load", lambda: FIXTURE)
    out = cm.compare("England", "Australia", "t20i")      # +8 rating gap
    assert out["probability"]["England"] > 0.5
    assert abs(sum(out["probability"].values()) - 1.0) < 1e-6


def test_unfitted_format_still_refuses_probability(monkeypatch):
    monkeypatch.setattr(cm, "load", lambda: FIXTURE)
    out = cm.compare("England", "India", "odi")           # no odi fit in fixture
    assert out["probability"] is None
    assert "refus" in out["why_no_probability"]


def test_compare_lean_follows_rating_gap(monkeypatch):
    monkeypatch.setattr(cm, "load", lambda: FIXTURE)
    out = cm.compare("Australia", "England", "t20i")
    assert out["rating_gap"] == -8
    assert out["edge_lean"] == "England"


def test_unknown_team_refuses(monkeypatch):
    monkeypatch.setattr(cm, "load", lambda: FIXTURE)
    out = cm.compare("England", "Atlantis", "t20i")
    assert out["error"] == "NO_DATA"
    assert "Atlantis" in out["missing_teams"]


def test_format_isolation(monkeypatch):
    monkeypatch.setattr(cm, "load", lambda: FIXTURE)
    assert cm.compare("Australia", "India", "odi")["error"] == "NO_DATA"  # Australia not in odi fixture
    assert cm.compare("England", "India", "the_hundred")["error"] == "BAD_FORMAT"


def test_fit_formats_filters_franchise_and_undecided():
    from fetch_cricket_rankings import fit_formats, MIN_FIT_MATCHES
    table = {"A": {"rating": 260}, "B": {"rating": 200}}
    doc = {"t20i": table}
    # 120 A-wins (fit ok), 30 no-results, franchise rows dropped silently
    rows = ["match_id,match_type,team1,team2,venue,city,match_date,toss_winner,toss_decision,winner,win_margin"]
    rows += ["1,T20,A,B,v,c,2025-06-01,A,bat,A,5 runs"] * 120
    rows += ["2,T20,A,B,v,c,2025-06-01,A,bat,no result,"] * 30
    rows += ["3,T20,Mumbai Indians,B,v,c,2025-06-01,A,bat,B,"] * 50
    fits = fit_formats("\n".join(rows), doc)
    f = fits["t20i"]
    assert f["n"] == 120 >= MIN_FIT_MATCHES
    assert f["draw_or_nr_rate"] == 0.2            # 30 of 150 eligible
    assert f["k"] > 0.02                          # all wins for the +60 side -> k pushed high

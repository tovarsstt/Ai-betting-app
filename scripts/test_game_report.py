"""game_report — per-game sims are consistent (no network)."""
import game_report as gr


def test_analyze_is_consistent():
    g = {"sport": "NFL", "home": "Home", "away": "Away", "id": "Away@Home",
         "moneyline": {"home": -330, "away": 265}, "spread": {"home_line": -6.5},
         "total": {"points": 44.5}}
    a = gr.analyze(g, n_sims=200_000, seed=1)
    assert abs(sum(p for _, p in a["home_buckets"]) - 1) < 1e-9
    home, away = dict(a["ladder_home"]), dict(a["ladder_away"])
    assert home["ML"] > 0.65 and abs(home["ML"] + away["ML"] - 1) < 1e-9
    assert home["+13.5"] > home["-6.5"] > home["-13.5"]           # ladder is monotone
    assert a["proj"][1] > a["proj"][0] and a["key3"] > a["key7"] * 0.8
    assert all(abs(o + u - 1) < 1e-9 for ln, o, u in a["totals"] if ln % 1)   # half-point lines never push
    assert "Away @ Home" in "\n".join(gr.game_md(g, a))

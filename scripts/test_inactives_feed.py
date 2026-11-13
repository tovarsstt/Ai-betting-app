from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
import inactives_feed as f

FIX = Path(__file__).resolve().parent.parent / "data" / "test_fixtures" / "rotowire_inactives_20261112.html"


def test_parses_both_teams_with_positions():
    out = f.parse(FIX.read_text())
    assert out["NYG"] == [("CB", "Paulson Adebo"), ("OT", "J.C. Davis"), ("TE", "Thomas Fidone")]
    assert out["WAS"][1] == ("QB", "Athan Kaliakmanis") and len(out["WAS"]) == 3


def test_team_name_after_list_does_not_open_a_new_team():
    out = f.parse(FIX.read_text())
    assert set(out) == {"NYG", "WAS"}

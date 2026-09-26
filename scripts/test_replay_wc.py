"""Replay harness test — fixture-driven, no network."""
import replay_wc as rw


def test_replay_flags_canada_draw_as_lite():
    report = rw.run_replay()
    canada = next(r for r in report if "Canada" in r["label"])
    assert canada["grade"] == "LITE"
    assert canada["actual"] == "DRAW"


def test_replay_does_not_flag_germany_blowout():
    report = rw.run_replay()
    germany = next(r for r in report if "Germany" in r["label"])
    assert germany["grade"] == "NONE"

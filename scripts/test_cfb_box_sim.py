import numpy as np
import cfb_box_sim as S

L = {"TD": 0.25, "FG": 0.1, "MFG": 0.04, "TO": 0.12, "DTD": 0.01, "NO": 0.48}


def test_matchup_probs_sum_to_one_and_shift_toward_weak_defense():
    off = dict(L)
    weak_def = {**L, "TD": 0.40, "NO": 0.33}
    p = S.matchup_probs(off, weak_def, L)
    assert abs(p.sum() - 1) < 1e-9
    assert p[S.CLASSES.index("TD")] > L["TD"]


def test_drive_class_maps_known_and_unknown_results():
    assert S.drive_class("Touchdown") == "TD"
    assert S.drive_class("Downs") == "TO"
    assert S.drive_class("End of Half") == "NO"
    assert S.drive_class(None) == "NO"


def test_cover_counts_push_as_half():
    m = np.array([3.0, 3.0, 4.0, 2.0])
    assert abs(S.cover(m, -3.0) - 0.5) < 1e-9


def test_shrunk_rates_sum_to_one():
    r = S.shrunk({"TD": 20, "NO": 40}, 60, L)
    assert abs(sum(r.values()) - 1) < 1e-9

import numpy as np
import nfl_slate_final as F
import stake_week_retro as R


def test_tilt_hits_win_prob_and_total():
    rng = np.random.default_rng(1)
    M = np.round(rng.normal(2, 13, 20000)); T = np.round(rng.normal(48, 10, 20000))
    w = F.tilt(M, T, 0.7, 42.0)
    assert abs(w.sum() - 1) < 1e-9
    assert abs((w * ((M > 0) + 0.5 * (M == 0))).sum() - 0.7) < 0.01     # ties count half, as in the sim
    assert abs((w * T).sum() - 42.0) < 0.2


def test_weighted_quantile_matches_unweighted_on_uniform_weights():
    x = np.arange(1, 101.0); w = np.full(100, 0.01)
    assert F.wq(x, w, (0.5,))[0] in (50.0, 51.0)


def test_retro_roi_and_biggest_win_removed():
    rows = [["28 Oct", "multi", 3, 5.0, 10, 50.0, "W"], ["28 Oct", "multi", 3, 3.0, 10, 0, "L"], ["29 Oct", "sgm", 1, 4.0, 10, 0, "L"]]
    out = R.retro(rows)
    assert out["total"]["all"]["roi"] == round(50 / 30 - 1, 3)
    assert out["type"]["sgm"]["roi"] == -1.0
    top, roi = R.drop_largest_win(rows)
    assert top[5] == 50.0 and roi == -1.0

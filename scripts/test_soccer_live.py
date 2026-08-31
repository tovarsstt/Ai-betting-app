"""Tests for soccer_live: time-decayed Poisson live pricing (soccer_skill.md discipline)."""
import math
import unittest

from soccer_live import REGULATION_MIN, STOPPAGE_MIN, live_probs


LAM_H, LAM_A = 1.2, 1.6  # generic pre-match lambdas


class TestLiveProbs(unittest.TestCase):
    def test_probs_sum_to_one(self):
        p = live_probs(LAM_H, LAM_A, minute=30, score_home=0, score_away=1)
        self.assertAlmostEqual(p["home"] + p["draw"] + p["away"], 1.0, places=9)

    def test_minute_zero_equals_prematch(self):
        live = live_probs(LAM_H, LAM_A, minute=0, score_home=0, score_away=0)
        # full lambdas, no goals: this IS the pre-match matrix
        self.assertGreater(live["away"], live["home"])
        self.assertAlmostEqual(live["exp_goals_remaining"], LAM_H + LAM_A, places=9)

    def test_full_time_collapses_to_score(self):
        p = live_probs(LAM_H, LAM_A, minute=REGULATION_MIN + STOPPAGE_MIN, score_home=0, score_away=1)
        self.assertAlmostEqual(p["away"], 1.0, places=6)
        self.assertAlmostEqual(p["over_2_5"], 0.0, places=6)

    def test_leader_prob_grows_as_clock_burns(self):
        early = live_probs(LAM_H, LAM_A, minute=20, score_home=0, score_away=1)
        late = live_probs(LAM_H, LAM_A, minute=75, score_home=0, score_away=1)
        self.assertGreater(late["away"], early["away"])

    def test_over_line_already_beaten_is_certain(self):
        p = live_probs(LAM_H, LAM_A, minute=60, score_home=2, score_away=1)
        self.assertAlmostEqual(p["over_2_5"], 1.0, places=9)

    def test_dnb_decomposition(self):
        p = live_probs(LAM_H, LAM_A, minute=30, score_home=1, score_away=1)
        dnb = p["away_dnb"]
        # DNB win prob is conditional on no push
        self.assertAlmostEqual(dnb, p["away"] / (1.0 - p["draw"]), places=9)

    def test_btts_with_both_scored_is_certain(self):
        p = live_probs(LAM_H, LAM_A, minute=50, score_home=1, score_away=1)
        self.assertAlmostEqual(p["btts"], 1.0, places=9)

    def test_stoppage_allowance_keeps_leader_below_certainty(self):
        # at min 90 score 0-1 there is still stoppage time to survive
        p = live_probs(LAM_H, LAM_A, minute=90, score_home=0, score_away=1)
        self.assertLess(p["away"], 1.0)
        self.assertGreater(p["away"], 0.9)

    def test_handicap_minus_one(self):
        p = live_probs(LAM_H, LAM_A, minute=85, score_home=0, score_away=2)
        self.assertGreater(p["away_minus_1_5"], 0.8)


class TestRatingsLookup(unittest.TestCase):
    def test_alias_miss_raises(self):
        from soccer_live import lambdas_from_ratings
        with self.assertRaises(KeyError):
            lambdas_from_ratings("Serie A", "AS Roma FC Nonsense", "Lecce")

    def test_known_teams_resolve(self):
        from soccer_live import lambdas_from_ratings
        lam_h, lam_a = lambdas_from_ratings("Serie A", "Lecce", "Roma")
        self.assertGreater(lam_a, lam_h)  # Roma stronger away than Lecce home

    def test_champions_league_uses_europe_pool(self):
        # cross-league match — only priceable off the pooled Europe fit
        from soccer_live import lambdas_from_ratings
        lam_h, lam_a = lambdas_from_ratings("Champions League", "Real Madrid", "Arsenal")
        self.assertGreater(lam_h, 0.3)
        self.assertGreater(lam_a, 0.3)


class TestAsianEv(unittest.TestCase):
    """Quarter-line EV decomposition — over X.25 half-LOSES on exact X, over X.75 half-WINS on exact X+1."""

    def setUp(self):
        # deterministic total-goals pmf: P(4)=0.35, P(5)=0.40, P(3)=0.25
        from soccer_live import asian_ev
        self.asian_ev = asian_ev
        self.pmf = {3: 0.25, 4: 0.35, 5: 0.40}

    def test_half_line_simple(self):
        # over 4.5 @ 1.60: win 0.40, lose 0.60 -> EV = .40*.6 - .60 = -0.36
        self.assertAlmostEqual(self.asian_ev(self.pmf, 4.5, 1.60, "over"), -0.36, places=9)

    def test_whole_line_push(self):
        # over 4 @ 1.60: win .40*.6=.24, push .35, lose .25 -> EV = .24-.25 = -0.01
        self.assertAlmostEqual(self.asian_ev(self.pmf, 4.0, 1.60, "over"), -0.01, places=9)

    def test_quarter_line_is_mean_of_halves(self):
        # over 4.25 = mean(over 4.0, over 4.5)
        ev = self.asian_ev(self.pmf, 4.25, 1.40, "over")
        ev40 = self.asian_ev(self.pmf, 4.0, 1.40, "over")
        ev45 = self.asian_ev(self.pmf, 4.5, 1.40, "over")
        self.assertAlmostEqual(ev, (ev40 + ev45) / 2, places=9)

    def test_over_x25_half_loses_on_exact(self):
        # exact-4 mass must HURT over 4.25 (half stake lost), not pay half a win
        pmf_all4 = {4: 1.0}
        ev = self.asian_ev(pmf_all4, 4.25, 1.40, "over")
        self.assertAlmostEqual(ev, -0.5, places=9)  # half push, half lose

    def test_over_x75_half_wins_on_exact(self):
        pmf_all4 = {4: 1.0}
        ev = self.asian_ev(pmf_all4, 3.75, 1.40, "over")
        self.assertAlmostEqual(ev, 0.5 * 0.40, places=9)  # half wins at 1.40, half pushes

    def test_under_side(self):
        # under 4.5 @ 2.35: win P(<=4)=.60 -> EV = .60*1.35 - .40 = 0.41
        self.assertAlmostEqual(self.asian_ev(self.pmf, 4.5, 2.35, "under"), 0.41, places=9)

    def test_handicap_wrapper(self):
        from soccer_live import asian_handicap_ev
        # margin pmf (team perspective): win by 3 = 0.5, win by 4 = 0.5
        mpmf = {3: 0.5, 4: 0.5}
        # team -3.25 @ 1.43: margin 3 -> half push, half lose (return -0.5 on
        # that outcome); margin 4 -> full win at 0.43 net
        ev = asian_handicap_ev(mpmf, -3.25, 1.43)
        self.assertAlmostEqual(ev, 0.5 * 0.43 + 0.5 * (-0.5), places=9)


class TestTempoMultiplier(unittest.TestCase):
    def test_baseline_game_stays_near_one(self):
        from soccer_live import tempo_multiplier
        # ~0.09 SOT/min combined is baseline
        self.assertAlmostEqual(tempo_multiplier(total_sot=4, minute=45), 1.0, delta=0.12)

    def test_hot_game_bounded(self):
        from soccer_live import tempo_multiplier
        m = tempo_multiplier(total_sot=12, minute=30)
        self.assertLessEqual(m, 1.5)
        self.assertGreater(m, 1.2)

    def test_dead_game_bounded_below(self):
        from soccer_live import tempo_multiplier
        m = tempo_multiplier(total_sot=0, minute=80)
        self.assertGreaterEqual(m, 0.7)

    def test_early_minutes_shrink_to_prior(self):
        from soccer_live import tempo_multiplier
        # 2 SOT in 5 min is noisy — must stay close to 1, not explode
        self.assertLess(tempo_multiplier(total_sot=2, minute=5), 1.2)


if __name__ == "__main__":
    unittest.main()

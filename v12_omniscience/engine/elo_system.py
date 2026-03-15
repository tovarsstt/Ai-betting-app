"""
VIDEO-INSPIRED UPGRADE: ELO RATING SYSTEM
Source: YouTube Video 3 (Random Forest Tennis) — ELO gives the strongest predictive signal.
Concept: Track team/player skill ratings that update after every match outcome.
Application: Better than form-based stats. Fed into the Random Forest as a top feature.
"""
import math
import json
import os

INITIAL_ELO = 1500
K_FACTOR = 32  # Sensitivity of rating updates

class ELOSystem:
    """
    Elo Rating System — The strongest signal for predicting match outcomes.
    As shown in Video 3: Elo split data better than any other feature.
    """

    def __init__(self, save_path="/Users/josetovar/Documents/APP AI BETS/v12_omniscience/data/elo_ratings.json"):
        self.save_path = save_path
        self.ratings = self._load()

    def _load(self):
        if os.path.exists(self.save_path):
            with open(self.save_path) as f:
                return json.load(f)
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
        with open(self.save_path, "w") as f:
            json.dump(self.ratings, f, indent=2)

    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, INITIAL_ELO)

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Standard ELO expected win probability for Team A."""
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def update(self, winner: str, loser: str, draw: bool = False):
        """Update ELO ratings after a match result."""
        r_a = self.get_rating(winner)
        r_b = self.get_rating(loser)
        e_a = self.expected_score(r_a, r_b)
        s_a = 0.5 if draw else 1.0

        self.ratings[winner] = round(r_a + K_FACTOR * (s_a - e_a), 2)
        self.ratings[loser] = round(r_b + K_FACTOR * ((1 - s_a) - (1 - e_a)), 2)
        self._save()

    def compare(self, team_a: str, team_b: str) -> dict:
        """
        Main interface: get ELO-based win probabilities.
        This is the #1 feature to feed into Random Forest.
        """
        r_a = self.get_rating(team_a)
        r_b = self.get_rating(team_b)
        p_a = self.expected_score(r_a, r_b)
        diff = r_a - r_b

        return {
            "team_a_elo": r_a,
            "team_b_elo": r_b,
            "elo_diff": round(diff, 1),
            "elo_win_prob_a": round(p_a, 4),
            "elo_win_prob_b": round(1 - p_a, 4),
            "elo_signal": "TEAM_A_FAVORED" if diff > 50 else ("TEAM_B_FAVORED" if diff < -50 else "COIN_FLIP"),
            "elo_edge": round(abs(diff) / 400 * 100, 2)  # Edge magnitude in pct
        }

    def bulk_update_from_history(self, match_results: list):
        """
        Batch ingest historical results.
        Each item: {"winner": "TeamA", "loser": "TeamB", "draw": False}
        """
        for m in match_results:
            self.update(m["winner"], m["loser"], m.get("draw", False))
        return {"updated": len(match_results), "teams_rated": len(self.ratings)}

"""
VIDEO-INSPIRED UPGRADE & V13 INTEGRATION: ELO RATING SYSTEM
Source: YouTube Video 3 (Random Forest Tennis) — ELO gives the strongest predictive signal.
V13 Upgrade: Integrated ATPBetting logic to track multi-surface dynamic Elo (CLAY, GRASS, HARD).
"""
import math
import json
import os
import logging

INITIAL_ELO = 1500
K_FACTOR = 32  # Sensitivity of rating updates

class ELOSystem:
    """
    Elo Rating System — The strongest signal for predicting match outcomes.
    Now supports n-dimensional tracking based on Surface Types for Tennis predictions.
    """

    def __init__(self, save_path="/Users/josetovar/Documents/APP AI BETS/v12_omniscience/data/elo_ratings.json"):
        self.save_path = save_path
        self.ratings = self._load()

    def _load(self):
        if os.path.exists(self.save_path):
            try:
                with open(self.save_path) as f:
                    data = json.load(f)
                    # Backward compatibility for V12 flat structure
                    if data and "GLOBAL" not in data:
                        return {"GLOBAL": data, "CLAY": {}, "GRASS": {}, "HARD": {}}
                    if not data:
                        return {"GLOBAL": {}, "CLAY": {}, "GRASS": {}, "HARD": {}}
                    return data
            except Exception as e:
                logging.error(f"Error loading Elo ratings: {e}. Rebuilding matrix.")
        return {"GLOBAL": {}, "CLAY": {}, "GRASS": {}, "HARD": {}}

    def _save(self):
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
        with open(self.save_path, "w") as f:
            json.dump(self.ratings, f, indent=2)

    def get_rating(self, team: str, surface: str = "GLOBAL") -> float:
        surface = surface.upper() if surface else "GLOBAL"
        if surface not in self.ratings:
            self.ratings[surface] = {}
        return self.ratings[surface].get(team, INITIAL_ELO)

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Standard ELO expected win probability for Team A."""
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def _update_surface(self, winner: str, loser: str, draw: bool, surface: str):
        r_a = self.get_rating(winner, surface)
        r_b = self.get_rating(loser, surface)
        e_a = self.expected_score(r_a, r_b)
        s_a = 0.5 if draw else 1.0

        # Tennis-specific boost: if it's a specific surface, increase volatility/K-factor slightly
        # as surface specialists can have rapid swings in form during their primary seasons
        active_k = K_FACTOR * 1.25 if surface != "GLOBAL" else K_FACTOR

        self.ratings[surface][winner] = round(r_a + active_k * (s_a - e_a), 2)
        self.ratings[surface][loser] = round(r_b + active_k * ((1 - s_a) - (1 - e_a)), 2)

    def update(self, winner: str, loser: str, draw: bool = False, surface: str = None):
        """
        Update ELO ratings after a match result.
        Automatically updates GLOBAL, and specifically updates the surface if provided.
        """
        self._update_surface(winner, loser, draw, "GLOBAL")
        if surface:
            surface_key = surface.upper().strip()
            if surface_key in ["CLAY", "GRASS", "HARD", "HARDCOURT"]:
                mapped_surface = "HARD" if surface_key == "HARDCOURT" else surface_key
                self._update_surface(winner, loser, draw, mapped_surface)
        
        self._save()

    def compare(self, team_a: str, team_b: str, surface: str = None) -> dict:
        """
        Main interface: get ELO-based win probabilities.
        If surface is provided, calculates the weighted tensor of Global + Surface Elo.
        """
        r_a_global = self.get_rating(team_a, "GLOBAL")
        r_b_global = self.get_rating(team_b, "GLOBAL")
        
        r_a_surface = self.get_rating(team_a, surface) if surface else r_a_global
        r_b_surface = self.get_rating(team_b, surface) if surface else r_b_global

        # Weight surface heavily (70%) if evaluating a specific tennis context
        eff_r_a = (0.3 * r_a_global) + (0.7 * r_a_surface) if surface else r_a_global
        eff_r_b = (0.3 * r_b_global) + (0.7 * r_b_surface) if surface else r_b_global

        p_a = self.expected_score(eff_r_a, eff_r_b)
        diff = eff_r_a - eff_r_b

        return {
            "team_a_elo": round(eff_r_a, 1),
            "team_b_elo": round(eff_r_b, 1),
            "elo_diff": round(diff, 1),
            "elo_win_prob_a": round(p_a, 4),
            "elo_win_prob_b": round(1 - p_a, 4),
            "elo_signal": "TEAM_A_FAVORED" if diff > 50 else ("TEAM_B_FAVORED" if diff < -50 else "COIN_FLIP"),
            "elo_edge": round(abs(diff) / 400 * 100, 2), # Edge magnitude in pct
            "surface_evaluated": surface.upper() if surface else "GLOBAL"
        }

    def bulk_update_from_history(self, match_results: list):
        """
        Batch ingest historical results.
        Each item: {"winner": "TeamA", "loser": "TeamB", "draw": False, "surface": "CLAY"}
        """
        for m in match_results:
            self.update(m["winner"], m["loser"], m.get("draw", False), m.get("surface"))
        return {"updated": len(match_results), "teams_rated_global": len(self.ratings.get("GLOBAL", {}))}


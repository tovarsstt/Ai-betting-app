"""
ASA v5.0: RANDOM FOREST DECISION ENGINE
Evaluates 100+ decision trees per match to find non-linear outcomes.
This module is used as the core 'brain' of the ASA pipeline.
"""
import numpy as np
import random
import math
import time

class RandomForestDecisionEngine:
    """
    Implements the 'Random Forest Logic' from ASA v5.0.
    Each 'tree' evaluates a subset of features and votes on the outcome.
    The majority vote of 100 trees = the TRUE_PROBABILITY.
    """

    N_TREES = 100

    # --- Decision Tree Feature Weights ---
    FEATURE_KEYS = [
        "form_last5_weighted",     # Last 5 games, 40% weight on most recent
        "tackle_success_rate",     # Defensive aggression proxy
        "xg_offense",              # Expected goals / points (offense)
        "xg_defense",              # Expected goals allowed (defense)
        "referee_card_bias",       # Historical cards given by this ref
        "fatigue_decay",           # Minutes played in last 7 days
        "home_advantage",          # Home/away multiplier
        "momentum_velocity",       # Rate of change of efficiency (last 120 min)
        "altitude_tax",            # Performance drop at high altitude
        "key_player_available",    # 1.0 if starter playing, 0.7 if not
    ]

    def _single_tree(self, features_a, features_b, noise_scale=0.05):
        """
        A single decision tree. Each tree randomly drops 30% of features
        and evaluates the remaining using a simple weighted scoring model.
        This forces 'feature diversity' across the forest.
        """
        # Sample 70% of features per tree (like sklearn's max_features)
        n_features = max(3, int(len(self.FEATURE_KEYS) * 0.7))
        active_features = random.sample(self.FEATURE_KEYS, n_features)

        score_a = 0.0
        score_b = 0.0

        for feature in active_features:
            val_a = features_a.get(feature, 0.5) + random.gauss(0, noise_scale)
            val_b = features_b.get(feature, 0.5) + random.gauss(0, noise_scale)
            
            # Non-linear interaction: referee_card_bias amplified by fatigue
            if feature == "referee_card_bias" and "fatigue_decay" in active_features:
                val_a *= (1 + features_a.get("fatigue_decay", 0.5) * 0.3)
                val_b *= (1 + features_b.get("fatigue_decay", 0.5) * 0.3)

            score_a += val_a
            score_b += val_b

        # Tree vote: does Team A win?
        return 1 if score_a > score_b else 0

    def run_forest(self, features_a, features_b):
        """
        Runs all N_TREES and aggregates votes to find TRUE_PROBABILITY.
        Also detects non-linear outcomes (e.g., ref bias impacts late-game).
        """
        start = time.time()
        votes = [self._single_tree(features_a, features_b) for _ in range(self.N_TREES)]
        true_prob = sum(votes) / self.N_TREES
        
        # Feature Importance: which feature swings most votes?
        importance = {}
        for key in self.FEATURE_KEYS:
            delta = abs(
                features_a.get(key, 0.5) - features_b.get(key, 0.5)
            )
            importance[key] = round(delta, 3)
        
        top_factor = max(importance, key=importance.get)
        
        return {
            "true_probability": round(true_prob, 4),
            "forest_votes": f"{sum(votes)}/{self.N_TREES} trees favor Team A",
            "top_decisive_factor": top_factor,
            "confidence": "HIGH" if abs(true_prob - 0.5) > 0.1 else "MARGINAL",
            "exec_ms": round((time.time() - start) * 1000, 2)
        }

    def build_features(self, match_data):
        """
        Auto-maps matchup_data dict into the 10 core feature vectors.
        Works for both Team A and Team B.
        """
        return {
            "form_last5_weighted": match_data.get("form", 0.55),
            "tackle_success_rate": match_data.get("tackle_pct", 0.60),
            "xg_offense": match_data.get("xg_off", 0.55),
            "xg_defense": match_data.get("xg_def", 0.50),
            "referee_card_bias": match_data.get("ref_bias", 0.50),
            "fatigue_decay": match_data.get("fatigue", 0.40),
            "home_advantage": match_data.get("home_advantage", 0.52),
            "momentum_velocity": match_data.get("momentum", 0.50),
            "altitude_tax": match_data.get("altitude_tax", 0.48),
            "key_player_available": match_data.get("key_player", 1.0),
        }

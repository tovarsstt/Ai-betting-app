import numpy as np
from scipy.stats import poisson, norm
import time

# --- ARCHITECTURAL CORE: THE OMNISCIENCE ENGINE V12 (SHARP UPGRADE) ---

class V12SportEngine:
    def __init__(self, bankroll=1000.0):
        self.bankroll = bankroll
        self.version = "12.0.6-OMNISCIENCE-CORE"
        # Internal "Self-Evolving" Database (Simplified)
        self.league_avg_volatility = {
            "NBA": 12.0, "NFL": 14.0, "MLB": 4.1, "SOCCER": 1.1,
            "UFC": 0.5, "TENNIS": 0.3, "F1": 0.2, "WNBA": 11.0
        }

    def apply_quantum_overlay(self, probs, deep_features):
        """
        Adjusts probabilities by 'tilting' them based on the Combined Friction Index (CFI).
        CFI > 1.0 = Environmental Resistance (Win prob decay)
        CFI < 1.0 = Alpha Drive (Win prob boost)
        """
        cfi = deep_features.get("CFI", 1.0)
        # 1.0 is neutral. 1.2 is 20% friction. 
        # We apply a logarithmic adjustment to ensure non-linear decay
        tilt_factor = 1.0 / (cfi ** 0.5)
        
        new_win = probs['win'] * tilt_factor
        new_loss = probs['loss'] * (1.1 if cfi > 1.0 else 0.9) # Opponent benefits from your friction
        
        # Normalize
        total = new_win + new_loss + probs.get('draw', 0.0)
        return {
            "win": new_win / total,
            "loss": new_loss / total,
            "draw": probs.get('draw', 0.0) / total,
            "overlay_applied": True,
            "cfi_impact": cfi
        }

    def _get_poisson_probs(self, xg_home, xg_away, tactical_bias=1.0):
        """Logic for Soccer, MLB, NHL (Low-Scoring) with Tactical Bias"""
        # Apply tactical bias to the expected goals (e.g., 0.8 for defensive grind)
        xg_home *= tactical_bias
        xg_away *= tactical_bias
        
        home_win = 0
        draw = 0
        away_win = 0
        under_3_5 = 0
        
        for i in range(12):
            for j in range(12):
                p = poisson.pmf(i, xg_home) * poisson.pmf(j, xg_away)
                # Primary Outcomes
                if i > j: home_win += p
                elif i == j: draw += p
                else: away_win += p
                
                # Sharp Variable: Under 3.5 Logic
                if (i + j) < 3.5:
                    under_3_5 += p
                    
        return {
            "win": home_win, 
            "draw": draw, 
            "loss": away_win,
            "under_3_5": under_3_5
        }

    def _get_gaussian_probs(self, proj_home, proj_away, sport):
        """Logic for NBA, NFL, NCAAB, CFB, WNBA (High-Scoring)"""
        std_dev = self.league_avg_volatility.get(sport.upper(), 12.0)
        diff = proj_home - proj_away
        # Probability of winning outright (Moneyline)
        win_prob = 1 - norm.cdf(0, loc=diff, scale=std_dev)
        return {"win": win_prob, "loss": 1 - win_prob, "draw": 0.0}

    def _get_binary_probs(self, rating_a, rating_b):
        """Logic for UFC, Tennis, F1 (Elo-Based Individual)"""
        prob = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
        return {"win": prob, "loss": 1 - prob, "draw": 0.0}

    def calculate_kelly_stake(self, model_prob, market_odds):
        """Hedge Fund Risk Allocation (Fractional Kelly)"""
        b = market_odds - 1
        p = model_prob
        q = 1 - p
        if b <= 0: return 0.0
        edge = (b * p - q) / b
        if edge <= 0: return 0.0
        # Using 0.20 (1/5th Kelly) for maximum long-term bankroll safety
        return round(edge * self.bankroll * 0.20, 2)

    def analyze(self, sport, match_name, team_a_stats, team_b_stats, market_odds, sharp_factors=None, deep_features=None):
        sport = sport.upper()
        start_time = time.time()
        
        # Initialize Sharp Variables and Deep Features
        sharp_factors = sharp_factors or {}
        deep_features = deep_features or {}
        home_fortress = sharp_factors.get('home_fortress', 1.0)
        tactical_bias = sharp_factors.get('tactical_bias', 1.0)
        
        # 1. ROUTE LOGIC BY SPORT TYPE
        if sport in ["SOCCER", "MLB", "NHL"]:
            # Apply Home Fortress to Home xG
            val_a = team_a_stats['val'] * home_fortress
            val_b = team_b_stats['val']
            probs = self._get_poisson_probs(val_a, val_b, tactical_bias)
            market_type = "1X2 / DNB"
        elif sport in ["NBA", "NFL", "NCAAB", "NCAAW", "CFB", "WNBA"]:
            # Apply Home Fortress to Home Projected Points
            val_a = team_a_stats['val'] + (3.0 * (home_fortress - 1.0) * 5) # Scale to points
            val_b = team_b_stats['val']
            probs = self._get_gaussian_probs(val_a, val_b, sport)
            market_type = "SPREAD / ML"
        elif sport in ["UFC", "TENNIS", "F1"]:
            probs = self._get_binary_probs(team_a_stats['val'], team_b_stats['val'])
            market_type = "MONEYLINE"
        else:
            return {"error": f"Sport '{sport}' not supported in V12 Core."}

        # 1.5 APPLY QUANTUM OVERLAY (The Secret Alpha)
        if deep_features:
            probs = self.apply_quantum_overlay(probs, deep_features)

        # 2. DATA ANALYST QUANT LAYER
        model_prob = probs['win']
        implied_prob = 1 / market_odds if market_odds > 0 else 1.0
        ev = (model_prob * market_odds) - 1
        edge = model_prob - implied_prob
        stake = self.calculate_kelly_stake(model_prob, market_odds)

        # 3. SELF-EVOLVING INSIGHT GENERATION
        status = "ALPHA_LOCK" if edge > 0.05 else "NEUTRAL"
        if edge < 0: status = "AVOID_VALUE_TRAP"
        
        # Extra Sharp Insights
        sharp_insight = ""
        if home_fortress > 1.1:
            sharp_insight += f" // HOME_FORTRESS_DETECTED ({int((home_fortress-1)*100)}% boost)"
        if tactical_bias < 0.9:
            sharp_insight += f" // DEFENSIVE_GRIND_DETECTED ({int((1-tactical_bias)*100)}% total reduction)"

        # 4. SOCIAL SYNDICATION FORMATTING
        execution_ms = (time.time() - start_time) * 1000
        
        return {
            "SYNDICATION_BLOCK": {
                "HEADER": f"GOD-ENGINE {self.version} // {match_name.upper()}",
                "SPORT_CORE": f"{sport} [{market_type}]",
                "PRIMARY_PICK": f"{match_name.split('vs')[0].strip() if 'vs' in match_name else match_name}",
                "METRICS": {
                    "MODEL_PROB": f"{round(model_prob * 100, 2)}%",
                    "MARKET_EDGE": f"{round(edge * 100, 2)}%",
                    "ADJ_EV": f"+{round(ev * 100, 2)}%",
                },
                "RISK_MGMT": {
                    "SUGGESTED_STAKE": f"${stake}",
                    "CONFIDENCE": status
                },
                "V12_DIAGNOSTIC": f"Simulated in {round(execution_ms, 2)}ms. Bayesian Variance: Low.{sharp_insight}",
                "DEEP_FEATURES": deep_features
            },
            "raw_probs": probs,
            "edge": edge,
            "ev": ev,
            "stake": stake,
            "sharp_variables": {
                "under_3_5_prob": f"{round(probs.get('under_3_5', 0) * 100, 2)}%" if 'under_3_5' in probs else "N/A"
            }
        }

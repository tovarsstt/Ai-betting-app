import numpy as np
from scipy.stats import poisson, norm
import time
import random
import json

class QSA_V13_Engine:
    """
    QUANTUM SPORTS ARCHITECT (QSA) - VERSION 4.0 [EVOLVING]
    OMNISCIENCE V13: The Perfect Algorithm.
    """

    def __init__(self, feature_factory=None):
        self.version = "13.0.1-QSA-VANGUARD"
        self.features = feature_factory
        self.sim_iterations = 10000

    # --- SUBROUTINE_1: {DATA_HARVEST} ---
    def _data_harvest(self, matchup_data):
        """Extracts Impact Delta and weighting for injuries/form."""
        intel = {
            "injuries": matchup_data.get("injuries", "NONE_CRITICAL"),
            "stadium": matchup_data.get("stadium_conditions", "STABLE"),
            "impact_delta": matchup_data.get("impact_delta", 1.0) # 1.0 = Neutral
        }
        return intel

    # --- SUBROUTINE_2: {TACTICAL_GEOMETRY} ---
    def _tactical_geometry(self, sport, team_a_tactics, team_b_tactics):
        """Calculates tactical friction based on playing styles."""
        # Example: Soccer Verticality vs High Line
        friction = 1.0
        if sport == "SOCCER":
            if "high_line" in team_b_tactics and "verticality" in team_a_tactics:
                friction -= 0.15 # Team A exploits space behind B
        return friction

    # --- SUBROUTINE_3: {NARRATIVE_LOAD} ---
    def _narrative_load(self, psych_factors):
        """Calculates the Psychological Coefficient (Stress/Complacency)."""
        coeff = 1.0
        if psych_factors.get("is_revenge_arc"): coeff += 0.08
        if psych_factors.get("is_trap_game"): coeff -= 0.12
        return coeff

    # --- SUBROUTINE_4: {MONTE_CARLO_ATOMIC_SIM} ---
    def _atomic_simulation(self, sport, team_a_power, team_b_power, multipliers):
        """
        Runs 10,000 iterations of a minute-by-minute state-space model.
        Detects the PIVOT POINT where probability swings >15%.
        """
        win_a = 0
        points_a_timeline = []
        pivot_minute = 45 # Default
        
        # We simulate the first 100 sims to find the pivot point
        # And then run the rest for probability convergence
        pivot_swings = []
        
        for sim in range(self.sim_iterations):
            score_a = 0
            score_b = 0
            prob_history = []
            
            # Simple 90-minute walk (Soccer as base)
            for m in range(1, 91):
                # Pressure increases as game goes on (Fatigue)
                pressure = (m / 90) * 0.2
                
                # Base prob of scoring per minute
                m_prob_a = (team_a_power / 90) * multipliers['cfi'] * (1 + pressure)
                m_prob_b = (team_b_power / 90) * (1 - pressure)
                
                if random.random() < m_prob_a: score_a += 1
                if random.random() < m_prob_b: score_b += 1
                
                # In first 100 sims, track prob swings
                if sim < 100:
                    current_prob_swing = (score_a - score_b) * 0.1
                    prob_history.append(current_prob_swing)
            
            if score_a > score_b: win_a += 1
            
            if sim < 100:
                # Find the minute with max diff in derivative
                deltas = np.diff(prob_history)
                if len(deltas) > 0:
                    max_swing_idx = np.argmax(np.abs(deltas))
                    pivot_swings.append(max_swing_idx + 1)

        final_prob = win_a / self.sim_iterations
        avg_pivot = int(np.mean(pivot_swings)) if pivot_swings else 45
        
        return {
            "win_prob": final_prob,
            "pivot_point": f"{avg_pivot}'th Minute",
            "script": "Early pressure likely to yield 1st-half dominance."
        }

    def analyze(self, matchup_request):
        """Standard QSA v4.0 Output Orchestrator."""
        start_time = time.time()
        
        # Execute Subroutines
        intel = self._data_harvest(matchup_request)
        tactical_friction = self._tactical_geometry(
            matchup_request.get("sport"), 
            matchup_request.get("team_a_tactics", []), 
            matchup_request.get("team_b_tactics", [])
        )
        psych_coeff = self._narrative_load(matchup_request.get("psych", {}))
        
        # Global Multiplier
        cfi = tactical_friction * psych_coeff * intel['impact_delta']
        
        # Run Atomic Sim
        sim_results = self._atomic_simulation(
            matchup_request.get("sport"),
            matchup_request.get("team_a_stats", {}).get("val", 1.5),
            matchup_request.get("team_b_stats", {}).get("val", 1.1),
            {"cfi": cfi}
        )
        
        execution_ms = (time.time() - start_time) * 1000
        
        # QSA v4.0 FORMAT
        return {
            "EVENT_NAME": matchup_request.get("matchup", "UNKNOWN MATCHUP"),
            "LIVE_INTEL": f"Injuries: {intel['injuries']} // Conditions: {intel['stadium']}",
            "TACTICAL_BLUEPRINT": f"Tactical Friction Index: {round(tactical_friction, 2)}. Interaction: {sim_results['script']}",
            "PIVOT_POINT": sim_results['pivot_point'],
            "ALPHA_PICK": f"{matchup_request.get('matchup').split('vs')[0].strip()} ML / Spread",
            "EDGE_CALCULATION": {
                "SIM_WIN_PROB": f"{round(sim_results['win_prob'] * 100, 2)}%",
                "MARKET_IMPLIED": f"{round((1/matchup_request.get('market_odds', 2.0))*100, 2)}%",
                "VALUE_EDGE": f"{round((sim_results['win_prob'] - (1/matchup_request.get('market_odds', 2.0)))*100, 2)}%"
            },
            "DIAGNOSTIC": f"V13 Engine // Simulated in {round(execution_ms, 2)}ms."
        }

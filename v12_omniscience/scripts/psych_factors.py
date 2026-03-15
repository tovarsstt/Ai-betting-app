import numpy as np
from datetime import datetime, timedelta

class PsychFactors:
    """
    Implements 'The Tilt Tensor' and 'Fatigue Decay' logic.
    """

    def calculate_tilt_tensor(self, last_game_margin, spread_diff, is_loss=True):
        """
        Quantifies a team's performance variance after a 'High-Stress/Low-Outcome' event.
        Tilt = (abs(Actual_Margin - Spread) / Time_Delta) * Impact_Weight
        """
        if not is_loss:
            return 0.0 # Positive wins rarely cause 'tilt' in the same negative sense
            
        # A 'heartbreaking loss' is one where they lost by more than the spread in a close game,
        # or lost a game they were heavily favored in.
        stress_score = abs(last_game_margin - spread_diff)
        
        # Normalize stress score to [0, 1]
        tilt_factor = min(1.0, stress_score / 20.0)
        return round(float(tilt_factor), 4)

    def calculate_fatigue_decay(self, minutes_played_7d):
        """
        Recovery-curve variable (R) based on minutes played in a rolling 7-day window.
        Fatigue = 1 - exp(-minutes / Baseline)
        """
        # Baseline: 120 minutes in 7 days is high for a star, 240 for a team average?
        # Let's say 200 minutes is the 'red zone'.
        baseline = 200.0
        r_value = 1 - np.exp(-minutes_played_7d / baseline)
        return round(float(r_value), 4)

if __name__ == "__main__":
    psych = PsychFactors()
    # Scenario: Team lost by 1 point at the buzzer when they were -5 favorites.
    tilt = psych.calculate_tilt_tensor(-1, -5)
    print(f"🧠 Tilt Tensor [Heartbreaker]: {tilt}")
    
    # Scenario: Star player played 180 minutes in last 7 days.
    fatigue = psych.calculate_fatigue_decay(180)
    print(f"💤 Fatigue Decay Score: {fatigue}")

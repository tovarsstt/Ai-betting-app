import pandas as pd
import numpy as np

class ContextELO:
    """
    Calculates separate ELO ratings for teams based on context (Home/Away, Surface, etc).
    """
    
    def __init__(self, k_factor=32):
        self.k_factor = k_factor
        self.elo_matrix = {} # {(team, context): rating}

    def get_elo(self, team, context='neutral'):
        return self.elo_matrix.get((team, context), 1500.0)

    def expected_score(self, rating_a, rating_b):
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    def update_elo(self, team_a, team_b, actual_a, actual_b, context_a='neutral', context_b='neutral'):
        """
        actual_a: 1 if win, 0.5 if draw, 0 if loss
        """
        elo_a = self.get_elo(team_a, context_a)
        elo_b = self.get_elo(team_b, context_b)
        
        expected_a = self.expected_score(elo_a, elo_b)
        expected_b = 1 - expected_a
        
        new_elo_a = elo_a + self.k_factor * (actual_a - expected_a)
        new_elo_b = elo_b + self.k_factor * (actual_b - expected_b)
        
        self.elo_matrix[(team_a, context_a)] = round(new_elo_a, 2)
        self.elo_matrix[(team_b, context_b)] = round(new_elo_b, 2)
        
        return new_elo_a, new_elo_b

if __name__ == "__main__":
    elo_engine = ContextELO()
    # Mock update: Lakers win at home against Knicks
    new_a, new_b = elo_engine.update_elo("Lakers", "Knicks", 1, 0, context_a="home", context_b="away")
    print(f"🏀 Updated Home ELO (Lakers): {new_a}")
    print(f"🏀 Updated Away ELO (Knicks): {new_b}")

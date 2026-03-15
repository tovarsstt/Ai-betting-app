import numpy as np
from scipy.stats import poisson

def simulate_live_total(xg_remaining, goals_needed):
    """
    Simulates the probability of scoring 'goals_needed' or more 
    given the 'xg_remaining' for the rest of the match.
    """
    # Probability of scoring EXACTLY k goals
    prob_less_than_needed = 0
    for k in range(goals_needed):
        prob_less_than_needed += poisson.pmf(k, xg_remaining)
    
    prob_hitting = 1 - prob_less_than_needed
    return prob_hitting

# Newcastle vs Barca Live Analysis
# Pre-match total xG estimate: 3.1
# Current time: 27' (63 mins remaining)
# Current score: 0-0
# Goals needed for Over 2.5: 3

xg_pre = 3.1
time_rem = 63
xg_rem = xg_pre * (time_rem / 90)

prob_over_2_5 = simulate_live_total(xg_rem, 3)

print(f"--- V12 LIVE: NEWCASTLE vs BARCELONA ---")
print(f"Current Score: 0-0 (27')")
print(f"Remaining Time: {time_rem} mins")
print(f"Adjusted xG for remainder: {round(xg_rem, 2)}")
print(f"Probability of OVER 2.5: {round(prob_over_2_5 * 100, 2)}%")
print(f"Recommended Action: {'HOLD' if prob_over_2_5 > 0.4 else 'CONSIDER HEDGE'}")

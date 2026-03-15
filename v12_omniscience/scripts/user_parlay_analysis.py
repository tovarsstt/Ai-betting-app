import sys
import os
import json
import numpy as np

# Ensure imports work from project root
sys.path.append(os.getcwd())

from v12_omniscience.engine.simulators import MonteCarloSimulator

def analyze_user_parlays():
    mc = MonteCarloSimulator(iterations=50000)
    
    # xG Data from V12 OSINT
    games = {
        "GALA_LIV": {"xg_a": 1.1, "xg_b": 2.5},
        "ATA_BAY": {"xg_a": 1.6, "xg_b": 2.1},
        "NEW_BARG": {"xg_a": 1.47, "xg_b": 1.31},
        "ATM_TOT": {"xg_a": 1.55, "xg_b": 1.53}
    }

    # Helper function for BTTS
    def prob_btts(mc_res, iters=50000):
        # We need the actual goal arrays, but we can approximate:
        # BTTS Prob = Prob(Both > 0) = (1 - CleanSheetA) * (1 - CleanSheetB) 
        # (This assumes independence, but Poisson goals are independent in this model)
        return (1 - mc_res['clean_sheet_prob_a']) * (1 - mc_res['clean_sheet_prob_b'])

    # Helper function for Over 2.5
    def prob_over_total(mean_a, mean_b, total=2.5, iters=50000):
        goals_a = np.random.poisson(lam=mean_a, size=iters)
        goals_b = np.random.poisson(lam=mean_b, size=iters)
        return np.sum((goals_a + goals_b) > total) / iters

    # Helper function for Draw No Bet
    def prob_dnb_a(mc_res):
        # DNB A = WinA / (WinA + WinB)
        total_non_draw = mc_res['win_prob_a'] + mc_res['win_prob_b']
        return mc_res['win_prob_a'] / total_non_draw if total_non_draw > 0 else 0

    print("🧩 V12 USER PARLAY ANALYSIS 🧩")
    print("-" * 60)

    # Pre-simulate all games
    sims = {k: mc.simulate_soccer_match(v['xg_a'], v['xg_b']) for k, v in games.items()}

    # Parlay 1 Analysis
    print("\n📦 PARLAY 1: 'Stability Mix' (Odds: 3.09)")
    p1_legs = [
        {"name": "Gala-Liv X2", "prob": sims['GALA_LIV']['win_prob_b'] + sims['GALA_LIV']['draw_prob'], "odds": 1.22},
        {"name": "Ata-Bay Over 2.5", "prob": prob_over_total(games['ATA_BAY']['xg_a'], games['ATA_BAY']['xg_b']), "odds": 1.46},
        {"name": "New-Bar BTTS (Yes)", "prob": prob_btts(sims['NEW_BARG']), "odds": 1.39},
        {"name": "Atm DNB", "prob": prob_dnb_a(sims['ATM_TOT']), "odds": 1.25}
    ]
    
    p1_total_prob = 1.0
    for leg in p1_legs:
        p1_total_prob *= leg['prob']
        print(f"  - {leg['name']}: {leg['prob']*100:.1f}% Prob | Fair Odds: {1/leg['prob']:.2f} (Market: {leg['odds']})")
    
    p1_total_odds = 3.09
    print(f"  📊 PARLAY 1 WIN PROB: {p1_total_prob*100:.2f}%")
    print(f"  📊 V12 FAIR ODDS: {1/p1_total_prob:.2f}")
    print(f"  📈 EDGE (EV): {((p1_total_prob * p1_total_odds) - 1) * 100:+.1f}%")

    # Parlay 2 Analysis
    print("\n💥 PARLAY 2: 'The Over-Drive' (Odds: 6.11)")
    p2_legs = [
        {"name": "Gala-Liv Over 2.5", "prob": prob_over_total(games['GALA_LIV']['xg_a'], games['GALA_LIV']['xg_b']), "odds": 1.55},
        {"name": "New-Bar Over 2.5", "prob": prob_over_total(games['NEW_BARG']['xg_a'], games['NEW_BARG']['xg_b']), "odds": 1.42},
        {"name": "Ata-Bay Over 2.5", "prob": prob_over_total(games['ATA_BAY']['xg_a'], games['ATA_BAY']['xg_b']), "odds": 1.46},
        {"name": "Atm-Tot Over 2.5", "prob": prob_over_total(games['ATM_TOT']['xg_a'], games['ATM_TOT']['xg_b']), "odds": 1.90}
    ]
    
    p2_total_prob = 1.0
    for leg in p2_legs:
        p2_total_prob *= leg['prob']
        print(f"  - {leg['name']}: {leg['prob']*100:.1f}% Prob | Fair Odds: {1/leg['prob']:.2f} (Market: {leg['odds']})")
    
    p2_total_odds = 6.11
    print(f"  📊 PARLAY 2 WIN PROB: {p2_total_prob*100:.2f}%")
    print(f"  📊 V12 FAIR ODDS: {1/p2_total_prob:.2f}")
    print(f"  📈 EDGE (EV): {((p2_total_prob * p2_total_odds) - 1) * 100:+.1f}%")

if __name__ == "__main__":
    analyze_user_parlays()

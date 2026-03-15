import sys
import os
import json
import time

# Ensure imports work from project root
sys.path.append(os.getcwd())

from v12_omniscience.engine.simulators import MonteCarloSimulator

def run_ucl_scan():
    mc = MonteCarloSimulator(iterations=50000) # Ultra-high fidelity for UCL
    
    print("🔥 PROJECT OMNISCIENCE: UCL CHAMPIONS LEAGUE SCAN [2026-03-10] 🔥")
    print("-" * 60)
    
    # Data gathered from V12 OSINT Scan
    matchups = [
        {
            "matchup": "Galatasaray vs Liverpool",
            "xg_a": 1.1, "xg_b": 2.5,
            "market_odds_a": 6.5, "market_odds_b": 1.45, "market_odds_draw": 4.5
        },
        {
            "matchup": "Atalanta vs Bayern Munich",
            "xg_a": 1.6, "xg_b": 2.1,
            "market_odds_a": 3.8, "market_odds_b": 1.85, "market_odds_draw": 4.0
        },
        {
            "matchup": "Newcastle vs Barcelona",
            "xg_a": 1.47, "xg_b": 1.31,
            "market_odds_a": 2.6, "market_odds_b": 2.5, "market_odds_draw": 3.6
        },
        {
            "matchup": "Atlético Madrid vs Tottenham",
            "xg_a": 1.55, "xg_b": 1.53,
            "market_odds_a": 2.4, "market_odds_b": 2.9, "market_odds_draw": 3.4
        }
    ]
    
    slate_analysis = []
    
    for game in matchups:
        res = mc.simulate_soccer_match(game['xg_a'], game['xg_b'])
        
        # Identify Best Edge (Alpha)
        edges = [
            {"label": "Home Win", "prob": res['win_prob_a'], "odds": game['market_odds_a']},
            {"label": "Away Win", "prob": res['win_prob_b'], "odds": game['market_odds_b']},
            {"label": "Draw", "prob": res['draw_prob'], "odds": game['market_odds_draw']}
        ]
        
        # Identify Stability Picks (Highest Probability including Double Chance)
        # Prob of Home Win or Draw
        prob_1x = res['win_prob_a'] + res['draw_prob']
        # Prob of Away Win or Draw
        prob_x2 = res['win_prob_b'] + res['draw_prob']
        
        stability_options = [
            {"label": f"{game['matchup'].split(' vs ')[0]} Win", "prob": res['win_prob_a'], "odds": game['market_odds_a']},
            {"label": f"{game['matchup'].split(' vs ')[1]} Win", "prob": res['win_prob_b'], "odds": game['market_odds_b']},
            {"label": f"{game['matchup'].split(' vs ')[0]} or Draw", "prob": prob_1x, "odds": 1.35}, # Conservative estimate for DC
            {"label": f"{game['matchup'].split(' vs ')[1]} or Draw", "prob": prob_x2, "odds": 1.40}  # Conservative estimate for DC
        ]
        
        for e in edges:
            e['ev'] = (e['prob'] * e['odds']) - 1
            
        best_edge = max(edges, key=lambda x: x['ev'])
        best_stability = max(stability_options, key=lambda x: x['prob'])
        
        print(f"📍 {game['matchup']}")
        print(f"   V12 Projections: {res['win_prob_a']*100:.1f}% / {res['draw_prob']*100:.1f}% / {res['win_prob_b']*100:.1f}%")
        print(f"   STABILITY LOCK: {best_stability['label']} ({best_stability['prob']*100:.1f}% Prob)")
        
        slate_analysis.append({
            "matchup": game['matchup'],
            "simulation": res,
            "best_edge": best_edge,
            "stability_pick": best_stability
        })

    # Generate the "GOD-TIER ALPHA" Parlay
    sorted_alpha = sorted(slate_analysis, key=lambda x: x['best_edge']['ev'], reverse=True)
    parlay_alpha = sorted_alpha[:3]
    
    # Generate the "STABILITY LOCK" Parlay
    # We pick the 3 legs with highest "Lock" probability
    sorted_stability = sorted(slate_analysis, key=lambda x: x['stability_pick']['prob'], reverse=True)
    parlay_stability = sorted_stability[:3]
    
    print("\n🛡️ V12 STABILITY LOCK PARLAY 🛡️")
    print("-" * 60)
    stable_prob = 1.0
    stable_odds = 1.0
    for leg in parlay_stability:
        pick = leg['stability_pick']
        stable_prob *= pick['prob']
        stable_odds *= pick['odds']
        print(f"🔒 {leg['matchup']} -> {pick['label']} (@{pick['odds']}) [{pick['prob']*100:.1f}%]")
    
    print("-" * 60)
    print(f"📊 TOTAL WIN PROBABILITY: {stable_prob * 100:.2f}%")
    print(f"📊 COMBINED ODDS: {stable_odds:.2f}")
    print(f"📈 ESTIMATED PARLAY EV: {((stable_prob * stable_odds) - 1) * 100:+.1f}%")

    with open("v12_omniscience/data/ucl_parlay_analysis.json", "w") as f:
        json.dump(slate_analysis, f, indent=4)

if __name__ == "__main__":
    run_ucl_scan()

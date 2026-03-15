from v12_omniscience.engine.v12_core_engine import V12SportEngine
import json

def run_post_mortem():
    engine = V12SportEngine(bankroll=1000.0)
    
    print("🔬 V12 Post-Mortem: Galatasaray vs Liverpool")
    
    # Let's assume some xG based on market expectations (Liverpool heavy favorites)
    # Market price 1.22 for X2 implies ~82% probability.
    xg_galatasaray = 1.1 # Home dog
    xg_liverpool = 1.9   # Visiting favorite
    
    # Analysis using V12 Core
    analysis = engine.analyze(
        sport="SOCCER",
        match_name="Galatasaray vs Liverpool",
        team_a_stats={'val': xg_galatasaray},
        team_b_stats={'val': xg_liverpool}, # Note: Engine A vs B is Galatasaray vs Liverpool
        market_odds=1.22 # This was the price for X2 (Draw or Away win)
    )
    
    # Calculate Prob(X2) = Prob(Draw) + Prob(Away Win)
    probs = analysis['raw_probs']
    prob_x2 = probs['draw'] + probs['loss'] # 'loss' in engine terms is Away Win if Team A is Home
    
    print(f"Engine Projections:")
    print(f" - Prob(Galatasaray Win): {round(probs['win'] * 100, 2)}%")
    print(f" - Prob(Draw): {round(probs['draw'] * 100, 2)}%")
    print(f" - Prob(Liverpool Win): {round(probs['loss'] * 100, 2)}%")
    print(f"\nFinal Result: Galatasaray 1-0 Liverpool")
    print(f"Model Prob(X2): {round(prob_x2 * 100, 2)}%")
    print(f"Market Prob(X2): {round((1/1.22) * 100, 2)}%")
    print(f"Edge: {round((prob_x2 - (1/1.22)) * 100, 2)}%")
    print(f"Status: {analysis['SYNDICATION_BLOCK']['RISK_MGMT']['CONFIDENCE']}")

if __name__ == "__main__":
    run_post_mortem()

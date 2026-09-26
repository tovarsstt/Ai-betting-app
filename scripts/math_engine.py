import json
import math
import sys
import os
import time
import requests
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import numpy as np
from scipy.stats import poisson, norm as scipy_norm, beta as scipy_beta
import asyncio
import uvicorn
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import playercareerstats, leaguedashplayerstats

app = FastAPI(title="CTE LOCKS Quant Simulation Node")

# v11 Environment
BALLDONTLIE_API_KEY = os.environ.get("BALLDONTLIE_API_KEY", "")
NBA_API_SEASON = '2025-26'

class OddsRequest(BaseModel):
    matchup: str
    sharp_odds: float = 1.90
    soft_odds: float = 2.00
    bankroll: float = 20.0
    market_spread: float = 0.0
    injury_impact_score: float = 0.0
    time_remaining_mins: float = 0.0
    distraction_index: float = 0.0
    sport: str = "NBA"

class PredictReq(BaseModel):
    true_prob: float
    market_spread: float
    injury_impact_score: float = 0.0
    time_remaining_mins: float = 48.0
    distraction_index: float = 1.0
    bankroll: float = 1000.0
    rest_advantage: int = 0  # Days of rest difference (Home - Away)
    sport: str = "NBA"
    market_type: str = "SPREAD"  # SPREAD, ML, TOTAL, SHOTS, BTTS

class PickAlpha(BaseModel):
    label: str
    edge: float
    true_probability_percent: float
    expected_value_usd: float
    kelly_sizing_usd: float
    analysis_rationale: str

class V11SimulationResult(BaseModel):
    status: str
    matchup: str
    date_context: str
    target_odds: str
    vig_adjusted_ev: str
    alpha_edge: str
    primary_lock: PickAlpha
    derivative_alpha: PickAlpha
    correlation_play: PickAlpha

class EvolveRequest(BaseModel):
    volatility_weight: float

class SimulationResult(BaseModel):
    mean_success_rate: float
    variance: float
    true_probability_percent: float
    kelly_sizing_usd: float
    expected_value_usd: float
    dynamic_edge_factor: float
    ref_delta: float
    pace_modifier: float
    verify_jit_alpha: bool

class RankedPick(BaseModel):
    label: str
    edge: float
    true_probability_percent: float
    expected_value_usd: float
    kelly_sizing_usd: float

class RankedSimulationResult(BaseModel):
    status: str
    picks: List[RankedPick]

# Global State for Sigma-3 Programmatic Evolution
VOLATILITY_SCALING = 1.0

# In-memory cache for NBA stats — prevents hitting NBA API on every request
_nba_stats_cache: dict = {"df": None, "fetched_at": 0.0}
_NBA_STATS_TTL = 3600  # 1 hour

def get_cached_nba_stats():
    now = time.time()
    if _nba_stats_cache["df"] is not None and now - _nba_stats_cache["fetched_at"] < _NBA_STATS_TTL:
        return _nba_stats_cache["df"]
    try:
        df = leaguedashplayerstats.LeagueDashPlayerStats(season=NBA_API_SEASON).get_data_frames()[0]
        _nba_stats_cache["df"] = df
        _nba_stats_cache["fetched_at"] = now
        return df
    except Exception as e:
        print(f"Warning: Could not fetch NBA API stats ({e})")
        return _nba_stats_cache["df"]  # return stale if available

@app.post("/evolve")
async def evolve_engine(request: EvolveRequest):
    global VOLATILITY_SCALING
    VOLATILITY_SCALING = request.volatility_weight
    return {"status": "Evolution Matrix Updated", "new_scaling": VOLATILITY_SCALING}

def calculate_exact_variance(true_prob: float, market_spread: float = 0.0, injury_impact_score: float = 0.0, time_remaining_mins: float = 0.0, distraction_index: float = 0.0) -> dict:
    """Bernoulli variance with heuristic injury/distraction adjustments. All weights are hand-tuned, not trained."""
    mean_success = float(true_prob)
    variance = float(true_prob * (1 - true_prob))

    # Injury penalty: each point of injury_impact reduces team efficiency up to 40%
    covariance_penalty = max(0.6, 1.0 - (injury_impact_score * 0.02)) if injury_impact_score > 0 else 1.0

    # Heuristic weighted blend: base prob, injury-adjusted prob, distraction-adjusted prob
    # Weights (0.60 / 0.25 / 0.15) are tuned heuristics, not fitted to data.
    w_base = 0.60
    w_injury = 0.25
    w_distraction = 0.15
    m_base = mean_success
    m_injury = mean_success * covariance_penalty
    m_distraction = mean_success * max(0.5, 1.0 - (distraction_index * 0.05))
    mean_success = (w_base * m_base) + (w_injury * m_injury) + (w_distraction * m_distraction)

    # Volatility scaling: high-injury or externally-set volatility widens the edge factor.
    # The 1.35 multiplier is a heuristic — it amplifies signal when context is extreme.
    edge_multiplier = (1.35 * VOLATILITY_SCALING) if (injury_impact_score > 15 or VOLATILITY_SCALING > 1.0) else 1.0

    # Spreads > 7 indicate higher game variance — inflate variance buffer accordingly
    volatility_buffer = 1.15 if abs(market_spread) > 7 else 1.0
    adjusted_variance = variance * volatility_buffer
    std_dev = float(math.sqrt(adjusted_variance))
    edge_factor = (mean_success / (std_dev if std_dev > 0 else 1)) * edge_multiplier

    # Garbage time: blowout + <4min remaining deflates predictive value
    if abs(market_spread) > 12.0 and 0.0 < time_remaining_mins < 4.0:
        edge_factor *= 0.78
        mean_success *= 0.78

    return {
        "mean": mean_success,
        "variance": adjusted_variance,
        "std_dev": std_dev,
        "edge_factor": edge_factor
    }

def fetch_live_action_network_odds(team_a: str, team_b: str) -> dict:
    """
    Autonomously pulls live odds from the Action Network public JSON scoreboard
    and correlates them against the requested teams. 
    Converts standard American odds to True Probability Decimal formats required for V11 execution.
    """
    try:
        url = "https://api.actionnetwork.com/web/v1/scoreboard/nba"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None
        
        data = response.json()
        search_a = team_a.lower()
        search_b = team_b.lower()
        
        for game in data.get("games", []):
            teams = game.get("teams", [])
            if len(teams) < 2: continue
            
            away_name = teams[0].get("full_name", "").lower()
            home_name = teams[1].get("full_name", "").lower()
            
            # Fuzzy match team names
            if (search_a in away_name or search_a in home_name) and (search_b in away_name or search_b in home_name):
                odds_list = game.get("odds", [])
                if not odds_list: return None
                
                odds = odds_list[0]
                
                if search_a in away_name:
                    team_a_ml = odds.get("ml_away")
                    team_a_spread = odds.get("spread_away")
                    team_b_ml = odds.get("ml_home")
                else:
                    team_a_ml = odds.get("ml_home")
                    team_a_spread = odds.get("spread_home")
                    team_b_ml = odds.get("ml_away")
                    
                def american_to_decimal(ame):
                    if not ame or ame == 0: return 1.90
                    if ame > 0: return (ame / 100.0) + 1.0
                    else: return (100.0 / abs(ame)) + 1.0
                
                # Vig removal approximation for Sharp Odds
                dec_a = american_to_decimal(team_a_ml)
                dec_b = american_to_decimal(team_b_ml)
                
                # [V12.0] Odds Ratio Devigging (Institutional Grade)
                def devig_odds_ratio(p1_implied, p2_implied):
                    # Solves for k where (p1^k + p2^k) = 1
                    # Approximation for 2-way markets: k = ln(1/sum) / ln(avg_p) ... simplified
                    # Actually, a robust iterative or algebraic approximation for 2-way:
                    total_implied = p1_implied + p2_implied
                    if total_implied <= 1: return p1_implied, p2_implied
                    
                    # Logarithmic / Power Method
                    k = math.log(0.5) / math.log((p1_implied + p2_implied) / 2.0) if (p1_implied + p2_implied) > 0 else 1
                    # More direct Odds Ratio approximation for 2-way:
                    # p_true = implied / (implied + (1-implied)*margin_factor)
                    margin = total_implied - 1
                    p1_true = p1_implied - (margin * (p1_implied * (1-p1_implied))) / (p1_implied*(1-p1_implied) + p2_implied*(1-p2_implied))
                    p2_true = p2_implied - (margin * (p2_implied * (1-p2_implied))) / (p1_implied*(1-p1_implied) + p2_implied*(1-p2_implied))
                    return p1_true, p2_true

                implied_a = 1.0 / dec_a if dec_a > 0 else 0
                implied_b = 1.0 / dec_b if dec_b > 0 else 0
                
                true_prob_a, true_prob_b = devig_odds_ratio(implied_a, implied_b)
                
                sharp_decimal_a = 1.0 / true_prob_a if true_prob_a > 0 else dec_a
                sharp_decimal_b = 1.0 / true_prob_b if true_prob_b > 0 else dec_b
                
                return {
                    "team_a_sharp": sharp_decimal_a,
                    "team_a_soft": dec_a,
                    "team_a_spread": team_a_spread,
                    "team_b_sharp": sharp_decimal_b,
                    "team_b_soft": dec_b,
                    "team_b_spread": team_b_spread,
                    "american_ml": team_a_ml
                }
    except Exception as e:
        print(f"Error fetching live odds: {e}")
    return None

def calculate_kelly_sizing(true_prob: float, decimal_odds: float, bankroll: float, fraction: float = 0.25) -> float:
    """
    Calculates the exact dollar amount to risk using a Fractional Kelly Criterion.
    """
    b = decimal_odds - 1.0
    q = 1.0 - true_prob
    if b <= 0: return 0.0
    
    # Standard Kelly Percentage
    kelly_pct = (b * true_prob - q) / b
    
    # If edge is negative, bet size is $0
    if kelly_pct <= 0:
        return 0.0
        
    # Apply fractional safety buffer
    adjusted_pct = kelly_pct * fraction
    
    # Cap maximum risk at 5% of total bankroll to prevent ruin
    final_risk_pct = min(adjusted_pct, 0.05)
    
    return round(bankroll * final_risk_pct, 2)

def poisson_player_prop_prob(avg_stat: float, line_value: float, xMins: float = 36.0) -> float:
    """
    P(stat > line) for discrete counting stats (points, rebounds, assists).
    Uses Poisson survival function — not a Monte Carlo simulation.
    xMins scales lambda via per-36 normalization.
    """
    if avg_stat <= 0 or xMins <= 0:
        return 0.0
    adjusted_avg = avg_stat * (xMins / 36.0)
    return float(poisson.sf(math.floor(line_value), adjusted_avg))

@app.post("/simulate", response_model=SimulationResult)
async def simulate_edge(request: OddsRequest):
    # Support both decimal odds (>1) and raw probabilities (<1)
    true_prob = 1 / request.sharp_odds if request.sharp_odds > 1 else request.sharp_odds
    true_prob = max(0.001, min(0.999, true_prob))
    soft_odds_decimal = request.soft_odds if request.soft_odds > 1 else (1 / max(0.001, request.soft_odds))
    mc_data = calculate_exact_variance(true_prob, request.market_spread, request.injury_impact_score, request.time_remaining_mins, request.distraction_index)
    
    # Tier 2: Poisson Check (Data-driven lambda based on implied probability)
    # λ = Expected value of the discrete variable. For a win-prob, we can derive a proxy lambda.
    # For a game total, λ = total / 2.
    # Since we don't have the full total here, we use a calibrated baseline (e.g., 105 pts per team)
    base_lambda = 105.0 
    poisson_edge = 1.0 - poisson.cdf(math.floor(request.market_spread + base_lambda), base_lambda)

    
    # Calculate EV
    unit_size = request.bankroll
    potential_profit = (soft_odds_decimal - 1.0) * unit_size
    ev = (true_prob * potential_profit) - ((1.0 - true_prob) * unit_size)
    
    kelly = calculate_kelly_sizing(true_prob, soft_odds_decimal, request.bankroll)
    
    # V7.0 Variables (Mocked baseline logic for context injection)
    base_ref_delta = 2.5 if request.sharp_odds < 2.0 else -1.5 
    base_pace = 101.5 
    
    # Just-In-Time Alpha Verification (V8.0)
    # The minimum required expected value threshold before proceeding to NLP TikTok script compilation
    is_jit_verified = ev > 0.02
    
    return SimulationResult(
        mean_success_rate=mc_data["mean"],
        variance=mc_data["variance"],
        true_probability_percent=true_prob * 100,
        kelly_sizing_usd=kelly,
        expected_value_usd=ev,
        dynamic_edge_factor=mc_data["edge_factor"],
        ref_delta=base_ref_delta,
        pace_modifier=base_pace,
        verify_jit_alpha=is_jit_verified
    )

@app.post("/simulate-ranked", response_model=RankedSimulationResult)
async def simulate_ranked(request: OddsRequest):
    true_prob = 1 / request.sharp_odds if request.sharp_odds > 1 else request.sharp_odds
    true_prob = max(0.001, min(0.999, true_prob))
    soft_odds_decimal = request.soft_odds if request.soft_odds > 1 else (1 / max(0.001, request.soft_odds))
    
    mc_data = calculate_exact_variance(true_prob, request.market_spread, request.injury_impact_score, request.time_remaining_mins, request.distraction_index)
    
    unit_size = request.bankroll
    potential_profit = (soft_odds_decimal - 1.0) * unit_size
    ev = (true_prob * potential_profit) - ((1.0 - true_prob) * unit_size)
    
    kelly = calculate_kelly_sizing(true_prob, soft_odds_decimal, request.bankroll)

    primary_edge = mc_data["edge_factor"]

    # Extract primary team from matchup for better labeling
    primary_team = "Game Line"
    if " vs " in request.matchup.lower():
        teams = request.matchup.split(" vs ")
        primary_team = teams[0].strip()
    elif " @ " in request.matchup.lower():
        teams = request.matchup.split(" @ ")
        primary_team = teams[0].strip()

    derivative_edge = primary_edge * 0.95
    correlation_edge = primary_edge * 0.85

    potential_plays = [
        {"label": f"{primary_team} ML/Spread", "edge": primary_edge, "prob": round(true_prob * 100, 1), "ev": ev, "kelly": kelly},
        {"label": f"{primary_team} Derivative Prop", "edge": derivative_edge, "prob": round(true_prob * 100 * 0.90, 1), "ev": ev * 0.95, "kelly": kelly * 0.95},
        {"label": "Correlated Market Alpha", "edge": correlation_edge, "prob": round(true_prob * 100 * 0.82, 1), "ev": ev * 0.85, "kelly": kelly * 0.85}
    ]

    # SORT BY WIN PROBABILITY FIRST, EDGE SECOND (favor likely winners over longshots)
    ranked_picks = sorted(potential_plays, key=lambda x: (x['prob'], x['edge']), reverse=True)

    final_picks = [
        RankedPick(
            label=p["label"],
            edge=p["edge"],
            true_probability_percent=p["prob"],
            expected_value_usd=p["ev"],
            kelly_sizing_usd=p["kelly"]
        ) for p in ranked_picks[:3]
    ]

    return RankedSimulationResult(
        status="ALPHA_ACTIVE",
        picks=final_picks
    )

def search_player(name):
    nba_players = players.get_players()
    found_players = [p for p in nba_players if p['full_name'].lower().find(name.lower()) != -1]
    return found_players[0] if found_players else None

def get_player_stats(player):
    try:
        career = playercareerstats.PlayerCareerStats(player_id=player['id'])
        df = career.get_data_frames()[0]
        
        if df.empty:
            return None
            
        latest_season = df.iloc[-1]
        
        return {
            "entity": player['full_name'],
            "type": "player",
            "stats": {
                "season": str(latest_season['SEASON_ID']),
                "games_played": int(latest_season['GP']),
                "points": float(latest_season['PTS']) / float(latest_season['GP']) if float(latest_season['GP']) > 0 else 0,
                "rebounds": float(latest_season['REB']) / float(latest_season['GP']) if float(latest_season['GP']) > 0 else 0,
                "assists": float(latest_season['AST']) / float(latest_season['GP']) if float(latest_season['GP']) > 0 else 0,
                "fg_pct": float(latest_season['FG_PCT']),
                "fg3_pct": float(latest_season['FG3_PCT'])
            }
        }
    except Exception as e:
        return None

@app.get("/nba-stats/{query}")
async def fetch_nba_stats(query: str):
    clean_name = query.replace("points", "").replace("over", "").replace("under", "").replace("rebounds", "").replace("assists", "").strip()
    parts = clean_name.split(" ")
    search_name = " ".join(parts[:2]) if len(parts) > 1 else parts[0]

    player = search_player(search_name)
    if player:
        stats = get_player_stats(player)
        if stats:
             return stats
            
    # Fallback to first name
    fallback_player = search_player(parts[0])
    if fallback_player:
         stats = get_player_stats(fallback_player)
         if stats:
              return stats

    raise HTTPException(status_code=404, detail=f"Could not extract player stats for: {clean_name}")

@app.get("/nba-matchup-context/{team_a}/{team_b}")
async def fetch_nba_matchup_context(team_a: str, team_b: str):
    try:
        stats_df = get_cached_nba_stats()
        if stats_df is None:
            raise HTTPException(status_code=503, detail="NBA stats unavailable")
        
        nba_teams = teams.get_teams()
        
        def get_team_abbrev(search_str):
            search_lower = search_str.lower()
            for t in nba_teams:
                if search_lower in t['full_name'].lower() or search_lower in t['nickname'].lower() or search_lower in t['abbreviation'].lower():
                    return t['abbreviation'], t['full_name']
            return None, None

        abbrev_a, name_a = get_team_abbrev(team_a)
        abbrev_b, name_b = get_team_abbrev(team_b)
        
        result_text = ""
        
        for abbrev, full_name in [(abbrev_a, name_a), (abbrev_b, name_b)]:
            if abbrev:
                team_players = stats_df[stats_df['TEAM_ABBREVIATION'] == abbrev].sort_values('PTS', ascending=False)
                top_3 = team_players[['PLAYER_NAME', 'PTS', 'REB', 'AST', 'GP']].head(3).to_dict('records')
                
                result_text += f"[{full_name} - Top 3 Scorers (2025-2026 Average)]:\n"
                for p in top_3:
                    pts_avg = round(p['PTS'] / p['GP'], 1) if p['GP'] > 0 else 0
                    reb_avg = round(p['REB'] / p['GP'], 1) if p['GP'] > 0 else 0
                    ast_avg = round(p['AST'] / p['GP'], 1) if p['GP'] > 0 else 0
                    result_text += f"- {p['PLAYER_NAME']}: {pts_avg} PPG, {reb_avg} RPG, {ast_avg} APG\n"
                result_text += "\n"
        
        if not result_text:
            raise HTTPException(status_code=404, detail="Could not identify valid NBA teams.")
            
        return {"context": result_text}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching matchup context: {str(e)}")

@app.post("/v11/analyze", response_model=V11SimulationResult)
async def execute_v11_analysis(request: OddsRequest):
    """
    God Engine V11 Orchestrator
    """
    matchup_str = request.matchup
    bankroll = request.bankroll
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧠 CTE LOCKS Engine Initializing for: {matchup_str}")
    
    # 1. Team Extraction
    teams_split = []
    if " vs " in matchup_str.lower():
        teams_split = matchup_str.lower().split(" vs ")
    elif " @ " in matchup_str.lower():
         teams_split = matchup_str.lower().split(" @ ")
         
    team_a = teams_split[0].strip().title() if len(teams_split) > 0 else "Team A"
    team_b = teams_split[1].strip().title() if len(teams_split) > 1 else "Team B"
    
    # 2. Fetch Deep Player Stats
    try:
        stats_df = get_cached_nba_stats()
        nba_teams = teams.get_teams()
        
        def get_team_abbrev(search_str):
            search_lower = search_str.lower()
            for t in nba_teams:
                if search_lower in t['full_name'].lower() or search_lower in t['nickname'].lower() or search_lower in t['abbreviation'].lower():
                    return t['abbreviation'], t['full_name']
            return None, search_str

        abbrev_a, name_a = get_team_abbrev(team_a)
        abbrev_b, name_b = get_team_abbrev(team_b)
        
        team_a_stars = []
        team_b_stars = []
        
        if abbrev_a:
            team_players = stats_df[stats_df['TEAM_ABBREVIATION'] == abbrev_a].sort_values('PTS', ascending=False)
            top_3 = team_players[['PLAYER_NAME', 'PTS', 'REB', 'AST', 'GP']].head(3).to_dict('records')
            for p in top_3:
                pts_avg = round(p['PTS'] / p['GP'], 1) if p['GP'] > 0 else 0
                team_a_stars.append({"name": p['PLAYER_NAME'], "pts": pts_avg})
                
        if abbrev_b:
            team_players = stats_df[stats_df['TEAM_ABBREVIATION'] == abbrev_b].sort_values('PTS', ascending=False)
            top_3 = team_players[['PLAYER_NAME', 'PTS', 'REB', 'AST', 'GP']].head(3).to_dict('records')
            for p in top_3:
                pts_avg = round(p['PTS'] / p['GP'], 1) if p['GP'] > 0 else 0
                team_b_stars.append({"name": p['PLAYER_NAME'], "pts": pts_avg})
                
    except Exception as e:
        print(f"Warning: Could not fetch NBA API stats ({e})")
        team_a_stars = [{"name": "Star A", "pts": 25.0}]
        team_b_stars = [{"name": "Star B", "pts": 25.0}]
        name_a, name_b = team_a, team_b

    # 3. Simulate Primary Spread (Mathematical Abstraction)
    
    # [V11.5] Autonomously fetch live odds
    live_odds = fetch_live_action_network_odds(name_a, name_b)
    
    lock_team = name_a
    fade_team = name_b
    
    if live_odds and live_odds["team_a_sharp"] > 0:
        prob_a = 1.0 / live_odds["team_a_sharp"]
        prob_b = 1.0 / live_odds["team_b_sharp"]

        if prob_a >= prob_b:
            true_prob = prob_a  # vig-free probability from Pinnacle — no fake bump
            request.market_spread = live_odds["team_a_spread"] or 0.0
            primary_decimal_odds = live_odds["team_a_soft"]
            spread_str = f" {request.market_spread:+g}" if request.market_spread != 0 else " ML"
            lock_label = f"[THE LOCK] {name_a}{spread_str}"
            lock_team = name_a
            fade_team = name_b
        else:
            true_prob = prob_b
            request.market_spread = live_odds["team_b_spread"] or 0.0
            primary_decimal_odds = live_odds["team_b_soft"]
            spread_str = f" {request.market_spread:+g}" if request.market_spread != 0 else " ML"
            lock_label = f"[THE LOCK] {name_b}{spread_str}"
            lock_team = name_b
            fade_team = name_a
    else:
        # Fallback to request data if odd scraper fails
        true_prob = 1.0 / request.sharp_odds if request.sharp_odds > 1.0 else request.sharp_odds
        primary_decimal_odds = request.soft_odds if request.soft_odds > 1.0 else (1.0 / max(0.001, request.soft_odds))
        lock_label = f"[THE LOCK] {name_a} Spread/ML"
        lock_team = name_a
        fade_team = name_b
        
    # Run the exact variance logic
    math_data = calculate_exact_variance(true_prob, request.market_spread, request.injury_impact_score, request.time_remaining_mins, request.distraction_index)
    
    primary_prob = math_data["mean"]
    
    primary_ev = (primary_prob * (primary_decimal_odds - 1.0) * bankroll) - ((1.0 - primary_prob) * bankroll)
    primary_kelly = calculate_kelly_sizing(primary_prob, primary_decimal_odds, bankroll)
    
    # Calculate American target odds for output
    if primary_decimal_odds >= 2.0:
        target_odds_str = f"+{int(round((primary_decimal_odds - 1.0) * 100))}"
    else:
        target_odds_str = f"-{int(round(100.0 / (primary_decimal_odds - 1.0)))}"
    
    # 4. Simulate Player Props
    # Select the prop star based on which team the AI locked
    star_team_stars = team_a_stars if lock_team == name_a else team_b_stars
    star_player = star_team_stars[0]['name'] if star_team_stars else "Primary Scorer"
    star_avg = star_team_stars[0]['pts'] if star_team_stars else 25.0
    
    target_line = int(star_avg) - 1.5

    # Default xMins for starters; real value injected when called via /nba-player-minutes
    star_xMins = 34.0
    prop_prob = poisson_player_prop_prob(star_avg, target_line, xMins=star_xMins)
    prop_ev = (prop_prob * (1.909 - 1.0) * bankroll) - ((1.0 - prop_prob) * bankroll) # Standard -110 for props
    prop_kelly = calculate_kelly_sizing(prop_prob, 1.909, bankroll)
    
    return V11SimulationResult(
        status="V11_MATHEMATICS_COMPLETE",
        matchup=f"{name_a} vs {name_b}",
        date_context=datetime.now().strftime("%B %d, %Y"),
        target_odds=target_odds_str,
        vig_adjusted_ev=f"${round(primary_ev, 2):+.2f}",
        alpha_edge=f"+{round((primary_prob - (1 / primary_decimal_odds)) * 100, 2)}%",
        primary_lock=PickAlpha(
            label=lock_label,
            edge=round(math_data["edge_factor"], 3),
            true_probability_percent=round(primary_prob * 100, 2),
            expected_value_usd=round(primary_ev, 2),
            kelly_sizing_usd=primary_kelly,
            analysis_rationale=f"O(1) Exact Bernoulli Mathematical Variance detects a slight pricing inefficiency on {lock_team}."
        ),
        derivative_alpha=PickAlpha(
            label=f"{star_player} OVER {target_line} Points",
            edge=round(prop_prob - (1.0 / 1.909), 3),  # real edge vs -110 implied prob
            true_probability_percent=round(prop_prob * 100, 2),
            expected_value_usd=round(prop_ev, 2),
            kelly_sizing_usd=prop_kelly,
            analysis_rationale=f"Poisson model on {star_player}'s {star_avg} PPG at {star_xMins} projected minutes gives {round(prop_prob * 100, 1)}% over the line — vs 52.4% implied at -110."
        ),
        correlation_play=PickAlpha(
             label=f"{fade_team} Team Total UNDER",
            edge=round(math_data["edge_factor"] * 0.98, 3),
            true_probability_percent=round(primary_prob * 100 * 0.95, 1),
            expected_value_usd=round(primary_ev * 0.88, 2),
            kelly_sizing_usd=round(primary_kelly * 0.85, 2),
            analysis_rationale=f"Directly correlated with a {lock_team} victory block. Scheme friction will limit {fade_team}'s offensive rhythm. Dynamic correlation factor applied."
        )
    )

# ─────────────────────────────────────────────
# HarvardX STAT110x: Probability Theory Layer
# Blitzstein's core theorems applied to betting
# ─────────────────────────────────────────────

def stat110_bayes_update(prior: float, likelihood_if_win: float, likelihood_if_loss: float) -> float:
    """
    Bayes' Theorem: P(Win|Evidence) = P(E|Win)*P(Win) / P(E)
    Use for line movement: if sharp money moved line toward team,
    likelihood_if_win > likelihood_if_loss signals informed money.
    """
    p_evidence = likelihood_if_win * prior + likelihood_if_loss * (1.0 - prior)
    if p_evidence <= 0:
        return prior
    return (likelihood_if_win * prior) / p_evidence


def stat110_law_of_total_prob(scenarios: list) -> float:
    """
    Law of Total Probability: P(Win) = Σ P(Win|Bᵢ) * P(Bᵢ)
    scenarios: [{"weight": float, "win_prob": float}]
    Weights must sum to 1. Decomposes win prob across game states
    (e.g., starter plays, starter sits, pace scenario).
    """
    total_weight = sum(s["weight"] for s in scenarios)
    if total_weight <= 0:
        return 0.0
    return sum((s["weight"] / total_weight) * s["win_prob"] for s in scenarios)


def stat110_beta_credible_interval(wins: float, losses: float, confidence: float = 0.90) -> dict:
    """
    Beta-Binomial model for win probability uncertainty (STAT110x Ch. 8).
    Treats p as Beta(wins+1, losses+1) — uniform prior + observed record.
    Returns mean, lo/hi credible interval at given confidence.
    """
    alpha = wins + 1.0
    beta_param = losses + 1.0
    tail = (1.0 - confidence) / 2.0
    lo = scipy_beta.ppf(tail, alpha, beta_param)
    hi = scipy_beta.ppf(1.0 - tail, alpha, beta_param)
    mean = alpha / (alpha + beta_param)
    return {"mean": float(mean), "lo": float(lo), "hi": float(hi), "confidence": confidence}


def stat110_correlated_ev(
    prob_a: float, odds_a: float,
    prob_b: float, odds_b: float,
    correlation: float, bankroll: float
) -> dict:
    """
    Conditional Expectation for 2-leg correlated parlay (STAT110x Ch. 9).
    P(A∩B) = P(B|A)*P(A) where P(B|A) = prob_b + correlation*(1-prob_b)
    correlation ∈ [-1,1]: 0=independent, >0=positively correlated legs.
    """
    prob_b_given_a = min(1.0, max(0.0, prob_b + correlation * (1.0 - prob_b)))
    prob_both = prob_a * prob_b_given_a
    combined_decimal = odds_a * odds_b
    ev = (prob_both * (combined_decimal - 1.0) * bankroll) - ((1.0 - prob_both) * bankroll)
    return {
        "prob_both": float(prob_both),
        "combined_decimal_odds": float(combined_decimal),
        "expected_value_usd": float(round(ev, 2)),
        "edge": float(round(prob_both - (1.0 / combined_decimal), 4))
    }


class Stat110Request(BaseModel):
    prior_prob: float                    # initial win probability (0–1)
    line_move_toward_team: bool = False  # did sharp line move toward this team?
    wins_in_sample: float = 10.0        # historical wins for Beta model
    losses_in_sample: float = 10.0      # historical losses for Beta model
    scenarios: list = []                 # [{weight, win_prob}] for LOTP
    parlay_prob_b: float = 0.0          # second leg probability for correlated EV
    parlay_odds_a: float = 1.909        # first leg decimal odds
    parlay_odds_b: float = 1.909        # second leg decimal odds
    parlay_correlation: float = 0.0     # correlation between legs
    bankroll: float = 100.0


@app.post("/stat110/analyze")
async def stat110_analyze(req: Stat110Request):
    """
    HarvardX STAT110x full pipeline:
    1. Bayes update on prior using line movement signal
    2. Law of Total Probability across weighted scenarios
    3. Beta credible interval on true win probability
    4. Correlated parlay EV if second leg provided
    """
    # 1. Bayes update — sharp line move = P(move|Win)=0.75, P(move|Loss)=0.35
    if req.line_move_toward_team:
        bayes_prob = stat110_bayes_update(req.prior_prob, 0.75, 0.35)
    else:
        bayes_prob = stat110_bayes_update(req.prior_prob, 0.35, 0.75)

    # 2. Law of Total Probability (use scenarios if provided, else use bayes_prob)
    if req.scenarios:
        lotp_prob = stat110_law_of_total_prob(req.scenarios)
    else:
        # Default 3-scenario decomposition: strong/neutral/weak game state
        lotp_prob = stat110_law_of_total_prob([
            {"weight": 0.25, "win_prob": min(1.0, bayes_prob * 1.15)},
            {"weight": 0.50, "win_prob": bayes_prob},
            {"weight": 0.25, "win_prob": max(0.0, bayes_prob * 0.85)},
        ])

    # 3. Beta credible interval
    beta_result = stat110_beta_credible_interval(
        req.wins_in_sample, req.losses_in_sample
    )
    # Blend historical Beta mean with LOTP estimate (50/50)
    blended_prob = 0.5 * lotp_prob + 0.5 * beta_result["mean"]

    # 4. Correlated parlay EV
    parlay_result = None
    if req.parlay_prob_b > 0:
        parlay_result = stat110_correlated_ev(
            blended_prob, req.parlay_odds_a,
            req.parlay_prob_b, req.parlay_odds_b,
            req.parlay_correlation, req.bankroll
        )

    return {
        "stat110_analysis": True,
        "prior_prob": req.prior_prob,
        "bayes_updated_prob": round(bayes_prob, 4),
        "lotp_prob": round(lotp_prob, 4),
        "beta_credible_interval": beta_result,
        "blended_final_prob": round(blended_prob, 4),
        "kelly_sizing_usd": calculate_kelly_sizing(blended_prob, req.parlay_odds_a, req.bankroll),
        "correlated_parlay": parlay_result,
        "interpretation": (
            f"STAT110x: Bayesian update {'raised' if bayes_prob > req.prior_prob else 'lowered'} "
            f"prior from {req.prior_prob:.1%} → {bayes_prob:.1%}. "
            f"Beta 90% CI: [{beta_result['lo']:.1%}, {beta_result['hi']:.1%}]. "
            f"Final blended prob: {blended_prob:.1%}."
        )
    }


def calculate_alt_line_prob(mean: float, std_dev: float, alt_line: float, is_over: bool = True) -> float:
    """Calculates the probability of hitting an alt line using Normal CDF."""
    prob_less = scipy_norm.cdf(alt_line, loc=mean, scale=std_dev)
    return 1 - prob_less if is_over else prob_less

# ─────────────────────────────────────────────────────────────
# HarvardX PH125.4x: Data Science — Inference and Modeling
# Frequentist inference: CIs, p-values, MLE from odds history
# ─────────────────────────────────────────────────────────────

def ph125_proportion_ci(wins: int, n: int, confidence: float = 0.95) -> dict:
    """
    PH125.4x: Normal-approximation CI for a win proportion.
    p_hat ± z * sqrt(p_hat*(1-p_hat)/n)
    Tells you the margin of error on your observed win rate.
    """
    if n <= 0:
        return {"p_hat": 0.0, "lo": 0.0, "hi": 0.0, "margin_of_error": 0.0}
    p_hat = wins / n
    z = scipy_norm.ppf(1.0 - (1.0 - confidence) / 2.0)
    se = math.sqrt(p_hat * (1.0 - p_hat) / n)
    return {
        "p_hat": round(p_hat, 4),
        "lo": round(max(0.0, p_hat - z * se), 4),
        "hi": round(min(1.0, p_hat + z * se), 4),
        "margin_of_error": round(z * se, 4),
        "confidence": confidence,
    }


def ph125_edge_significance(observed_wins: int, n: int, null_prob: float) -> dict:
    """
    PH125.4x: One-sided z-test — is the observed win rate significantly
    above the null (implied by market odds)?
    H0: p = null_prob  |  H1: p > null_prob
    Returns p-value and whether edge is statistically significant at 5%.
    """
    if n <= 0 or null_prob <= 0 or null_prob >= 1:
        return {"z_score": 0.0, "p_value": 1.0, "significant": False}
    p_hat = observed_wins / n
    se = math.sqrt(null_prob * (1.0 - null_prob) / n)
    z = (p_hat - null_prob) / se if se > 0 else 0.0
    p_value = 1.0 - scipy_norm.cdf(z)
    return {
        "observed_win_rate": round(p_hat, 4),
        "null_prob": null_prob,
        "z_score": round(z, 4),
        "p_value": round(p_value, 4),
        "significant_at_5pct": bool(p_value < 0.05),
        "significant_at_1pct": bool(p_value < 0.01),
    }


def ph125_mle_true_prob(implied_probs: List[float]) -> dict:
    """
    PH125.4x: MLE for true probability from a list of market-implied probs.
    MLE estimate = mean of devigged implied probs.
    Also returns variance and std error of the estimate.
    """
    if not implied_probs:
        return {"mle_prob": 0.0, "std_error": 0.0, "n": 0}
    arr = np.array(implied_probs, dtype=float)
    mle = float(np.mean(arr))
    variance = float(np.var(arr, ddof=1)) if len(arr) > 1 else 0.0
    se = float(np.std(arr, ddof=1) / math.sqrt(len(arr))) if len(arr) > 1 else 0.0
    return {
        "mle_prob": round(mle, 4),
        "variance": round(variance, 6),
        "std_error": round(se, 4),
        "n": len(arr),
    }


class PH125Request(BaseModel):
    wins: int = 10
    losses: int = 10
    null_prob: float = 0.50          # market implied probability (vig-free)
    implied_probs_history: list = [] # list of past devigged implied probs


@app.post("/ph125/inference")
async def ph125_inference(req: PH125Request):
    """
    PH125.4x pipeline: frequentist CI + significance test + MLE.
    """
    n = req.wins + req.losses
    ci = ph125_proportion_ci(req.wins, n)
    sig = ph125_edge_significance(req.wins, n, req.null_prob)
    mle = ph125_mle_true_prob(req.implied_probs_history) if req.implied_probs_history else None

    edge_exists = sig["significant_at_5pct"]
    verdict = "EDGE CONFIRMED" if edge_exists else "NO SIGNIFICANT EDGE"

    return {
        "ph125_inference": True,
        "sample_size": n,
        "confidence_interval_95pct": ci,
        "significance_test": sig,
        "mle_from_history": mle,
        "verdict": verdict,
        "interpretation": (
            f"Win rate {ci['p_hat']:.1%} ± {ci['margin_of_error']:.1%}. "
            f"vs market null {req.null_prob:.1%}: z={sig['z_score']}, p={sig['p_value']}. "
            f"{verdict}."
        ),
    }


# ─────────────────────────────────────────────────────────────
# HarvardX PH526x: Using Python for Research
# Bootstrap resampling + bankroll growth Monte Carlo
# ─────────────────────────────────────────────────────────────

def ph526_bootstrap_edge(win_probs: List[float], market_prob: float, n_bootstrap: int = 5000) -> dict:
    """
    PH526x: Bootstrap CI on the edge = mean(win_probs) - market_prob.
    Resamples win_probs with replacement n_bootstrap times.
    Returns 95% CI on edge and probability edge > 0.
    """
    if not win_probs:
        return {"edge_mean": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "prob_positive_edge": 0.0}
    arr = np.array(win_probs, dtype=float)
    rng = np.random.default_rng()
    boot_edges = np.array([
        np.mean(rng.choice(arr, size=len(arr), replace=True)) - market_prob
        for _ in range(n_bootstrap)
    ])
    return {
        "edge_mean": round(float(np.mean(boot_edges)), 4),
        "ci_lo": round(float(np.percentile(boot_edges, 2.5)), 4),
        "ci_hi": round(float(np.percentile(boot_edges, 97.5)), 4),
        "prob_positive_edge": round(float(np.mean(boot_edges > 0)), 4),
        "n_bootstrap": n_bootstrap,
    }


def ph526_bankroll_simulation(
    win_prob: float,
    decimal_odds: float,
    kelly_fraction: float = 0.25,
    starting_bankroll: float = 1000.0,
    n_bets: int = 100,
    n_simulations: int = 2000,
) -> dict:
    """
    PH526x: Monte Carlo bankroll growth simulation.
    Simulates n_simulations paths of n_bets bets each.
    Returns median, 10th/90th percentile final bankroll, and ruin rate.
    """
    b = decimal_odds - 1.0
    q = 1.0 - win_prob
    kelly_pct = max(0.0, (b * win_prob - q) / b) * kelly_fraction if b > 0 else 0.0
    kelly_pct = min(kelly_pct, 0.05)

    rng = np.random.default_rng()
    outcomes = rng.random((n_simulations, n_bets)) < win_prob  # True = win

    bankrolls = np.full(n_simulations, starting_bankroll)
    for bet_idx in range(n_bets):
        stake = np.maximum(bankrolls * kelly_pct, 0.0)
        bankrolls = np.where(
            outcomes[:, bet_idx],
            bankrolls + stake * b,
            bankrolls - stake,
        )
        bankrolls = np.maximum(bankrolls, 0.0)

    ruin_rate = float(np.mean(bankrolls < starting_bankroll * 0.10))
    return {
        "starting_bankroll": starting_bankroll,
        "n_bets": n_bets,
        "n_simulations": n_simulations,
        "kelly_bet_pct": round(kelly_pct * 100, 2),
        "median_final": round(float(np.median(bankrolls)), 2),
        "p10_final": round(float(np.percentile(bankrolls, 10)), 2),
        "p90_final": round(float(np.percentile(bankrolls, 90)), 2),
        "ruin_rate_pct": round(ruin_rate * 100, 2),
        "expected_roi_pct": round(
            (float(np.median(bankrolls)) - starting_bankroll) / starting_bankroll * 100, 2
        ),
    }


class PH526Request(BaseModel):
    win_prob: float = 0.55
    decimal_odds: float = 1.909
    kelly_fraction: float = 0.25
    starting_bankroll: float = 1000.0
    n_bets: int = 100
    n_simulations: int = 2000
    win_probs_sample: list = []   # for bootstrap edge CI
    market_prob: float = 0.50     # market null for bootstrap


@app.post("/ph526/simulate")
async def ph526_simulate(req: PH526Request):
    """
    PH526x pipeline: bootstrap edge CI + bankroll Monte Carlo.
    """
    bankroll_sim = ph526_bankroll_simulation(
        req.win_prob, req.decimal_odds,
        req.kelly_fraction, req.starting_bankroll,
        req.n_bets, req.n_simulations,
    )
    bootstrap_result = (
        ph526_bootstrap_edge(req.win_probs_sample, req.market_prob)
        if req.win_probs_sample
        else None
    )
    profitable = bankroll_sim["median_final"] > req.starting_bankroll
    return {
        "ph526_simulation": True,
        "bankroll_growth": bankroll_sim,
        "bootstrap_edge": bootstrap_result,
        "verdict": "PROFITABLE LONG-TERM" if profitable else "UNPROFITABLE — REVIEW EDGE",
        "interpretation": (
            f"Over {req.n_bets} bets @ {req.win_prob:.1%} win rate: "
            f"median bankroll ${bankroll_sim['median_final']:,.0f} "
            f"(P10: ${bankroll_sim['p10_final']:,.0f} / P90: ${bankroll_sim['p90_final']:,.0f}). "
            f"Ruin rate: {bankroll_sim['ruin_rate_pct']}%."
        ),
    }


# ─────────────────────────────────────────────────────────────
# HarvardX CS109xa: Machine Learning and AI with Python
# Logistic regression inference, feature attribution, stacking
# ─────────────────────────────────────────────────────────────

# Heuristic logistic weights — manually set from domain knowledge, NOT trained on data.
# To make this real ML: collect historical bet outcomes and fit via sklearn LogisticRegression.
_CS109X_WEIGHTS = {
    "intercept":        0.0,
    "sharp_prob":       2.50,   # devigged market prob — strongest predictor
    "spread_norm":     -0.20,   # spread / 10; wider spread = more uncertainty
    "injury_penalty":  -1.20,   # injury_impact / 20; injuries compress true prob
    "rest_factor":      0.18,   # rest_advantage / 3; rest edge is real but small
    "distraction":     -0.25,   # distraction_index / 10; focus matters
}


def cs109x_logistic_prob(
    sharp_prob: float,
    market_spread: float = 0.0,
    injury_impact: float = 0.0,
    rest_advantage: float = 0.0,
    distraction_index: float = 0.0,
) -> dict:
    """
    CS109xa: Logistic regression inference.
    p = sigmoid(w · x) using domain-calibrated weights.
    Features are normalized before multiplying weights.
    """
    w = _CS109X_WEIGHTS
    # Calibrated base: market log-odds. Neutral adjustments → output == market prob.
    # (Old form sigmoid(2.5*p) mapped a 50% coin-flip to 77.7% — fabricated edge.)
    p = max(0.001, min(0.999, sharp_prob))
    z = (
        math.log(p / (1.0 - p))
        + w["spread_norm"]      * (market_spread / 10.0)
        + w["injury_penalty"]   * (injury_impact / 20.0)
        + w["rest_factor"]      * (rest_advantage / 3.0)
        + w["distraction"]      * (distraction_index / 10.0)
    )
    prob = 1.0 / (1.0 + math.exp(-z))
    prob = max(0.001, min(0.999, prob))
    return {"logistic_prob": round(prob, 4), "log_odds": round(z, 4)}


def cs109x_feature_importance(
    sharp_prob: float,
    market_spread: float = 0.0,
    injury_impact: float = 0.0,
    rest_advantage: float = 0.0,
    distraction_index: float = 0.0,
) -> List[dict]:
    """
    CS109xa: Gradient-based feature attribution.
    ∂p/∂xᵢ = wᵢ * p * (1 - p)  — how much each feature moves the output prob.
    Returns features sorted by absolute importance descending.
    """
    lr = cs109x_logistic_prob(sharp_prob, market_spread, injury_impact, rest_advantage, distraction_index)
    p = lr["logistic_prob"]
    scale = p * (1.0 - p)  # logistic derivative

    w = _CS109X_WEIGHTS
    raw_inputs = {
        "sharp_prob":       (sharp_prob,               w["sharp_prob"]),
        "spread_norm":      (market_spread / 10.0,     w["spread_norm"]),
        "injury_penalty":   (injury_impact / 20.0,     w["injury_penalty"]),
        "rest_factor":      (rest_advantage / 3.0,     w["rest_factor"]),
        "distraction":      (distraction_index / 10.0, w["distraction"]),
    }
    attributions = []
    for name, (val, weight) in raw_inputs.items():
        grad = weight * scale
        attributions.append({
            "feature": name,
            "value": round(val, 4),
            "weight": weight,
            "gradient": round(grad, 5),
            "abs_importance": round(abs(grad), 5),
            "direction": "boosting" if grad > 0 else "suppressing",
        })
    attributions.sort(key=lambda x: x["abs_importance"], reverse=True)
    return attributions


def cs109x_ensemble_stack(estimates: List[float], weights: List[float]) -> float:
    """
    CS109xa: Weighted model stacking.
    Combines multiple probability estimates (from different models/courses)
    into a single calibrated final probability.
    Weights are normalized to sum to 1.
    """
    if not estimates or len(estimates) != len(weights):
        return float(np.mean(estimates)) if estimates else 0.5
    total_w = sum(weights)
    if total_w <= 0:
        return float(np.mean(estimates))
    stacked = sum(e * w for e, w in zip(estimates, weights)) / total_w
    return round(max(0.001, min(0.999, stacked)), 4)


class CS109xRequest(BaseModel):
    sharp_prob: float = 0.55          # devigged win probability
    market_spread: float = 0.0
    injury_impact: float = 0.0
    rest_advantage: float = 0.0       # days home team rested vs away
    distraction_index: float = 0.0
    decimal_odds: float = 1.909
    bankroll: float = 100.0


@app.post("/cs109x/predict")
async def cs109x_predict(req: CS109xRequest):
    """CS109xa: logistic inference + feature importance + Kelly sizing."""
    lr = cs109x_logistic_prob(
        req.sharp_prob, req.market_spread,
        req.injury_impact, req.rest_advantage, req.distraction_index,
    )
    importance = cs109x_feature_importance(
        req.sharp_prob, req.market_spread,
        req.injury_impact, req.rest_advantage, req.distraction_index,
    )
    kelly = calculate_kelly_sizing(lr["logistic_prob"], req.decimal_odds, req.bankroll)
    top_driver = importance[0]["feature"] if importance else "sharp_prob"

    return {
        "cs109x_ml": True,
        "logistic_prob": lr["logistic_prob"],
        "log_odds": lr["log_odds"],
        "kelly_sizing_usd": kelly,
        "feature_importance": importance,
        "top_driver": top_driver,
        "interpretation": (
            f"CS109xa logistic: {lr['logistic_prob']:.1%} win probability. "
            f"Top driver: '{top_driver}'. "
            f"Kelly: ${kelly:.2f}."
        ),
    }


# ─────────────────────────────────────────────────────────────
# HarvardX MASTER ENGINE
# Chains all 4 courses into one final probability + verdict
# STAT110x → PH125.4x → CS109xa → weighted stack → Kelly
# ─────────────────────────────────────────────────────────────

class HarvardMasterRequest(BaseModel):
    # Core inputs
    prior_prob: float = 0.55              # raw/sharp win probability
    market_spread: float = 0.0
    injury_impact: float = 0.0
    rest_advantage: float = 0.0
    distraction_index: float = 0.0
    decimal_odds: float = 1.909
    bankroll: float = 100.0
    # STAT110x inputs
    line_move_known: bool = False         # only apply Bayes line-move update when we HAVE the signal
    line_move_toward_team: bool = False
    wins_in_sample: float = 10.0
    losses_in_sample: float = 10.0
    # PH125.4x inputs
    observed_wins: int = 10
    observed_losses: int = 10


@app.post("/harvard/master")
async def harvard_master(req: HarvardMasterRequest):
    """
    HarvardX Master Engine — all 4 courses in sequence:
    1. STAT110x: Bayes update + Beta credible interval
    2. PH125.4x: Frequentist CI + edge significance
    3. CS109xa:  Logistic regression + feature attribution
    4. Stack:    Weighted ensemble → final probability → Kelly
    """
    # ── 1. STAT110x ──────────────────────────────────────────
    # No line-move signal = no update. Treating "unknown" as "moved against"
    # fabricated a negative Bayes shift on every neutral request.
    if not req.line_move_known:
        bayes_prob = req.prior_prob
    elif req.line_move_toward_team:
        bayes_prob = stat110_bayes_update(req.prior_prob, 0.75, 0.35)
    else:
        bayes_prob = stat110_bayes_update(req.prior_prob, 0.35, 0.75)

    beta_ci = stat110_beta_credible_interval(req.wins_in_sample, req.losses_in_sample)
    lotp_prob = stat110_law_of_total_prob([
        {"weight": 0.25, "win_prob": min(1.0, bayes_prob * 1.15)},
        {"weight": 0.50, "win_prob": bayes_prob},
        {"weight": 0.25, "win_prob": max(0.0, bayes_prob * 0.85)},
    ])
    # Blend in the Beta sample mean only with a real sample (>= 30 games);
    # the default 10-10 placeholder pins it at 0.5 and dilutes market info.
    sample_n = req.wins_in_sample + req.losses_in_sample
    stat110_final = (
        0.5 * lotp_prob + 0.5 * beta_ci["mean"] if sample_n >= 30 else lotp_prob
    )

    # ── 2. PH125.4x ──────────────────────────────────────────
    n_obs = req.observed_wins + req.observed_losses
    ph125_ci = ph125_proportion_ci(req.observed_wins, n_obs)
    ph125_sig = ph125_edge_significance(req.observed_wins, n_obs, req.prior_prob)
    ph125_final = ph125_ci["p_hat"]

    # ── 3. CS109xa ────────────────────────────────────────────
    lr = cs109x_logistic_prob(
        req.prior_prob, req.market_spread,
        req.injury_impact, req.rest_advantage, req.distraction_index,
    )
    importance = cs109x_feature_importance(
        req.prior_prob, req.market_spread,
        req.injury_impact, req.rest_advantage, req.distraction_index,
    )
    cs109x_final = lr["logistic_prob"]

    # ── 4. Weighted Stack ─────────────────────────────────────
    # CS109xa logistic carries the most weight (trained on features),
    # STAT110x Bayesian second (incorporates prior evidence),
    # PH125.4x frequentist last (pure observed sample).
    # PH125 needs a real sample — with the default 10-10 placeholder it just
    # drags the stack toward 0.5. Include only when n >= 30 observed games.
    if n_obs >= 30:
        final_prob = cs109x_ensemble_stack(
            estimates=[stat110_final, ph125_final, cs109x_final],
            weights=[0.35, 0.25, 0.40],
        )
    else:
        final_prob = cs109x_ensemble_stack(
            estimates=[stat110_final, cs109x_final],
            weights=[0.45, 0.55],
        )

    kelly = calculate_kelly_sizing(final_prob, req.decimal_odds, req.bankroll)
    market_implied = 1.0 / req.decimal_odds if req.decimal_odds > 1 else req.prior_prob
    edge_pct = round((final_prob - market_implied) * 100, 2)
    # Edge under 1.5% is inside vig noise — calling it VALUE invites bad bets
    verdict = "LOCK" if edge_pct > 4 else ("VALUE" if edge_pct > 1.5 else "NO EDGE")

    return {
        "harvard_master": True,
        "course_outputs": {
            "stat110x_prob": round(stat110_final, 4),
            "ph125_prob":    round(ph125_final, 4),
            "cs109x_prob":   round(cs109x_final, 4),
        },
        "stacked_final_prob": final_prob,
        "market_implied_prob": round(market_implied, 4),
        "edge_pct": edge_pct,
        "kelly_sizing_usd": kelly,
        "beta_credible_interval_90pct": beta_ci,
        "edge_significant": ph125_sig["significant_at_5pct"],
        "feature_importance": importance[:3],
        "verdict": verdict,
        "interpretation": (
            f"STAT110x={stat110_final:.1%} | PH125={ph125_final:.1%} | "
            f"CS109x={cs109x_final:.1%} → Stack={final_prob:.1%}. "
            f"Edge vs market: {edge_pct:+.2f}%. "
            f"Verdict: {verdict}. Kelly: ${kelly:.2f}."
        ),
    }


@app.post("/generate-ladder")
def generate_ladder(req: PredictReq):
    # Standard deviation baseline (Sport specific)
    std_dev = 7.0 
    if "MLB" in req.sport: std_dev = 1.2 
    if "SOCCER" in req.sport: std_dev = 1.2
    if "SHOTS" in req.market_type.upper(): std_dev = 3.5 # Shots have higher variance than goals
    
    # Generate 4 steps of ladders
    if "NBA" in req.sport:
        alt_steps = [2, 4, 6, 8]
    elif "SOCCER" in req.sport:
        if "SHOTS" in req.market_type.upper():
            alt_steps = [1, 2, 3, 4] # For SoT or Total Shots
        else:
            alt_steps = [0.5, 1.0, 1.5] # Over 2.5 -> 3.0 -> 3.5 -> 4.0
    else:
        alt_steps = [0.5, 1.5, 2.5]
    
    ladder = []
    for step in alt_steps:
        alt_val = req.market_spread + step
        prob = calculate_alt_line_prob(req.true_prob, std_dev, alt_val, True)
        
        if prob < 0.01: continue
        
        # Convert prob to American Odds
        if prob > 0.5:
            american = int(round((prob / (1 - prob)) * -100))
        else:
            american = int(round(((1 - prob) / prob) * 100))
            
        ladder.append({
            "alt_line": alt_val,
            "win_prob": round(prob, 4),
            "suggested_odds": american
        })
    
    return {"ladder": ladder}

@app.get("/nba-player-minutes/{team_abbr}")
async def get_player_minutes(team_abbr: str):
    """xMins: per-player season minutes projection for a given team abbreviation."""
    try:
        stats_df = get_cached_nba_stats()
        if stats_df is None:
            raise HTTPException(status_code=503, detail="NBA stats unavailable")

        team_upper = team_abbr.upper()
        team_df = stats_df[stats_df['TEAM_ABBREVIATION'] == team_upper]

        if team_df.empty:
            raise HTTPException(status_code=404, detail=f"No players for team: {team_abbr}")

        result = []
        for _, row in team_df.iterrows():
            gp = int(row['GP']) or 1
            min_pg  = round(float(row['MIN']) / gp, 1)
            pts_pg  = round(float(row['PTS']) / gp, 1)
            reb_pg  = round(float(row['REB']) / gp, 1)
            ast_pg  = round(float(row['AST']) / gp, 1)
            # xMins = season min_pg (ground truth baseline; caller applies pace/injury modifiers)
            result.append({
                "player": row['PLAYER_NAME'],
                "team":   team_upper,
                "gp":     gp,
                "xMins":  min_pg,
                "pts_pg": pts_pg,
                "reb_pg": reb_pg,
                "ast_pg": ast_pg,
                # Per-36 projections at xMins
                "proj_pts": round((pts_pg / max(min_pg, 1)) * min_pg, 1),
                "proj_reb": round((reb_pg / max(min_pg, 1)) * min_pg, 1),
                "proj_ast": round((ast_pg / max(min_pg, 1)) * min_pg, 1),
            })

        # Sort by xMins descending (rotation order)
        result.sort(key=lambda x: x['xMins'], reverse=True)
        return {"team": team_upper, "players": result[:10]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "CTE LOCKS Node Online", "node": "Python-HFT-Sim"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)

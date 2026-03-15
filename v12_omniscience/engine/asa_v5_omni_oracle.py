"""
ASA v5.1 + QSA v4.0: THE COMPLETE SHARP EXECUTION ENGINE
VERSION: 5.1-OMNISCIENCE [VIDEO-UPGRADED]

Pipeline (7 Steps):
1. ESPN Data Crawl + Injury Line-Gap Detection  (Video 4)
2. Sentiment Scanner / Public Trap              (ASA v5.0)
3. ELO Rating System                            (Video 3 — #1 predictive feature)
4. Random Forest (100 Trees, ELO as top feat)   (Video 3)
5. Monte Carlo Atomic Simulation (10k iters)    (QSA v4.0)
6. Quant Market Model + Line Shopping           (Video 5)
7. +EV Filter + Limit Order                     (ASA v5.0)
"""
import numpy as np
import random
import time
import json

from v12_omniscience.engine.random_forest_engine import RandomForestDecisionEngine
from v12_omniscience.engine.espn_data_crawler import ESPNDataCrawler
from v12_omniscience.engine.sentiment_scanner import SentimentScanner
from v12_omniscience.engine.ev_market_filter import EVMarketFilter
from v12_omniscience.engine.elo_system import ELOSystem
from v12_omniscience.engine.injury_line_gap import InjuryLineGapDetector
from v12_omniscience.engine.quant_market_model import QuantMarketModel


class ASA_V5_OmniOracle:
    """
    ANTIGRAVITY SHARP ARCHITECT (ASA) v5.1 [VIDEO-UPGRADED]
    7-step pipeline incorporating all YouTube video insights.
    """

    VERSION = "5.1-OMNISCIENCE-VIDEO-UPGRADED"
    SIM_ITERATIONS = 10_000

    def __init__(self):
        self.rf = RandomForestDecisionEngine()
        self.espn = ESPNDataCrawler()
        self.sentiment = SentimentScanner()
        self.ev = EVMarketFilter()
        self.elo = ELOSystem()
        self.injury_gap = InjuryLineGapDetector()
        self.quant = QuantMarketModel()

    # ─────────────────────────────────────────────────────────────
    # STEP 1: ESPN Data Crawl
    # ─────────────────────────────────────────────────────────────
    def _step1_data_crawl(self, sport, team_a_name, team_b_name, request_data):
        """Pull live odds, injuries, and momentum from ESPN."""
        # Fetch odds for this sport
        live_odds = self.espn.get_game_odds(sport)

        # Try to find this matchup
        matched_odds = None
        for game_name, odds in live_odds.items():
            if team_a_name.lower() in game_name.lower() or team_b_name.lower() in game_name.lower():
                matched_odds = odds
                break

        injuries = self.espn.get_injury_report(sport)
        momentum_a = self.espn.calculate_momentum_velocity(sport, team_a_name)
        momentum_b = self.espn.calculate_momentum_velocity(sport, team_b_name)

        market_decimal = 1.91  # default
        if matched_odds and matched_odds.get("ml_home"):
            try:
                market_decimal = self.ev.american_to_decimal(int(matched_odds["ml_home"]))
            except:
                pass

        # Override with user-provided odds if given
        if request_data.get("market_odds"):
            market_decimal = float(request_data["market_odds"])

        return {
            "impact_delta": injuries.get("impact_delta", 1.0),
            "injury_detail": injuries.get("details", "NONE_CRITICAL"),
            "stadium": request_data.get("stadium", "STANDARD"),
            "market_decimal": market_decimal,
            "momentum_a": momentum_a,
            "momentum_b": momentum_b,
            "matched_odds": matched_odds or {}
        }

    # ─────────────────────────────────────────────────────────────
    # STEP 2: Sentiment Analysis
    # ─────────────────────────────────────────────────────────────
    def _step2_sentiment(self, news_text, team_a_name, public_pct=0.5):
        sentiment = self.sentiment.scan_headlines(news_text)
        revenge = self.sentiment.detect_revenge_arc(news_text, team_a_name)
        trap = self.sentiment.detect_trap_game(news_text)
        return {
            **sentiment,
            "REVENGE": revenge,
            "IS_TRAP_GAME": trap,
            "public_pct": public_pct
        }

    # ─────────────────────────────────────────────────────────────
    # STEP 3: ELO Rating System (Video 3 — top predictive feature)
    # ─────────────────────────────────────────────────────────────
    def _step3_elo(self, team_a: str, team_b: str) -> dict:
        """ELO is the single strongest predictive signal (Video 3)."""
        return self.elo.compare(team_a, team_b)

    # ─────────────────────────────────────────────────────────────
    # STEP 4: Random Forest (100 Trees) — ELO as top feature
    # ─────────────────────────────────────────────────────────────
    def _step4_random_forest(self, team_a_data, team_b_data, crawl_data, elo_result):
        """Random Forest now uses ELO as primary feature (Video 3 insight)."""
        features_a = self.rf.build_features({
            **team_a_data,
            "momentum":        crawl_data["momentum_a"],
            "fatigue":         1.0 - crawl_data["impact_delta"],
            "form":            elo_result["elo_win_prob_a"],   # ELO as proxy for form
            "key_player":      crawl_data["impact_delta"],
        })
        features_b = self.rf.build_features({
            **team_b_data,
            "momentum":        crawl_data["momentum_b"],
            "form":            elo_result["elo_win_prob_b"],
            "key_player":      1.0,
        })
        return self.rf.run_forest(features_a, features_b)

    # ─────────────────────────────────────────────────────────────
    # STEP 5: Monte Carlo Atomic Simulation
    # ─────────────────────────────────────────────────────────────
    def _step4_monte_carlo(self, sport, power_a, power_b, cfi_mult):
        win_a = 0
        pivot_swings = []

        for sim in range(self.SIM_ITERATIONS):
            score_a = 0
            score_b = 0
            prob_history = []

            duration = 90 if sport in ["SOCCER", "MLS"] else (48 if sport in ["NBA", "WNBA"] else 60)

            for t in range(1, duration + 1):
                fatigue_curve = (t / duration) * 0.25
                p_a = (power_a / duration) * cfi_mult * (1 + fatigue_curve)
                p_b = (power_b / duration) * (1.0 - fatigue_curve * 0.5)
                if random.random() < p_a: score_a += 1
                if random.random() < p_b: score_b += 1
                if sim < 200:
                    prob_history.append((score_a - score_b) * 0.1)

            if score_a > score_b:
                win_a += 1
            if sim < 200 and len(prob_history) > 1:
                deltas = np.diff(prob_history)
                if len(deltas) > 0:
                    pivot_swings.append(int(np.argmax(np.abs(deltas))) + 1)

        true_prob = win_a / self.SIM_ITERATIONS
        avg_pivot = int(np.mean(pivot_swings)) if pivot_swings else (duration // 2)

        # Match script based on probability
        if true_prob > 0.65:
            script = "Team A controls the pace from the start. Expect early dominance to suppress Team B's rhythm."
        elif true_prob < 0.40:
            script = "Team B carries superior form. Look for counter-attack exploitation as Team A over-commits."
        else:
            script = "High-variance matchup. Tactical adjustments at the half will be decisive."

        return {
            "true_prob": round(true_prob, 4),
            "pivot_minute": avg_pivot,
            "match_script": script
        }

    # ─────────────────────────────────────────────────────────────
    # STEP 6: Quant Market Model + Line Shopping (Video 5)
    # ─────────────────────────────────────────────────────────────
    def _step6_quant(self, blended_prob: float, odds_across_books: dict) -> dict:
        """Video 5: Compare model prob vs market, shop best odds."""
        if not odds_across_books:
            return {"QUANT_VERDICT": "NO_BOOK_DATA", "LINE_SHOP": {}}
        return self.quant.quant_edge_analysis(blended_prob, odds_across_books)

    # ─────────────────────────────────────────────────────────────
    # STEP 7: +EV Market Filter + Limit Order
    # ─────────────────────────────────────────────────────────────
    def _step5_ev_filter(self, true_prob, market_decimal, bankroll=1000.0):
        return self.ev.analyze(true_prob, market_decimal, bankroll)

    # ─────────────────────────────────────────────────────────────
    # MASTER ORCHESTRATOR
    # ─────────────────────────────────────────────────────────────
    def analyze(self, request: dict) -> dict:
        """
        Full ASA v5.0 Omni-Oracle pipeline.
        Input: dict with matchup, sport, team data, news text, market odds.
        Output: Omni-Oracle formatted result.
        """
        t0 = time.time()

        sport    = request.get("sport", "NBA").upper()
        matchup  = request.get("matchup", "UNKNOWN vs UNKNOWN")
        parts    = matchup.split("vs")
        team_a   = parts[0].strip() if len(parts) > 0 else "Team A"
        team_b   = parts[1].strip() if len(parts) > 1 else "Team B"

        team_a_data = request.get("team_a_data", {})
        team_b_data = request.get("team_b_data", {})
        news_text   = request.get("news_text", matchup)
        public_pct  = float(request.get("public_sentiment_pct", 0.55))
        bankroll    = float(request.get("bankroll", 1000.0))
        # Multi-book odds for line shopping (Video 5)
        book_odds   = request.get("book_odds", {})  # e.g. {"FanDuel": -150, "DraftKings": -145}

        # STEP 1: ESPN Crawl
        crawl = self._step1_data_crawl(sport, team_a, team_b, request.get("features", {}))

        # STEP 2: Sentiment
        sentiment = self._step2_sentiment(news_text, team_a, public_pct)
        
        # Apply sentiment friction
        power_a = float(team_a_data.get("val", 1.5)) * crawl["impact_delta"] * (2.0 - sentiment["friction_score"])
        power_b = float(team_b_data.get("val", 1.1))
        
        # STEP 3: ELO (Video 3 — top predictive feature)
        elo_result = self._step3_elo(team_a, team_b)

        # STEP 4: Random Forest with ELO baked in
        rf_result = self._step4_random_forest(team_a_data, team_b_data, crawl, elo_result)
        rf_prob = rf_result["true_probability"]

        # Blend RF + ELO + momentum
        elo_prob = elo_result["elo_win_prob_a"]
        cfi = ((rf_prob * 0.5) + (elo_prob * 0.5) + 0.5) / 1.5
        
        # STEP 5: Monte Carlo
        mc = self._step4_monte_carlo(sport, power_a, power_b, cfi)
        
        # Blended: 40% RF + 30% ELO + 30% Monte Carlo
        blended_prob = (rf_prob * 0.40) + (elo_prob * 0.30) + (mc["true_prob"] * 0.30)

        # STEP 6: Quant Market (Video 5 — line shopping)
        quant_result = self._step6_quant(blended_prob, book_odds)
        
        # STEP 7: +EV Filter
        ev_result = self._step5_ev_filter(blended_prob, crawl["market_decimal"], bankroll)

        # Sentiment Gap
        sentiment_gap = self.sentiment.calculate_market_sentiment_gap(public_pct, blended_prob)

        exec_ms = round((time.time() - t0) * 1000, 2)

        # ── OMNI-ORACLE OUTPUT FORMAT ──────────────────────────────
        return {
            # Header
            "EVENT_NAME": matchup,
            "ENGINE": f"ASA v{self.VERSION}",
            "EXEC_MS": exec_ms,

            # ⚡ LIVE INTEL (Step 1)
            "LIVE_INTEL": {
                "INJURY_IMPACT":   crawl["injury_detail"],
                "IMPACT_DELTA":    crawl["impact_delta"],
                "STADIUM":         crawl["stadium"],
                "MOMENTUM_A":      crawl["momentum_a"],
                "MOMENTUM_B":      crawl["momentum_b"],
                "LIVE_ODDS_FOUND": bool(crawl["matched_odds"])
            },

            # 📊 SENTIMENT GAP (Step 2)
            "SENTIMENT_GAP": {
                **sentiment_gap,
                "IS_PUBLIC_TRAP":      sentiment["IS_PUBLIC_TRAP"],
                "SHARP_FADE_PROTOCOL": sentiment["SHARP_FADE_PROTOCOL"],
                "IS_REVENGE_ARC":      sentiment["REVENGE"]["IS_REVENGE_ARC"],
                "ADRENALINE_DELTA":    sentiment["REVENGE"]["PERFORMANCE_BOOST"],
                "IS_TRAP_GAME":        sentiment["IS_TRAP_GAME"],
            },

            # ⭐ ELO SYSTEM (Step 3 — Video 3 top signal)
            "ELO_ANALYSIS": {
                "TEAM_A_ELO":   elo_result["team_a_elo"],
                "TEAM_B_ELO":   elo_result["team_b_elo"],
                "ELO_DIFF":     elo_result["elo_diff"],
                "ELO_PROB_A":   f"{round(elo_result['elo_win_prob_a']*100,1)}%",
                "ELO_SIGNAL":   elo_result["elo_signal"],
            },

            # 🌲 RANDOM FOREST (Step 4)
            "RANDOM_FOREST": {
                "RF_TRUE_PROB":  f"{round(rf_prob * 100, 1)}%",
                "FOREST_VOTES": rf_result["forest_votes"],
                "TOP_FACTOR":   rf_result["top_decisive_factor"],
                "CONFIDENCE":   rf_result["confidence"]
            },

            # 🧠 TACTICAL BLUEPRINT (Step 5)
            "TACTICAL_BLUEPRINT": {
                "MC_TRUE_PROB": f"{round(mc['true_prob'] * 100, 1)}%",
                "BLENDED_PROB": f"{round(blended_prob * 100, 1)}%",
                "BLEND_WEIGHTS": "40% RF + 30% ELO + 30% Monte Carlo",
                "PIVOT_POINT":  f"{mc['pivot_minute']}' — Critical Momentum Shift",
                "MATCH_SCRIPT": mc["match_script"]
            },

            # 📈 QUANT MARKET (Step 6 — Video 5)
            "QUANT_MARKET": {
                "VERDICT":      quant_result.get("QUANT_VERDICT", "N/A"),
                "MODEL_PROB":   quant_result.get("MODEL_PROB", "N/A"),
                "MARKET_EDGE":  quant_result.get("EDGE", "N/A"),
                "LINE_SHOP":    quant_result.get("LINE_SHOP", {}),
                "EV_PER_100":   quant_result.get("EV_PER_100", "N/A"),
            },

            # ⚖️ +EV DISCREPANCY (Step 7)
            "EV_DISCREPANCY": {
                "IS_SHARP":       ev_result["IS_SHARP_BET"],
                "EDGE":           ev_result["EDGE_PCT"],
                "EXPECTED_VALUE": ev_result["EXPECTED_VALUE"],
                "KELLY_STAKE":    ev_result["KELLY_STAKE"],
                "SIGNAL":         ev_result["SIGNAL"]
            },

            # 🎯 ALPHA PICK
            "ALPHA_PICK": f"{team_a} ML / Spread" if blended_prob > 0.50 else f"{team_b} ML / Spread",

            # 🏦 LIMIT ORDER
            "LIMIT_ORDER": ev_result["LIMIT_ORDER"]
        }

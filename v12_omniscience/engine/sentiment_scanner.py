"""
ASA v5.0: SENTIMENT SCANNER & PUBLIC TRAP DETECTOR
Detects the 'Public Trap' when sentiment is >85% on one side.
Flags the 'Sharp Fade Protocol' for counter-market positioning.
Also calculates 'Adrenaline Delta' for revenge game scenarios.
"""
import re
import math
from typing import Dict, Any

NEGATIVE_MARKERS = [
    "hurt", "limping", "injured", "questionable", "doubtful", "out",
    "frustrated", "beef", "drama", "conflict", "limited", "soreness",
    "bad knee", "hobbling", "won't play", "scratch"
]
POSITIVE_MARKERS = [
    "revenge game", "motivated", "statement", "must win", "locked in",
    "healthy", "full lineup", "back to form", "100%", "hungry"
]
PUBLIC_TRAP_THRESHOLD = 0.85  # >85% one-sided sentiment = trap

class SentimentScanner:
    """
    ASA v5.0 Sentiment Analysis Module.
    Ingests text signals and detects sharp vs public money divergences.
    """

    def __init__(self):
        self.version = "5.0-SENTIMENT-VANGUARD"

    def scan_headlines(self, text: str) -> Dict[str, Any]:
        """
        Analyzes raw text (news headlines, social feeds) for market signals.
        Returns friction score, sentiment polarity, and trap flag.
        """
        text_lower = text.lower()
        neg_hits = sum(1 for m in NEGATIVE_MARKERS if m in text_lower)
        pos_hits = sum(1 for m in POSITIVE_MARKERS if m in text_lower)

        total_hits = neg_hits + pos_hits
        if total_hits == 0:
            sentiment_ratio = 0.5
        else:
            sentiment_ratio = pos_hits / total_hits

        # friction_score: 1.0 = neutral, >1.0 = risk, <1.0 = boost
        friction_score = 1.0 + (neg_hits * 0.12) - (pos_hits * 0.08)
        friction_score = round(max(0.6, min(1.5, friction_score)), 3)

        # Public sentiment proxy from keywords
        public_loading = min(1.0, (pos_hits + 1) / (neg_hits + pos_hits + 2))
        is_public_trap = public_loading > PUBLIC_TRAP_THRESHOLD

        return {
            "friction_score": friction_score,
            "sentiment_ratio": round(sentiment_ratio, 2),
            "neg_signals": neg_hits,
            "pos_signals": pos_hits,
            "public_loading": round(public_loading, 2),
            "IS_PUBLIC_TRAP": is_public_trap,
            "SHARP_FADE_PROTOCOL": is_public_trap,
        }

    def detect_revenge_arc(self, text: str, player_name: str = "") -> Dict[str, Any]:
        """
        Detects 'Revenge Game' narrative and calculates the Adrenaline Delta.
        Revenge games statistically show 7-12% boost in individual performance.
        """
        revenge_phrases = [
            "revenge", "prove wrong", "former team", "traded", "released",
            "cut by", "motivation", "personal", "back to", "wants to show"
        ]
        text_lower = text.lower()
        revenge_count = sum(1 for p in revenge_phrases if p in text_lower)

        is_revenge = revenge_count >= 2
        adrenaline_delta = min(0.12, revenge_count * 0.04)

        return {
            "IS_REVENGE_ARC": is_revenge,
            "ADRENALINE_DELTA": round(adrenaline_delta, 3),
            "PERFORMANCE_BOOST": f"+{round(adrenaline_delta * 100, 1)}%",
            "signal_count": revenge_count
        }

    def detect_trap_game(self, team_a_context: str) -> bool:
        """
        Flags a 'Trap Game' — when a team is heavily favored but faces
        a weaker opponent sandwiched between two big games.
        """
        trap_phrases = [
            "sandwiched", "looking ahead", "trap", "overlooking",
            "back-to-back", "3rd game in 4 nights", "tired legs"
        ]
        text_lower = team_a_context.lower()
        return any(p in text_lower for p in trap_phrases)

    def calculate_market_sentiment_gap(self, public_pct: float, sim_prob: float):
        """
        Compare PUBLIC sentiment (%) to TRUE PROBABILITY from simulation.
        A gap > 15% = valid fade signal.
        """
        gap = public_pct - sim_prob
        signal = "SHARP_FADE" if gap > 0.15 else ("SHARP_TAIL" if gap < -0.15 else "NEUTRAL")
        return {
            "PUBLIC_SENTIMENT": f"{round(public_pct * 100, 1)}%",
            "SIM_TRUE_PROB":    f"{round(sim_prob * 100, 1)}%",
            "SENTIMENT_GAP":    f"{round(gap * 100, 1)}%",
            "MARKET_SIGNAL":    signal
        }

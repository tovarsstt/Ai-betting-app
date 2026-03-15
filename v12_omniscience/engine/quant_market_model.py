"""
VIDEO-INSPIRED UPGRADE: QUANT MARKET MODEL
Source: YouTube Video 5 (Building a Betting Model — Quant Trading Approach)
Key insight: "DraftKings and FanDuel already know your basic stats. 
They're $20-40B companies. Basic stats are priced in. 
Use MARKET ODDS as your primary input, not historical averages."

Strategy: 
1. Never use raw average stats (already priced in by books).
2. Use MARKET ODDS as your primary signal.
3. Compare model probability vs market implied to find the tilt.
4. Always shop for the BEST PRICE across books (huge in video 5).

Also from Video 2: Normalize all features per match played (not totals).
"""
import math
from typing import Optional

class QuantMarketModel:
    """
    Quant trading approach applied to sports betting.
    The edge is in the MARKET, not in the raw stats.
    """

    def american_to_prob(self, american: Optional[int]) -> float:
        """Convert American odds to implied probability (with vig)."""
        if not american: 
            return 0.5
        if american > 0:
            return 100.0 / (american + 100.0)
        return abs(american) / (abs(american) + 100.0)

    def remove_vig(self, prob_a: float, prob_b: float):
        """
        De-vig: remove the book's margin to get the TRUE market probability.
        Video 5: The vig is typically 4-6% per side.
        """
        total = prob_a + prob_b
        return prob_a / total, prob_b / total

    def normalize_features(self, raw_stats: dict, matches_played: int) -> dict:
        """
        Video 2: Normalize all features per match played.
        "home wins divided by matches played, draws divided by matches played..."
        This removes the schedule-size bias that books already account for.
        """
        if matches_played == 0:
            return raw_stats
        return {k: round(v / matches_played, 4) for k, v in raw_stats.items() if isinstance(v, (int, float))}

    def line_shop_analysis(self, odds_across_books: dict) -> dict:
        """
        Video 5: Always get the BEST PRICE across books.
        "Make sure you're getting the best possible price. That's step one."

        odds_across_books = {
            "FanDuel": +300,
            "DraftKings": +280,
            "BetMGM": +290,
            "Caesars": +310
        }
        """
        if not odds_across_books:
            return {"best_book": "N/A", "best_odds": None, "ev_gain": 0}

        # Find the best odds (highest positive or least negative)
        def odds_value(o):
            return o if o > 0 else -(10000 / abs(o))

        best_book = max(odds_across_books, key=lambda k: odds_value(odds_across_books[k]))
        worst_book = min(odds_across_books, key=lambda k: odds_value(odds_across_books[k]))
        
        best_odds = odds_across_books[best_book]
        worst_odds = odds_across_books[worst_book]

        # EV gain from shopping (per $100 bet)
        def to_decimal(ml):
            return (ml / 100 + 1) if ml > 0 else (100 / abs(ml) + 1)

        gain = (to_decimal(best_odds) - to_decimal(worst_odds)) * 100

        return {
            "BEST_BOOK": best_book,
            "BEST_ODDS": f"+{best_odds}" if best_odds > 0 else str(best_odds),
            "WORST_BOOK": worst_book,
            "WORST_ODDS": f"+{worst_odds}" if worst_odds > 0 else str(worst_odds),
            "EV_GAIN_VS_WORST": f"+${round(gain, 2)}",
            "ACTION": f"Use {best_book}. Avoid {worst_book}."
        }

    def quant_edge_analysis(self, model_prob: float, odds_across_books: dict) -> dict:
        """
        Master quant analysis:
        1. Find best available odds.
        2. Calculate true edge vs market.
        3. Output sharp/no-value signal.

        Video 5: "If our model has Thunder at 95% and market implies 75%, bet Thunder."
        """
        shop = self.line_shop_analysis(odds_across_books)
        
        best_book_name = shop.get("BEST_BOOK", "N/A")
        best_american = odds_across_books.get(best_book_name, 100)
        
        market_implied = self.american_to_prob(best_american)
        
        # Calculate market probs across all books
        all_probs = {book: self.american_to_prob(o) for book, o in odds_across_books.items()}
        avg_market_prob = sum(all_probs.values()) / len(all_probs) if all_probs else 0.5

        edge = model_prob - market_implied
        ev_per_100 = (model_prob * (1 / market_implied - 1) - (1 - model_prob)) * 100

        return {
            "MODEL_PROB": f"{round(model_prob * 100, 1)}%",
            "MARKET_IMPLIED": f"{round(avg_market_prob * 100, 1)}%",
            "EDGE": f"+{round(edge * 100, 2)}%" if edge > 0 else f"{round(edge * 100, 2)}%",
            "EV_PER_100": f"+${round(ev_per_100, 2)}" if ev_per_100 > 0 else f"${round(ev_per_100, 2)}",
            "IS_SHARP": edge > 0.04,
            "LINE_SHOP": shop,
            "QUANT_VERDICT": "BET ✅" if edge > 0.04 else ("MARGINAL ⚠️" if edge > 0.01 else "SKIP ❌"),
        }

"""
ASA v5.0: +EV MARKET FILTER & LIMIT ORDER ENGINE
Compares TRUE PROBABILITY to live market odds.
Filters for +EV (Expected Value) where edge > 4% (Sharp threshold).
Suggests 'Limit Orders' (Maker Prices) for acting as the house.
"""
import math
from typing import Dict, Any, Optional

MIN_SHARP_EDGE = 0.04  # 4% minimum edge threshold (ASA v5.0 standard)

class EVMarketFilter:
    """
    Sharp market arbitrage engine.
    Compares model TRUE_PROBABILITY against book odds to find +EV opportunities.
    """

    def american_to_decimal(self, american: int) -> float:
        if not american or american == 0:
            return 1.91
        if american > 0:
            return (american / 100.0) + 1.0
        return (100.0 / abs(american)) + 1.0

    def decimal_to_implied(self, decimal_odds: float) -> float:
        return 1.0 / decimal_odds if decimal_odds > 0 else 0.0

    def remove_vig(self, implied_home: float, implied_away: float):
        """De-vig to get true market probabilities."""
        total = implied_home + implied_away
        if total <= 0:
            return 0.5, 0.5
        return implied_home / total, implied_away / total

    def calculate_ev(self, true_prob: float, decimal_odds: float, stake: float = 100) -> float:
        """Standard Expected Value calculation."""
        profit = (decimal_odds - 1.0) * stake
        return round((true_prob * profit) - ((1 - true_prob) * stake), 2)

    def calculate_kelly(self, true_prob: float, decimal_odds: float, bankroll: float = 1000, fraction: float = 0.25) -> float:
        """Fractional Kelly criterion for stake sizing."""
        b = decimal_odds - 1.0
        if b <= 0:
            return 0.0
        kelly_pct = ((b * true_prob) - (1 - true_prob)) / b
        return round(max(0, kelly_pct * fraction * bankroll), 2)

    def calculate_maker_price(self, true_prob: float, target_edge: float = 0.05) -> Dict[str, Any]:
        """
        'Limit Order' strategy: wait for odds to drift to a better price.
        Maker Price = the decimal odds that give you exactly target_edge.
        """
        # What decimal odds would give us target_edge EV?
        # EV = (p * profit) - (1-p*stake) > 0
        # Simplified: maker_odds = 1 / (true_prob - target_edge)
        maker_prob = max(0.01, true_prob - target_edge)
        maker_odds_decimal = round(1.0 / maker_prob, 3)

        # Convert to American
        if maker_odds_decimal >= 2.0:
            maker_american = f"+{int(round((maker_odds_decimal - 1) * 100))}"
        else:
            if maker_odds_decimal <= 1.0:
                maker_american = "N/A"
            else:
                maker_american = f"-{int(round(100 / (maker_odds_decimal - 1)))}"

        return {
            "MAKER_DECIMAL": maker_odds_decimal,
            "MAKER_AMERICAN": maker_american,
            "STRATEGY": f"Wait for {maker_american} before placing. Do NOT bet current price."
        }

    def analyze(self, true_prob: float, market_decimal_odds: float,
                bankroll: float = 1000.0, context: str = "") -> Dict[str, Any]:
        """
        Full +EV analysis pipeline.
        Returns Sharp/Fade signal, EV, Kelly sizing, and Limit Order suggestion.
        """
        implied = self.decimal_to_implied(market_decimal_odds)
        edge = true_prob - implied
        ev = self.calculate_ev(true_prob, market_decimal_odds)
        kelly = self.calculate_kelly(true_prob, market_decimal_odds, bankroll)
        maker = self.calculate_maker_price(true_prob)
        is_sharp = edge >= MIN_SHARP_EDGE

        return {
            "IS_SHARP_BET": is_sharp,
            "EDGE_PCT": f"+{round(edge * 100, 2)}%" if edge > 0 else f"{round(edge * 100, 2)}%",
            "EXPECTED_VALUE": f"+${ev}" if ev > 0 else f"${ev}",
            "KELLY_STAKE": f"${kelly}",
            "MARKET_IMPLIED": f"{round(implied * 100, 1)}%",
            "TRUE_PROBABILITY": f"{round(true_prob * 100, 1)}%",
            "LIMIT_ORDER": maker,
            "SIGNAL": "SHARP_VALUE ✅" if is_sharp else ("WEAK_EDGE ⚠️" if edge > 0 else "NO_VALUE ❌"),
            "context": context
        }

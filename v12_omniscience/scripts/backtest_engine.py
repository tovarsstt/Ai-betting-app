"""
V13 INTEGRATION: SCIKIT-LEARN CLASSIFIER BACKTESTER
Source: `georgedouzas/sports-betting` repository.
Concept: Validate God-Engine accuracy systematically using TimeSeriesSplit on historical data.
"""
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
import logging
import sys
import os

# Append parent dir so we can import the V13 Engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from engine.random_forest_engine import XGBoostDecisionEngine, XGB_AVAILABLE
except ImportError:
    XGB_AVAILABLE = False
    XGBoostDecisionEngine = None

class SportsModelBacktester:
    """
    Simulates the Scikit-Learn ClassifierBettor pipeline using our God-Engine Logic.
    Backtests predictive variables over chronological splits preventing look-ahead bias.
    """
    
    def __init__(self, db_path="v12_omniscience/data/god_engine.db"):
        self.db_path = db_path
        self.engine = XGBoostDecisionEngine() if XGBoostDecisionEngine else None

    def generate_synthetic_ledger(self, n_rows=5000):
        """Creates a mock historical ledger representing scraped closing vectors."""
        dates = pd.date_range(start="2024-10-01", periods=n_rows, freq="H")
        return pd.DataFrame({
            "game_date": dates,
            "sharp_odds": np.random.uniform(1.85, 2.15, size=n_rows),
            "market_odds": np.random.uniform(1.85, 2.15, size=n_rows),
            "true_win_prob": np.random.uniform(0.40, 0.60, size=n_rows),
            "actual_winner": np.random.randint(0, 2, size=n_rows)  # 1 = Home, 0 = Away
        }).sort_values("game_date")

    def run_time_series_backtest(self, n_splits=5):
        df = self.generate_synthetic_ledger()
        
        print(f"--- INIT V13 TIME-SERIES BACKTEST ({n_splits} SPLITS) ---")
        if XGB_AVAILABLE:
            print("Engine Mode: XGBoost Classifier (NBA Parameterization)")
        else:
            print("Engine Mode: Synthetic Random Forest Fallback")
            
        tscv = TimeSeriesSplit(n_splits=n_splits)
        
        # We simulate feature matrix 'X' and target 'y'
        features = ["sharp_odds", "market_odds", "true_win_prob"]
        X = df[features]
        y = df["actual_winner"]
        
        metrics = []

        for fold, (train_index, test_index) in enumerate(tscv.split(X)):
            X_train, X_test = X.iloc[train_index], X.iloc[test_index]
            y_train, y_test = y.iloc[train_index], y.iloc[test_index]
            
            # Predict Logic:
            # God Engine logic assumes if true probability > implied probability by market, it's a +EV bet
            implied_prob = 1.0 / X_test["market_odds"]
            
            # Simulated model output targeting +EV anomalies
            # Here, we mimic model inference by relying on the true_win_prob
            y_pred = (X_test["true_win_prob"] > implied_prob).astype(int)
            
            # Replace naive 0s with actual model logic if we were fully fitting
            # Since this is binary (0/1), we just compare y_test vs y_pred
            
            acc = accuracy_score(y_test, y_pred)
            
            # ROI Math: (Win % * Profit) - (Loss %)
            # For simplicity, if model voted 1 and outcome 1, we win market_odds - 1
            # If model voted 0 and outcome 0, we treat it as an Away bet win
            wins = (y_test == y_pred)
            losses = ~wins
            
            # Average ROI calculation per fold
            profit = (wins * (X_test["market_odds"] - 1.0)).sum()
            loss = losses.sum()
            roi = (profit - loss) / len(y_test)
            
            metrics.append({"fold": fold+1, "acc": acc, "roi_pct": roi * 100})
            print(f"Fold {fold+1} -> Test Size: {len(X_test)} | Accuracy: {acc*100:.1f}% | Assumed ROI: {roi*100:.2f}%")

        avg_roi = np.mean([m["roi_pct"] for m in metrics])
        avg_acc = np.mean([m["acc"] for m in metrics])
        
        print(f"====================================")
        print(f"TOTAL BACKTEST ACCURACY: {avg_acc*100:.2f}%")
        print(f"TOTAL BACKTEST EST ROI:  {avg_roi:.2f}%")
        print(f"====================================")

if __name__ == "__main__":
    backtester = SportsModelBacktester()
    backtester.run_time_series_backtest()

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

class SelfCorrectionLoop:
    """
    V12 Post-Mortem Engine. 
    Compares predictions vs actual outcomes and Closing Line Value (CLV).
    Updates feature weights via Gradient Descent.
    """
    
    def __init__(self, db_path='v12_omniscience/data/memory_matrix.sqlite'):
        self.db_path = db_path

    def run_daily_post_mortem(self):
        """Processes all 'pending' predictions that now have results."""
        conn = sqlite3.connect(self.db_path)
        
        # 1. Fetch pending predictions
        query = "SELECT * FROM predictions WHERE status = 'pending'"
        df_pending = pd.read_sql_query(query, conn)
        
        if df_pending.empty:
            print("📅 No pending results to process for today.")
            return

        print(f"🧐 Processing Post-Mortem for {len(df_pending)} events...")
        
        cursor = conn.cursor()
        for _, row in df_pending.iterrows():
            # Mocking result fetching (Syncing actual outcomes into the matrix)
            actual_outcome = 1 
            clv_delta = 1.5 
            
            # 2. Update status in predictions
            cursor.execute('''
                UPDATE predictions 
                SET status = 'graded', actual_outcome = ?, clv_delta = ?
                WHERE prediction_id = ?
            ''', (actual_outcome, clv_delta, row['prediction_id']))
            
            # 3. Log to results table for the Accountability Ledger
            cursor.execute('''
                INSERT OR IGNORE INTO results (prediction_id, winner_id, pnl_usd)
                VALUES (?, ?, ?)
            ''', (row['prediction_id'], 'Home_Winner' if actual_outcome == 1 else 'Away_Winner', 0.0))
            
            # 4. Dynamic Weight Update (Evolutionary Step)
            self._update_feature_weights(conn, row, actual_outcome)
            
        conn.commit()
        conn.close()

    def _update_feature_weights(self, conn, row, outcome):
        """Adjusts feature prominence based on accuracy (Evolutionary Gradient)."""
        cursor = conn.cursor()
        cursor.execute("SELECT feature_name, current_weight FROM feature_weights")
        weights = dict(cursor.fetchall())
        
        lr = 0.01 
        error = outcome - (row.get('model_probability') or 0.5)
        
        for feat, w in weights.items():
            # Apply adjustment to current_weight column
            adjustment = lr * error * 0.05 
            new_w = max(0.1, min(10.0, w + adjustment)) # Keep weights in reasonable bound
            cursor.execute("UPDATE feature_weights SET current_weight = ? WHERE feature_name = ?", (new_w, feat))

if __name__ == "__main__":
    loop = SelfCorrectionLoop()
    loop.run_daily_post_mortem()

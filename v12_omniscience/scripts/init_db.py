import sqlite3
import os

def initialize_database(db_path='v12_omniscience/data/memory_matrix.sqlite'):
    """Initializes the V12 Memory Matrix Schema."""
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Table for Predictions & Model Snapshots
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS predictions (
        prediction_id TEXT PRIMARY KEY,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        matchup TEXT NOT NULL,
        sport TEXT NOT NULL,
        model_name TEXT DEFAULT 'v12_ensemble',
        model_probability REAL,
        implied_probability REAL,
        clv_initial REAL,
        clv_closing REAL,
        clv_delta REAL,
        actual_outcome INTEGER, -- 1 for Home Win (or Over), 0 for Away (or Under)
        kelly_size_usd REAL,
        feature_vector_json TEXT,  -- JSON string of all feature inputs used
        status TEXT DEFAULT 'pending' -- pending, graded, void
    )
    ''')
    
    # 2. Table for Actual Outcomes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS results (
        prediction_id TEXT PRIMARY KEY,
        actual_score_home INTEGER,
        actual_score_away INTEGER,
        winner_id TEXT,
        cover_spread BOOLEAN,
        graded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        pnl_usd REAL,
        FOREIGN KEY (prediction_id) REFERENCES predictions (prediction_id)
    )
    ''')
    
    # 3. Table for Closing Line Value (CLV) Tracking
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS clv_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prediction_id TEXT,
        line_type TEXT, -- SPREAD, ML, TOTAL
        opening_line REAL,
        closing_line REAL,
        model_edge_at_close REAL,
        FOREIGN KEY (prediction_id) REFERENCES predictions (prediction_id)
    )
    ''')
    
    # 4. Table for Evolutionary Feature Weights (Gradient Descent)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feature_weights (
        feature_name TEXT PRIMARY KEY,
        current_weight REAL DEFAULT 1.0,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
        gradient_delta REAL DEFAULT 0.0,
        feature_importance_score REAL DEFAULT 0.0
    )
    ''')

    # 5. Table for Accountability Ledger (Actual Bets)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bet_ledger (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        prediction_id TEXT,
        amount_usd REAL,
        placed_odds REAL,
        status TEXT DEFAULT 'active', -- active, win, loss, pushed
        placed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (prediction_id) REFERENCES predictions (prediction_id)
    )
    ''')
    
    # Initialize basic Neuro-Quant feature weights
    base_features = [
        ('circadian_friction', 1.0),
        ('tilt_tensor', 1.0),
        ('fatigue_decay', 1.0),
        ('referee_bias', 1.0),
        ('home_elo', 1.0),
        ('away_elo', 1.0)
    ]
    
    cursor.executemany('INSERT OR IGNORE INTO feature_weights (feature_name, current_weight) VALUES (?, ?)', base_features)
    
    conn.commit()
    conn.close()
    print(f"✅ V12 Memory Matrix Initialized at: {db_path}")

if __name__ == "__main__":
    initialize_database()

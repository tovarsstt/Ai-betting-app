import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import log_loss, roc_auc_score
import json
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_telemetry_data():
    """Extracts historical prediction telemetry merged with actual ground-truth outcomes."""
    try:
        # SQLite connection matches the server.js in-memory map or disk map
        # For production synchronization, server.js would need to write to a disk file like 'engine_memory.db' rather than ':memory:'
        # Assuming for the architecture evolution we are targeting a persistent local file 'engine_memory.db'
        
        # NOTE: If server.js is using ':memory:', a parallel python process cannot read it. 
        # Modifying default target to 'engine_memory.db' to match standard production bridging.
        conn = sqlite3.connect('engine_memory.db') 
        
        query = """
            SELECT 
                t.bernoulli_edge,
                t.injury_score,
                t.smi_score,
                t.rlm_active,
                t.regression_delta,
                t.scheme_friction,
                m.home_score,
                m.away_score,
                m.actual_margin,
                m.closing_line_value,
                t.target_team,
                t.market_spread
            FROM engine_telemetry t
            JOIN market_outcomes m ON t.game_id = m.game_id
            WHERE m.actual_margin IS NOT NULL
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        logging.error(f"Failed to load telemetry data: {e}")
        return pd.DataFrame()

def preprocess_data(df):
    """Engineers the features and target variable (Win vs Spread)."""
    if df.empty:
        return df, pd.Series()

    # Determine Cover (Target Variable binary 1 or 0)
    # Simplified logic: If we bet target team and they covered the spread
    # Note: Requires deeper string matching on target_team vs home/away in production
    # For this architecture demonstration, we assume a synthetic 'is_cover' mapping
    df['is_cover'] = np.where(df['actual_margin'] > df['market_spread'], 1, 0)

    # Feature Matrix
    features = [
        'bernoulli_edge', 
        'injury_score', 
        'smi_score', 
        'rlm_active',
        'regression_delta', 
        'scheme_friction'
    ]
    
    X = df[features]
    y = df['is_cover']
    
    return X, y

def retrain_xgboost():
    """Executes the Autonomous ML Retraining Loop."""
    logging.info("Initiating God-Engine V8.0 ML Retraining Sequence...")
    
    df = load_telemetry_data()
    if len(df) < 50:
        logging.warning(f"Insufficient telemetry data ({len(df)} rows). Requires minimum 50 reconciled matches to retrain.")
        return

    X, y = preprocess_data(df)
    
    # Train/Test Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # XGBoost Parameters adjusted for high noise / standard athletic variance
    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'logloss',
        'max_depth': 4,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'seed': 42
    }

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtest = xgb.DMatrix(X_test, label=y_test)

    # Train Model
    evals = [(dtrain, 'train'), (dtest, 'eval')]
    model = xgb.train(
        params, 
        dtrain, 
        num_boost_round=200, 
        evals=evals, 
        early_stopping_rounds=20,
        verbose_eval=False
    )

    # Calculate global ROI trajectory standard metrics
    preds = model.predict(dtest)
    auc = roc_auc_score(y_test, preds)
    logging.info(f"Retraining Complete. Model AUC: {auc:.4f}")

    # Extract Feature Importances (Weightings)
    importance = model.get_score(importance_type='gain')
    total_gain = sum(importance.values())
    
    # Normalize to percentages matching DB schema
    weights = {k: v / total_gain for k, v in importance.items()}
    
    logging.info("--- New Calculated Feature Vectors ---")
    for feature, weight in weights.items():
        logging.info(f"{feature}: {weight:.4f}")

    # Update Evolution Matrix
    update_evolution_matrix(weights, auc)

def update_evolution_matrix(weights, auc):
    """Commits the new feature importance vectors back to SQLite memory."""
    try:
        conn = sqlite3.connect('engine_memory.db')
        cursor = conn.cursor()
        
        query = """
            INSERT INTO ensemble_weights (
                weight_bernoulli, 
                weight_injury, 
                weight_sharp_money, 
                weight_regression, 
                weight_scheme,
                global_roi_last_7_days
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (
            weights.get('bernoulli_edge', 0.60),
            weights.get('injury_score', 0.25),
            weights.get('smi_score', 0.15),
            weights.get('regression_delta', 0.0),
            weights.get('scheme_friction', 0.0),
            auc # Tracking AUC as proxy for ROI health metric
        ))
        
        conn.commit()
        conn.close()
        logging.info("Evolution Matrix Updated Successfully in SQLite.")
    except Exception as e:
        logging.error(f"Matrix Update Failed: {e}")

if __name__ == "__main__":
    retrain_xgboost()

import xgboost as xgb
import pandas as pd
import numpy as np
import os
import json

def generate_synthetic_data(samples=1000):
    """
    Generates synthetic historical sports data with Neuro-Quant features.
    Features: cf, elo_delta, tilt_factor, fatigue_index, ref_aggression.
    Target: winner (1 if home, 0 if away).
    """
    np.random.seed(42)
    
    data = []
    for i in range(samples):
        cf = np.random.uniform(0.1, 2.0)
        elo_home = np.random.uniform(1400, 1600)
        elo_away = np.random.uniform(1400, 1600)
        tilt = np.random.uniform(0, 1)
        fatigue = np.random.uniform(0, 1)
        
        # Win probability influenced by features
        # Higher Home Elo + Lower Fatigue - Higher CF = Higher Win Prob
        logit = (elo_home - elo_away) / 100 - (cf * 0.5) - (fatigue * 0.3) + (np.random.normal(0, 0.2))
        prob = 1 / (1 + np.exp(-logit))
        winner = 1 if np.random.rand() < prob else 0
        
        data.append({
            'cf': cf,
            'elo_delta': elo_home - elo_away,
            'tilt': tilt,
            'fatigue': fatigue,
            'winner': winner
        })
    
    return pd.DataFrame(data)

def train_v12_alpha():
    """Trains the first XGBoost model for V12."""
    print("🧠 Starting V12 Training Session...")
    
    df = generate_synthetic_data()
    X = df.drop('winner', axis=1)
    y = df['winner']
    
    # Simple Data Normalization
    X_norm = (X - X.mean()) / X.std()
    
    # XGBoost Parameters
    params = {
        'objective': 'binary:logistic',
        'eval_metric': 'logloss',
        'max_depth': 4,
        'learning_rate': 0.1,
        'n_estimators': 100
    }
    
    model = xgb.XGBClassifier(**params)
    model.fit(X_norm, y)
    
    # Save Model
    model_dir = "v12_omniscience/models"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "v12_alpha.json")
    model.save_model(model_path)
    
    # Save normalization metadata
    norm_path = os.path.join(model_dir, "normalization.json")
    with open(norm_path, 'w') as f:
        json.dump({
            'mean': X.mean().to_dict(),
            'std': X.std().to_dict()
        }, f)
    
    print(f"✅ V12 Training Session Complete. Model saved to: {model_path}")
    print(f"📈 Log-Loss (Initial Train): {model.evals_result_ if hasattr(model, 'evals_result_') else 'N/A'}")

if __name__ == "__main__":
    train_v12_alpha()

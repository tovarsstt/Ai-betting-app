import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os

# MMI_FEATURES = [
#     'home_elo', 'away_elo', 
#     'home_last_5_win_rate', 'away_last_5_win_rate',
#     'home_ppg_ema_10', 'away_ppg_ema_10',
#     'is_revenge_game', 'rest_days_delta'
# ]

def train_mmi_model(csv_path="data/nba_historical.csv"):
    if not os.path.exists(csv_path):
        print("⚠️ No real data found yet. Generating synthetic Alpha-Set for architecture validation...")
        X, y = generate_synthetic_data(1000)
    else:
        df = pd.read_csv(csv_path)
        if len(df) < 50:
            print("⚠️ Data too sparse. Using synthetic boost...")
            X, y = generate_synthetic_data(1000)
        else:
            X, y = preprocess_data(df)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("🚀 [MMI TRAINING] Igniting XGBoost Alpha-Core...")
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"✅ MODEL BRAIN SYNCED: Accuracy = {acc:.4f}")
    
    if not os.path.exists("models"): os.makedirs("models")
    joblib.dump(model, "models/mmi_v1.pkl")
    print("💾 Model saved to models/mmi_v1.pkl")

def generate_synthetic_data(n=1000):
    # Mocking the feature set for V13.6 MMI validation
    np.random.seed(42)
    X = np.random.rand(n, 8) 
    # Logic: Home team wins more if features [0] and [2] are high
    y = (X[:, 0] + X[:, 2] + np.random.normal(0, 0.1, n) > 1.0).astype(int)
    return X, y

def preprocess_data(df):
    # Placeholder for real feature engineering (Phase 2)
    # For now, return random based on count for skeleton testing
    return generate_synthetic_data(len(df))

if __name__ == "__main__":
    train_mmi_model()

"""
Kronos adapter for Caveman Locks.
Maps sports betting line movement to OHLCVA format for Kronos inference.

Line → OHLCVA mapping:
  Open   = opening line
  High   = peak line movement (most extreme in favor)
  Low    = floor line movement
  Close  = current/closing line
  Volume = bet volume (ticket count)
  Amount = handle (total $ wagered)

Usage:
  # Smoke test
  python3 kronos_adapter.py

  # Called by lineMovementService.ts with JSON on stdin:
  echo '{"history":[...],"steps":3,"n_samples":30}' | python3 kronos_adapter.py --json
"""
import sys
import json
import warnings
import numpy as np

warnings.filterwarnings("ignore")

KRONOS_DIR = "/Users/josetovar/Documents/APP AI BETS/scripts/kronos"
sys.path.insert(0, KRONOS_DIR)
sys.path.insert(0, f"{KRONOS_DIR}/model")


def build_ohlcva(line_history: list) -> np.ndarray:
    arr = np.array(
        [[r["open"], r["high"], r["low"], r["close"], r["volume"], r["amount"]]
         for r in line_history],
        dtype=np.float32,
    )
    return arr[-512:]  # Kronos max context


def predict(line_history: list, steps: int = 3, n_samples: int = 30) -> dict:
    try:
        import pandas as pd
        from model.kronos import Kronos, KronosTokenizer, KronosPredictor

        tokenizer  = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model      = Kronos.from_pretrained("NeoQuasar/Kronos-base")
        predictor  = KronosPredictor(model=model, tokenizer=tokenizer)

        arr  = build_ohlcva(line_history)
        df   = pd.DataFrame(arr, columns=["open", "high", "low", "close", "volume", "amount"])
        ts        = pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq="1min")
        future_ts = pd.date_range(start=ts[-1], periods=steps + 1, freq="1min")[1:]
        df.index  = ts

        # predict() uses .dt accessor internally — must be pandas Series
        # Returns a DataFrame with columns: open, high, low, close, volume, amount
        pred_df     = predictor.predict(df, pd.Series(ts), pd.Series(future_ts),
                                        pred_len=steps, sample_count=n_samples, verbose=False)
        close_preds = pred_df["close"].values
        current_close = float(arr[-1, 3])

        return {
            "direction": "up" if float(close_preds[-1]) > current_close else "down",
            "mean": close_preds.tolist(),
            "std":  [0.0] * len(close_preds),
        }
    except ModuleNotFoundError as e:
        return {
            "error": str(e),
            "note":  "torch/transformers not installed. On Intel Macs, recent PyTorch "
                     "releases dropped macOS x86_64 wheels for current Python versions "
                     "(cp313+) — `pip install torch transformers` will fail with "
                     "'No matching distribution'. Needs an arm64 Mac, an older "
                     "Python (<=3.12 for torch<=2.2.2, the last Intel-macOS build), "
                     "or a Linux/cloud box to run Kronos.",
        }
    except Exception as e:
        return {
            "error": str(e),
            "note":  "Kronos weights download on first run (~700MB). Needs internet.",
        }


if __name__ == "__main__":
    if "--json" in sys.argv:
        # Called by lineMovementService.ts — read JSON from stdin, print JSON to stdout
        raw   = sys.stdin.read().strip()
        args  = json.loads(raw)
        result = predict(
            args["history"],
            steps=args.get("steps", 3),
            n_samples=args.get("n_samples", 30),
        )
        print(json.dumps(result))
    else:
        # Smoke test
        synthetic = [
            {"open": -110, "high": -108, "low": -112, "close": -110, "volume": 100, "amount": 10000}
            for _ in range(20)
        ]
        result = predict(synthetic, steps=3, n_samples=5)
        print("Kronos adapter test:", result)

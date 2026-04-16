import sys
import os
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.market_data import MarketDataFetcher
from src.analysis.regime import RegimeDetector
from src.config import Config

def main():
    print("=== Market Regime Detection AI Training & Verification ===")
    
    # 1. Fetch Data
    print("1. Fetching Market Data...")
    fetcher = MarketDataFetcher()
    data = fetcher.get_regime_input_data()
    
    if data.empty:
        print("Error: Failed to fetch data.")
        return
        
    print(f"   Data Fetched: {len(data)} rows (Returns & Volatility)")
    print(data.tail())

    # 2. Train Model
    print("2. Training HMM Model...")
    detector = RegimeDetector(n_components=3, n_iter=100)
    detector.train_model(data)
    print("   Training Complete.")
    
    # 3. Predict & Analyze
    print("3. Analyzing Regimes...")
    data['regime'] = detector.model.predict(data.values)
    
    # Show stats by regime
    stats = data.groupby('regime').agg({
        'daily_return': ['mean', 'std', 'count'],
        'volatility': ['mean']
    })
    print("\n   Regime Statistics:")
    print(stats)
    
    # 4. Save Model
    print("4. Saving Model...")
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_path = Config.DATA_DIR / "regime_model.pkl"
    detector.save_model(str(save_path))
    print(f"   Model saved to: {save_path}")
    
    # 5. Recent Regime
    current_regime = data['regime'].iloc[-1]
    print(f"\n   Current Market Regime (Last Day): Regime-{current_regime}")

if __name__ == "__main__":
    main()

import sys
import os
import argparse
import json
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.market_data import MarketDataFetcher
from src.optimization.genetic import GeneticOptimizer

def main():
    parser = argparse.ArgumentParser(description="AutoML: Genetic Algorithm for Strategy Optimization")
    parser.add_argument("ticker", nargs="?", default="AAPL", help="Stock Ticker")
    parser.add_argument("--pop", type=int, default=50, help="Population Size")
    parser.add_argument("--gen", type=int, default=10, help="Generations")
    args = parser.parse_args()
    
    ticker = args.ticker
    print(f"=== AutoML Optimization for {ticker} ===")
    print(f"Config: Pop={args.pop}, Gen={args.gen}")
    
    # 1. Fetch Data
    print("Fetching data...")
    fetcher = MarketDataFetcher()
    # Use 1 year data for robust optimization
    df = fetcher.fetch_history(ticker, period="1y")
    
    if df.empty:
        print("Error: No data found.")
        return

    print(f"Data Loaded: {len(df)} candles")

    # 2. Run Optimization
    print("Starting Evolution...")
    optimizer = GeneticOptimizer(df, population_size=args.pop, generations=args.gen)
    best_params, best_fitness = optimizer.run()
    
    print("\n=== Optimization Result ===")
    print(f"Best Sharpe Ratio: {best_fitness:.4f}")
    print(f"Best Parameters: {best_params}")
    print("  [Fast, Slow, Signal, RSI_Win, RSI_Low, RSI_High]")
    
    # 3. Save Result
    result = {
        "ticker": ticker,
        "strategy": "MACD_RSI",
        "timestamp": datetime.now().isoformat(),
        "best_fitness": best_fitness,
        "best_params": {
            "macd_fast": int(best_params[0]),
            "macd_slow": int(best_params[1]),
            "macd_signal": int(best_params[2]),
            "rsi_window": int(best_params[3]),
            "rsi_lower": int(best_params[4]),
            "rsi_upper": int(best_params[5])
        }
    }
    
    os.makedirs("data", exist_ok=True)
    save_path = f"data/best_params_{ticker}_macd_rsi.json"
    with open(save_path, "w") as f:
        json.dump(result, f, indent=4)
        
    print(f"Saved best parameters to {save_path}")

if __name__ == "__main__":
    main()

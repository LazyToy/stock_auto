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
from src.optimization.strategy_registry import get_strategy_spec, normalize_strategy_type

def main():
    parser = argparse.ArgumentParser(description="AutoML: Genetic Algorithm for Strategy Optimization")
    parser.add_argument("ticker", nargs="?", default="AAPL", help="Stock Ticker")
    parser.add_argument("--pop", type=int, default=50, help="Population Size")
    parser.add_argument("--gen", type=int, default=10, help="Generations")
    parser.add_argument("--strategy", default="MACD_RSI", help="AutoML strategy type or label")
    parser.add_argument("--fitness", default="composite", choices=["composite", "sharpe"])
    args = parser.parse_args()
    
    ticker = args.ticker
    strategy_type = normalize_strategy_type(args.strategy)
    strategy_spec = get_strategy_spec(strategy_type)
    print(f"=== AutoML Optimization for {ticker} ===")
    print(
        f"Config: Pop={args.pop}, Gen={args.gen}, "
        f"Strategy={strategy_spec.display_name}, Fitness={args.fitness}"
    )
    
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
    optimizer = GeneticOptimizer(
        df,
        population_size=args.pop,
        generations=args.gen,
        strategy_type=strategy_type,
        fitness_metric=args.fitness,
    )
    best_params, best_fitness, _ = optimizer.run()
    
    print("\n=== Optimization Result ===")
    print(f"Best Fitness: {best_fitness:.4f}")
    print(f"Best Parameters: {best_params}")
    print(f"  {strategy_spec.parameter_labels}")
    
    # 3. Save Result
    result = {
        "ticker": ticker,
        "strategy": strategy_type,
        "timestamp": datetime.now().isoformat(),
        "best_fitness": best_fitness,
        "best_params": {
            label: int(value)
            for label, value in zip(strategy_spec.parameter_labels, best_params)
        },
    }
    
    os.makedirs("data", exist_ok=True)
    save_path = f"data/best_params_{ticker}_{strategy_type.lower()}.json"
    with open(save_path, "w") as f:
        json.dump(result, f, indent=4)
        
    print(f"Saved best parameters to {save_path}")

if __name__ == "__main__":
    main()

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimization.genetic import GeneticOptimizer
from src.optimization.automl_support import (
    build_multi_symbol_validation_report,
    download_automl_price_history,
    save_multi_symbol_validation_report,
)
from src.optimization.strategy_registry import get_strategy_spec, normalize_strategy_type


def parse_symbols(symbols: str | None, fallback_ticker: str = "AAPL") -> list[str]:
    raw_symbols = symbols if symbols else fallback_ticker
    parsed = [
        symbol.strip().upper()
        for symbol in str(raw_symbols).split(",")
        if symbol.strip()
    ]
    return parsed or [fallback_ticker.strip().upper()]


def build_validation_kwargs(
    *,
    validation_method: str,
    train_ratio: float,
    train_window: int,
    test_window: int,
    min_trades: int,
) -> dict:
    method = validation_method.strip().lower()
    if method == "walk_forward":
        return {
            "train_window": int(train_window),
            "test_window": int(test_window),
            "min_trades": int(min_trades),
        }
    if method == "train_test":
        return {
            "train_ratio": float(train_ratio),
            "min_trades": int(min_trades),
        }
    return {"min_trades": int(min_trades)}


def run_symbol_optimization(
    *,
    symbol: str,
    period: str,
    strategy_type: str,
    fitness_metric: str,
    population_size: int,
    generations: int,
    validation_method: str,
    validation_kwargs: dict,
) -> dict:
    df, resolved_symbol, error_message = download_automl_price_history(symbol, period=period)
    if df.empty:
        return {
            "symbol": symbol,
            "requested_symbol": symbol,
            "status": "skipped",
            "error": error_message or "No data found",
        }

    try:
        optimizer = GeneticOptimizer(
            df,
            population_size=population_size,
            generations=generations,
            strategy_type=strategy_type,
            fitness_metric=fitness_metric,
        )
        result = optimizer.evolve(
            symbol=resolved_symbol or symbol,
            validation_method=validation_method,
            validation_kwargs=validation_kwargs,
        )
    except Exception as exc:
        return {
            "symbol": symbol,
            "requested_symbol": symbol,
            "resolved_symbol": resolved_symbol or symbol,
            "status": "skipped",
            "error": str(exc),
        }
    result["requested_symbol"] = symbol
    result["resolved_symbol"] = resolved_symbol or symbol
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoML multi-symbol validation report")
    parser.add_argument("ticker", nargs="?", default="AAPL", help="Fallback stock ticker")
    parser.add_argument("--symbols", default="", help="Comma-separated tickers")
    parser.add_argument("--period", default="1y", help="History period for MarketDataFetcher")
    parser.add_argument("--pop", type=int, default=50, help="Population size")
    parser.add_argument("--gen", type=int, default=10, help="Generations")
    parser.add_argument("--strategy", default="ENSEMBLE_VOTE", help="AutoML strategy type or label")
    parser.add_argument("--fitness", default="composite", choices=["composite", "sharpe"])
    parser.add_argument(
        "--validation",
        default="walk_forward",
        choices=["train_test", "walk_forward"],
        help="Validation method",
    )
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--train-window", type=int, default=126)
    parser.add_argument("--test-window", type=int, default=21)
    parser.add_argument("--min-trades", type=int, default=1)
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols, fallback_ticker=args.ticker)
    strategy_type = normalize_strategy_type(args.strategy)
    strategy_spec = get_strategy_spec(strategy_type)
    validation_kwargs = build_validation_kwargs(
        validation_method=args.validation,
        train_ratio=args.train_ratio,
        train_window=args.train_window,
        test_window=args.test_window,
        min_trades=args.min_trades,
    )

    print("=== AutoML Multi-Symbol Validation Report ===")
    print(
        f"Symbols={', '.join(symbols)} | Strategy={strategy_spec.display_name} | "
        f"Fitness={args.fitness} | Validation={args.validation}"
    )

    results = []
    for symbol in symbols:
        print(f"\n[{symbol}] Fetching data...")
        result = run_symbol_optimization(
            symbol=symbol,
            period=args.period,
            strategy_type=strategy_type,
            fitness_metric=args.fitness,
            population_size=args.pop,
            generations=args.gen,
            validation_method=args.validation,
            validation_kwargs=validation_kwargs,
        )
        results.append(result)
        if result.get("status") == "skipped":
            print(f"[{symbol}] {result.get('error')}")
            continue

        validation = result.get("validation", {})
        guard = validation.get("overfit_guard", {}) if isinstance(validation, dict) else {}
        print(
            f"[{result.get('resolved_symbol') or symbol}] best={result.get('best_fitness'):.4f} "
            f"guard_pass={guard.get('passes', True)}"
        )

    report = build_multi_symbol_validation_report(results, requested_symbols=symbols)
    path = save_multi_symbol_validation_report(report)

    print("\n=== Report Summary ===")
    print(f"Validated symbols: {report['validated_symbol_count']}/{report['symbol_count']}")
    print(f"Guard pass/fail: {report['guard_pass_count']}/{report['guard_fail_count']}")
    print(f"Best usable symbol: {report['best_usable_symbol']}")
    print(f"Saved report: {path}")


if __name__ == "__main__":
    main()

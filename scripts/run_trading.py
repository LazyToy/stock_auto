"""Unified trading entrypoint."""

import argparse
from pathlib import Path
from typing import Dict, List

from src.broker.kis import KISBroker
from src.utils.execution_mode import (
    CONFIRM_ORDER_SUBMISSION_FLAG_HELP,
    CONFIRM_REAL_BROKER_FLAG_HELP,
    DRY_RUN_FLAG_HELP,
    LIVE_FLAG_HELP,
    MOCK_ORDER_FLAG_HELP,
    REAL_BROKER_FLAG_HELP,
    add_execution_mode_arguments,
    describe_execution_mode,
    emit_execution_banner,
    resolve_execution_flags,
    validate_execution_mode_or_exit,
)
from src.utils.runtime_clients import build_kis_broker, build_kis_client
from src.utils.logger import setup_logging

logger = setup_logging()
DEFAULT_BROKER_IS_MOCK = True
LIVE_FLAG_HELP = "주문 제출 실행 (기본값: broker=mock, orders=dry-run)"
DRY_RUN_FLAG_HELP = "mock broker + dry-run (기본값)"
LIVE_ALIAS_FLAG_HELP = "legacy alias for --mock-order"
DEFAULT_ML_COMPARISON_STRATEGIES = ["ml_rf", "ml_gb", "ensemble"]

try:
    from src.config import Config
    from src.data.api_client import KISAPIClient
    from src.live.engine import LiveTradingEngine
    from src.trader.auto_trader import AutoTrader

    TRADING_AVAILABLE = True
except ImportError as exc:
    logger.warning(f"트레이딩 모듈 로드 실패: {exc}")
    TRADING_AVAILABLE = False

try:
    from src.portfolio import MultiPortfolioManager, PortfolioConfig

    PORTFOLIO_AVAILABLE = True
except ImportError:
    PORTFOLIO_AVAILABLE = False

try:
    from src.strategies.ml_strategy import (
        EnsembleMLStrategy,
        GradientBoostingStrategy,
        MLPrediction,
        RandomForestStrategy,
    )

    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False


class StrategyFactory:
    """Factory for strategy construction."""

    @staticmethod
    def create(strategy_type: str, **kwargs):
        if strategy_type == "momentum":
            return {"type": "traditional", "style": "momentum"}
        if strategy_type == "value":
            return {"type": "traditional", "style": "value"}
        if strategy_type == "ml_rf":
            if not ML_AVAILABLE:
                raise ImportError("ML 전략 사용 불가. pip install scikit-learn")
            return RandomForestStrategy(**kwargs)
        if strategy_type == "ml_gb":
            if not ML_AVAILABLE:
                raise ImportError("ML 전략 사용 불가. pip install scikit-learn")
            return GradientBoostingStrategy(**kwargs)
        if strategy_type == "ensemble":
            if not ML_AVAILABLE:
                raise ImportError("ML 전략 사용 불가. pip install scikit-learn")
            return EnsembleMLStrategy(**kwargs)
        raise ValueError(f"지원하지 않는 전략: {strategy_type}")


class _ReportingBroker:
    """Delegate broker calls while capturing order submissions."""

    def __init__(self, broker):
        self._broker = broker
        self.orders: List[Dict[str, object]] = []

    def place_order(self, order, exchange: str = "NASD"):
        self.orders.append(
            {
                "symbol": order.symbol,
                "side": order.side.name,
                "quantity": order.quantity,
                "exchange": exchange,
            }
        )
        return self._broker.place_order(order, exchange=exchange)

    def __getattr__(self, name):
        return getattr(self._broker, name)


def _find_latest_runtime_model_path(market: str, strategy_type: str) -> Path | None:
    model_dir = Config.BASE_DIR / "models"
    if not model_dir.exists():
        return None

    strategy_names = [strategy_type]
    if strategy_type == "ensemble":
        strategy_names.append("ml_ensemble")

    candidates = []
    for name in strategy_names:
        candidates.extend(model_dir.glob(f"{market.lower()}_{name}_*.pkl"))

    if not candidates:
        return None

    def _sort_key(path: Path) -> tuple[float, str]:
        try:
            return (path.stat().st_mtime, path.name)
        except OSError:
            return (float("-inf"), path.name)

    return max(candidates, key=_sort_key)


def _try_load_runtime_ml_model(strategy, market: str, strategy_type: str) -> Path | None:
    load_fn = getattr(strategy, "load_model", None)
    if not callable(load_fn):
        return None

    model_path = _find_latest_runtime_model_path(market, strategy_type)
    if model_path is None:
        logger.info(f"No saved runtime ML model found for {market}/{strategy_type}")
        return None

    try:
        load_fn(str(model_path))
    except Exception as exc:
        logger.warning(f"Failed to load runtime ML model {model_path}: {exc}")
        return None

    logger.info(f"Loaded runtime ML model: {model_path}")
    return model_path


def run_single_strategy(
    market: str,
    strategy_type: str,
    dry_run: bool = True,
    capital: float = 1_000_000,
    is_mock: bool = DEFAULT_BROKER_IS_MOCK,
):
    logger.info(f"=== 단일 전략 모드: {strategy_type} ({market}) ===")

    if not TRADING_AVAILABLE:
        logger.error("트레이딩 모듈이 필요합니다")
        return

    universe = Config.load_universe().get(market, [])
    if not universe:
        raise ValueError(
            f"유니버스 설정이 없습니다. config/universe.json에서 '{market}' 를 확인하세요"
        )

    api_client = build_kis_client(
        market=market,
        is_mock=is_mock,
        client_cls=KISAPIClient,
    )
    broker = _ReportingBroker(
        build_kis_broker(
            market=market,
            is_mock=is_mock,
            broker_cls=KISBroker,
        )
    )
    style = strategy_type.upper() if strategy_type in ["momentum", "value"] else "VALUE"

    trader = AutoTrader(
        api_client=api_client,
        broker=broker,
        universe=universe,
        max_stocks=5,
        dry_run=dry_run,
        market=market,
        style=style,
    )

    loaded_model_path = None
    strategy_name = strategy_type
    if strategy_type.startswith("ml_") or strategy_type == "ensemble":
        ml_strategy = StrategyFactory.create(strategy_type)
        loaded_model_path = _try_load_runtime_ml_model(ml_strategy, market, strategy_type)
        trader.set_ml_strategy(ml_strategy)
        strategy_name = getattr(ml_strategy, "name", strategy_type)
        logger.info(f"ML 전략 활성화: {strategy_type}")

    logger.info(f"실행 모드: {describe_execution_mode(is_mock, dry_run)}")
    logger.info(f"트레이딩 시작 (dry_run={dry_run})")
    trader.run_rebalancing()
    return trader


def run_enhanced_strategy(
    market: str,
    base_strategy: str = "momentum",
    ai_filter: str = "ml_rf",
    dry_run: bool = True,
    confidence_threshold: float = 0.6,
    is_mock: bool = DEFAULT_BROKER_IS_MOCK,
):
    logger.info(f"=== 강화 모드: {base_strategy} + {ai_filter} ({market}) ===")

    if not TRADING_AVAILABLE or not ML_AVAILABLE:
        logger.error("트레이딩 및 ML 모듈이 필요합니다")
        return

    universe = Config.load_universe().get(market, [])
    if not universe:
        raise ValueError(
            f"유니버스 설정이 없습니다. config/universe.json에서 '{market}' 를 확인하세요"
        )

    api_client = build_kis_client(
        market=market,
        is_mock=is_mock,
        client_cls=KISAPIClient,
    )
    broker = build_kis_broker(
        market=market,
        is_mock=is_mock,
        broker_cls=KISBroker,
    )
    trader = AutoTrader(
        api_client=api_client,
        broker=broker,
        universe=universe,
        max_stocks=5,
        dry_run=dry_run,
        market=market,
        style=base_strategy.upper(),
    )

    ml_filter = StrategyFactory.create(ai_filter)
    _try_load_runtime_ml_model(ml_filter, market, ai_filter)
    trader.set_ml_filter(ml_filter, confidence_threshold)

    logger.info(f"AI 필터 활성화: {ai_filter} (임계값 {confidence_threshold})")
    logger.info(f"실행 모드: {describe_execution_mode(is_mock, dry_run)}")
    logger.info(f"트레이딩 시작 (dry_run={dry_run})")
    trader.run_rebalancing()
    return trader


def run_multi_portfolio(
    portfolios: List[Dict],
    total_capital: float = 2_000_000,
    dry_run: bool = True,
    is_mock: bool = DEFAULT_BROKER_IS_MOCK,
):
    logger.info(f"=== 멀티 포트폴리오 모드 (총 {total_capital:,.0f}) ===")

    if not PORTFOLIO_AVAILABLE:
        logger.error("멀티 포트폴리오 모듈이 필요합니다")
        return

    manager = MultiPortfolioManager(total_capital=total_capital)

    for portfolio_def in portfolios:
        config = PortfolioConfig(
            name=portfolio_def["name"],
            strategy_name=portfolio_def["strategy"],
            allocation_pct=portfolio_def["allocation"],
            market=portfolio_def.get("market", "KR"),
            max_stocks=portfolio_def.get("max_stocks", 5),
        )
        manager.add_portfolio(config)
        logger.info(f"포트폴리오 추가: {portfolio_def['name']} ({portfolio_def['allocation']}%)")

    if TRADING_AVAILABLE:
        api_clients = {}

        for name, portfolio in manager.portfolios.items():
            config = portfolio["config"]
            universe = Config.load_universe().get(config.market, [])
            if not universe:
                raise ValueError(
                    f"유니버스 설정이 없습니다. config/universe.json에서 '{config.market}' 를 확인하세요"
                )

            if config.market not in api_clients:
                api_clients[config.market] = build_kis_client(
                    market=config.market,
                    is_mock=is_mock,
                    client_cls=KISAPIClient,
                )
            broker = build_kis_broker(
                market=config.market,
                is_mock=is_mock,
                broker_cls=KISBroker,
            )
            api_client = api_clients[config.market]

            trader = AutoTrader(
                api_client=api_client,
                broker=broker,
                universe=universe,
                max_stocks=config.max_stocks,
                dry_run=dry_run,
                market=config.market,
                style=config.strategy_name.upper()
                if config.strategy_name in ["momentum", "value"]
                else "VALUE",
            )

            logger.info(f"\n--- {name} 실행 중 ---")
            trader.run_rebalancing()

    print(manager.generate_report())
    return manager


def run_ml_strategy_comparison(
    market: str,
    strategy_types: List[str] | None = None,
    dry_run: bool = True,
    capital: float = 1_000_000,
    is_mock: bool = DEFAULT_BROKER_IS_MOCK,
):
    strategy_types = strategy_types or list(DEFAULT_ML_COMPARISON_STRATEGIES)
    rows = []

    for strategy_type in strategy_types:
        trader = run_single_strategy(
            market=market,
            strategy_type=strategy_type,
            dry_run=dry_run,
            capital=capital,
            is_mock=is_mock,
        )
        if hasattr(trader, "comparison_report"):
            row = dict(getattr(trader, "comparison_report"))
        else:
            target_tickers = list(getattr(trader, "last_target_tickers", []) or [])
            ml_strategy = getattr(trader, "_ml_strategy", None)
            row = {
                "strategy_type": strategy_type,
                "strategy_name": getattr(ml_strategy, "name", strategy_type),
                "target_count": len(target_tickers),
                "target_tickers": target_tickers,
                "ordered_symbols": target_tickers,
                "order_count": len(target_tickers),
                "model_path": getattr(trader, "runtime_model_path", None),
                "execution_mode": describe_execution_mode(is_mock, dry_run),
            }
        rows.append(row)

    return {
        "market": market,
        "rows": rows,
        "text": format_ml_strategy_comparison_report(rows, market=market),
    }


def format_ml_strategy_comparison_report(rows: List[Dict], *, market: str | None = None) -> str:
    if not rows:
        return ""

    title = "ML strategy comparison"
    if market:
        title = f"ML Strategy Comparison ({market})"

    lines = [title]
    for item in rows:
        strategy_type = item.get("strategy_type", item.get("strategy", "unknown"))
        strategy_name = item.get("strategy_name", item.get("ml_strategy_name", strategy_type))
        ordered_symbols = item.get("ordered_symbols")
        if ordered_symbols is None:
            ordered_symbols = item.get("target_tickers", [])
        model_path = item.get("model_path")
        order_count = int(item.get("order_count", item.get("target_count", len(ordered_symbols))))
        symbols_text = ",".join(ordered_symbols)
        lines.append(
            f"{strategy_type} | "
            f"name={strategy_name} | "
            f"orders={order_count} | "
            f"symbols={symbols_text} | "
            f"model={model_path}"
        )

    return "\n".join(lines)


def print_ml_strategy_comparison_report(report) -> None:
    if not report:
        return

    if isinstance(report, dict):
        text = report.get("text", "")
    else:
        text = format_ml_strategy_comparison_report(report)

    if text:
        print(f"\n=== {text} ===" if "\n" not in text else f"\n=== {text.splitlines()[0]} ===")
        for line in text.splitlines()[1:]:
            print(line)


def main():
    parser = argparse.ArgumentParser(description="통합 트레이딩 시스템")
    parser.add_argument(
        "--mode",
        type=str,
        default="single",
        choices=["single", "enhanced", "multi", "compare"],
        help="실행 모드: single(단일), enhanced(AI강화), multi(멀티포트폴리오)",
    )
    parser.add_argument(
        "--market",
        type=str,
        default="KR",
        choices=["KR", "US"],
        help="시장: KR(국내), US(미국)",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="momentum",
        choices=["momentum", "value", "ml_rf", "ml_gb", "ensemble"],
        help="전략 선택",
    )
    parser.add_argument(
        "--ai-filter",
        type=str,
        default="ml_rf",
        choices=["ml_rf", "ml_gb", "ensemble"],
        help="AI 필터 전략 (enhanced 모드)",
    )
    parser.add_argument("--capital", type=float, default=1_000_000, help="투자 자본")

    parser.add_argument("--compare-ml", action="store_true", help="Run mock/runtime comparison across ML strategies")
    parser.add_argument(
        "--ml-strategies",
        nargs="+",
        default=list(DEFAULT_ML_COMPARISON_STRATEGIES),
        choices=DEFAULT_ML_COMPARISON_STRATEGIES,
        help="ML strategies to include in comparison mode",
    )

    add_execution_mode_arguments(
        parser,
        live_flag_help=LIVE_ALIAS_FLAG_HELP,
    )
    args = parser.parse_args()

    is_mock, dry_run = resolve_execution_flags(args)

    emit_execution_banner(
        title="통합 트레이딩 시스템",
        details=[
            f"모드: {args.mode}",
            f"시장: {args.market}",
            f"전략: {args.strategy}",
            f"자본: {args.capital:,.0f}",
        ],
        is_mock=is_mock,
        dry_run=dry_run,
    )

    validate_execution_mode_or_exit(
        args,
        is_mock=is_mock,
        dry_run=dry_run,
        real_broker_error="ERROR: --real-broker requires --confirm-real-broker",
    )

    compare_requested = getattr(args, "compare_ml", False) or getattr(args, "mode", None) == "compare"
    if compare_requested:
        comparison_kwargs = {
            "market": args.market,
            "dry_run": dry_run,
            "capital": args.capital,
            "is_mock": is_mock,
        }
        if getattr(args, "compare_ml", False):
            comparison_kwargs["strategy_types"] = getattr(
                args,
                "ml_strategies",
                list(DEFAULT_ML_COMPARISON_STRATEGIES),
            )
        report = run_ml_strategy_comparison(**comparison_kwargs)
        print_ml_strategy_comparison_report(report)
        return

    if args.mode == "single":
        run_single_strategy(
            market=args.market,
            strategy_type=args.strategy,
            dry_run=dry_run,
            capital=args.capital,
            is_mock=is_mock,
        )
    elif args.mode == "enhanced":
        run_enhanced_strategy(
            market=args.market,
            base_strategy=args.strategy,
            ai_filter=args.ai_filter,
            dry_run=dry_run,
            is_mock=is_mock,
        )
    elif args.mode == "multi":
        portfolios = [
            {"name": "KR_모멘텀", "strategy": "momentum", "market": "KR", "allocation": 50},
            {"name": "US_AI", "strategy": "ml_rf", "market": "US", "allocation": 50},
        ]
        run_multi_portfolio(
            portfolios=portfolios,
            total_capital=args.capital,
            dry_run=dry_run,
            is_mock=is_mock,
        )


if __name__ == "__main__":
    main()

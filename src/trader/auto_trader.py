"""자동 매매 실행기 (Auto Trader)

StockSelector를 통해 종목을 선정하고,
KISAPIClient를 통해 실제 매매 주문을 실행합니다.
또한 Stop Loss, Trailing Stop 등 출구 전략을 관리합니다.
"""

import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, cast

import pandas as pd

from src.config import Config
from src.data.api_client import KISAPIClient
from src.data.models import Order, OrderSide, OrderType
from src.strategies.selector import StockSelector
from src.trader.state_manager import StateManager
from src.utils.notification import send_notification
from src.optimization.automl_runtime import (
    apply_automl_candidate_adjustment,
    load_automl_artifacts_from_dir,
)

# Exit 전략 모듈 import
try:
    from src.strategies.exit_base import (
        BaseExitStrategy,
        CompositeExitStrategy,
        ExitSignal,
        PositionContext,
    )
    from src.strategies.exit_strategies import (
        ATRTrailingStop,
        FixedStopLoss,
        MinScoreExit,
        PartialTakeProfit,
        PercentTrailingStop,
        TimeBasedExit,
    )
    EXIT_MODULE_AVAILABLE = True
except ImportError:
    EXIT_MODULE_AVAILABLE = False

from src.utils.logger import get_logger, setup_logging

# 로거 설정
logger = setup_logging("AutoTrader")


from src.analysis.sentiment import SentimentAnalyzer


@dataclass(frozen=True)
class SmartMoneyTradingConfig:
    """자동매매 Smart Money 연동 설정."""

    enabled: bool = False
    mode: str = "advisory"
    buy_score_bonus: float = 0.0

    @property
    def is_filter_enabled(self) -> bool:
        """Smart Money 신호가 후보 제외에 영향을 줄 수 있는지 반환한다."""
        return self.enabled and self.mode == "filter"

    @property
    def is_advisory_enabled(self) -> bool:
        """Smart Money 신호를 로그/참고 용도로만 사용할지 반환한다."""
        return self.enabled and self.mode in {"advisory", "filter", "execute"}


SmartMoneySignalResolver = Callable[[str, str, str], Any]
SMART_MONEY_BUY_BONUS_MIN_SCORE = 1.0


@dataclass(frozen=True)
class AutoMLTradingConfig:
    """자동매매 AutoML 연동 설정."""

    enabled: bool = False
    mode: str = "advisory"
    params_path: str = "data/automl_params"
    min_fitness: float = 0.0
    max_bonus: float = 0.0

    @property
    def is_score_bonus_enabled(self) -> bool:
        return self.enabled and self.mode == "score_bonus"

    @property
    def is_advisory_enabled(self) -> bool:
        return self.enabled and self.mode in {"advisory", "score_bonus"}


def build_smart_money_trading_config(
    values: Mapping[str, object] | None,
) -> SmartMoneyTradingConfig:
    """YAML smart_money 값을 자동매매 연동 설정으로 변환한다."""
    if values is None:
        return SmartMoneyTradingConfig()

    enabled = _coerce_bool(values.get("enabled", False))
    mode = _coerce_mode(values.get("mode", "advisory"))
    buy_score_bonus = _coerce_float(values.get("buy_score_bonus", 0.0), default=0.0)

    return SmartMoneyTradingConfig(
        enabled=enabled,
        mode=mode,
        buy_score_bonus=max(0.0, buy_score_bonus),
    )


def build_automl_trading_config(values: Mapping[str, object] | None) -> AutoMLTradingConfig:
    """YAML automl 값을 자동매매 연동 설정으로 변환한다."""
    if values is None:
        return AutoMLTradingConfig()

    enabled = _coerce_bool(values.get("enabled", False))
    mode = _coerce_automl_mode(values.get("mode", "advisory"))
    params_path = str(values.get("params_path", "data/automl_params"))
    min_fitness = _coerce_float(values.get("min_fitness", 0.0), default=0.0)
    max_bonus = _coerce_float(values.get("max_bonus", 0.0), default=0.0)

    return AutoMLTradingConfig(
        enabled=enabled,
        mode=mode,
        params_path=params_path,
        min_fitness=min_fitness,
        max_bonus=max(0.0, max_bonus),
    )


def _coerce_bool(value: object) -> bool:
    """설정 값을 bool로 보수적으로 변환한다."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_mode(value: object) -> str:
    """지원 모드를 advisory/filter/execute 중 하나로 정규화한다."""
    if not isinstance(value, str):
        logger.warning("Smart Money mode가 문자열이 아니어서 advisory로 처리합니다.")
        return "advisory"

    mode = value.strip().lower()
    if mode in {"advisory", "filter", "execute"}:
        return mode

    logger.warning("지원하지 않는 Smart Money mode=%s 값을 advisory로 처리합니다.", value)
    return "advisory"


def _coerce_automl_mode(value: object) -> str:
    """AutoML mode를 advisory/score_bonus 중 하나로 정규화한다."""
    if not isinstance(value, str):
        logger.warning("AutoML mode가 문자열이 아니어서 advisory로 처리합니다.")
        return "advisory"

    mode = value.strip().lower()
    if mode in {"advisory", "score_bonus"}:
        return mode

    logger.warning("지원하지 않는 AutoML mode=%s 값을 advisory로 처리합니다.", value)
    return "advisory"


def _coerce_float(value: object, *, default: float) -> float:
    """설정 값을 float로 변환하고 실패하면 기본값을 반환한다."""
    if not isinstance(value, (str, int, float)):
        logger.warning("Smart Money 숫자 설정을 해석하지 못해 기본값을 사용합니다: %s", value)
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("Smart Money 숫자 설정을 해석하지 못해 기본값을 사용합니다: %s", value)
        return default


def _coerce_selector_score(value: object, *, symbol: str) -> float:
    """selector score를 안전하게 숫자로 변환한다."""
    try:
        score = float(cast(Any, value))
    except (TypeError, ValueError):
        logger.warning(
            "selector score 변환 실패: symbol=%s score=%s. 0.0으로 처리합니다.",
            symbol,
            value,
        )
        return 0.0

    if math.isfinite(score):
        return score

    logger.warning(
        "selector score 변환 실패: symbol=%s score=%s. 0.0으로 처리합니다.",
        symbol,
        value,
    )
    return 0.0


# 텔레그램 알림 모듈 import
try:
    from src.utils.telegram_notifier import TelegramNotifier, TradeAlert, get_notifier
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

# 데이터베이스 모듈 import
try:
    from src.utils.database import DatabaseManager, PortfolioSnapshot, TradeRecord, get_db
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

# 감사 로그 모듈 import
try:
    from src.utils.audit_log import AuditEvent, EventType, get_audit_logger
    AUDIT_LOG_AVAILABLE = True
except ImportError:
    AUDIT_LOG_AVAILABLE = False

class AutoTrader:
    def __init__(
        self, 
        api_client: KISAPIClient, 
        universe: List[str] = None, 
        max_stocks: int = 5,
        dry_run: bool = True,
        market: str = "KR", # "KR" or "US"
        style: str = "VALUE", # "VALUE" or "GROWTH"
        exit_strategy: Optional['BaseExitStrategy'] = None,
        broker=None,
        smart_money_signal_resolver: Optional[SmartMoneySignalResolver] = None,
    ):
        """초기화"""
        self.api_client = api_client
        self.broker = broker
        self.universe = universe or Config.load_universe().get(market, [])
        self.max_stocks = max_stocks
        self.dry_run = dry_run
        self.market = market
        self.style = style
        self.last_target_tickers: List[str] = []
        self.last_top_stocks: List[Dict] = []
        self.automl_config = self._load_automl_trading_config()
        self.smart_money_config = self._load_smart_money_trading_config()
        self.smart_money_signal_resolver = (
            smart_money_signal_resolver
            if smart_money_signal_resolver is not None
            else self._resolve_smart_money_signal
        )
        self._smart_money_fetcher: Any = None
        
        benchmark = "^GSPC" if market == "US" else "^KS11"
        self.selector = StockSelector(self.universe, benchmark=benchmark, style=style)
        self.state_manager = StateManager()
        self.sentiment_analyzer = SentimentAnalyzer() # 감성 분석기 초기화
        
        # Exit 전략 파라미터: config/trading.yaml 우선, 없으면 기본값
        _stop_loss_pct = -0.07
        _trail_activation_pct = 0.10
        _trail_pct = 0.05
        _min_score = 1.0
        try:
            import yaml as _yaml
            _yaml_path = Config.BASE_DIR / "config" / "trading.yaml"
            with open(_yaml_path, "r", encoding="utf-8") as _f:
                _trading_cfg = _yaml.safe_load(_f)
            _exit_cfg = _trading_cfg.get("exit_strategy", {})
            _stop_loss_pct = float(_exit_cfg.get("stop_loss_pct", _stop_loss_pct))
            _trail_activation_pct = float(_exit_cfg.get("trailing_stop_activation_pct", _trail_activation_pct))
            _trail_pct = float(_exit_cfg.get("trailing_stop_trail_pct", _trail_pct))
            _min_score = float(_exit_cfg.get("min_score", _min_score))
        except Exception:
            pass  # 파일 없거나 파싱 오류 시 기본값 유지

        # Exit 전략 초기화 (기본값: 복합 전략)
        if exit_strategy is not None:
            self.exit_strategy = exit_strategy
        elif EXIT_MODULE_AVAILABLE:
            self.exit_strategy = CompositeExitStrategy([
                FixedStopLoss(stop_pct=_stop_loss_pct),
                PercentTrailingStop(activation_pct=_trail_activation_pct, trail_pct=_trail_pct),
                MinScoreExit(min_score=_min_score),
            ])
            logger.info(
                f"Exit 전략 모듈 로드 완료: FixedStopLoss({_stop_loss_pct*100:.0f}%), "
                f"PercentTrailingStop(+{_trail_activation_pct*100:.0f}%/-{_trail_pct*100:.0f}%), "
                f"MinScoreExit({_min_score})"
            )
        else:
            self.exit_strategy = None
            logger.warning("Exit 전략 모듈 사용 불가 - 기본 로직 사용")
        
        # 진입일 추적 (TimeBasedExit 용)
        self._entry_dates: Dict[str, datetime] = {}
        
        # 텔레그램 알림 초기화
        if TELEGRAM_AVAILABLE:
            self.notifier = get_notifier()
            if self.notifier.enabled:
                logger.info("텔레그램 알림 활성화됨")
        else:
            self.notifier = None
        
        # 데이터베이스 초기화
        if DATABASE_AVAILABLE:
            self.db = get_db()
            logger.info("데이터베이스 연결 완료")
        else:
            self.db = None
        
        # 감사 로거 초기화
        if AUDIT_LOG_AVAILABLE:
            self.audit_logger = get_audit_logger()
            logger.info("감사 로그 활성화됨")
        else:
            self.audit_logger = None

        # 시장 레짐 감지기 초기화
        try:
            from src.analysis.market_data import MarketDataFetcher
            from src.analysis.regime import RegimeDetector
            self.market_data_fetcher = MarketDataFetcher()
            self.regime_detector = RegimeDetector()
            
            # 모델 로드 (존재할 경우)
            model_path = Config.DATA_DIR / "regime_model.pkl"
            if model_path.exists():
                if hasattr(self.regime_detector, "load_model"):
                    try:
                        self.regime_detector.load_model(str(model_path))
                    except Exception as exc:
                        logger.warning(f"Regime model load skipped: {exc}")
                    else:
                        logger.info(f"Regime model loaded: {model_path}")
                    logger.info(f"레짐 감지 모델 로드 완료: {model_path}")
                else:
                    logger.warning(
                        f"레짐 감지 모델 로드를 건너뜁니다. load_model 미구현: {model_path}"
                    )
            else:
                logger.warning("레짐 감지 모델이 없습니다. 학습이 필요합니다.")
        except ImportError as e:
            logger.warning(f"레짐 감지 모듈 로드 실패: {e}")
            self.regime_detector = None

    def set_ml_strategy(self, strategy):
        """ML 전략 설정"""
        self._ml_strategy = strategy
        self._use_ml = True
        logger.info(f"ML 전략 설정됨: {strategy.name}")

    def set_ml_filter(self, filter_strategy, threshold: float = 0.6):
        """ML 필터 설정"""
        self._ml_filter = filter_strategy
        self._use_ml_filter = True
        self._ml_confidence_threshold = threshold
        logger.info(f"ML 필터 설정됨: {filter_strategy.name}, Threshold: {threshold}")

    def _load_smart_money_trading_config(self) -> SmartMoneyTradingConfig:
        """config/trading.yaml의 Smart Money 자동매매 연동 설정을 읽는다."""
        try:
            import yaml as _yaml
            yaml_path = Config.BASE_DIR / "config" / "trading.yaml"
            with open(yaml_path, "r", encoding="utf-8") as file:
                trading_cfg = _yaml.safe_load(file) or {}
            smart_money_cfg = trading_cfg.get("smart_money", {})
            if not isinstance(smart_money_cfg, Mapping):
                logger.warning("smart_money 설정이 dict가 아니어서 기본값을 사용합니다.")
                return SmartMoneyTradingConfig()
            config = build_smart_money_trading_config(smart_money_cfg)
            if config.enabled and config.mode == "execute":
                logger.warning(
                    "Smart Money execute 모드는 아직 주문 실행에 연결하지 않고 참고 로그로만 처리합니다."
                )
            return config
        except Exception as exc:
            logger.warning("Smart Money 자동매매 설정 로드 실패, 기본값을 사용합니다: %s", exc)
            return SmartMoneyTradingConfig()

    def _load_automl_trading_config(self) -> AutoMLTradingConfig:
        """config/trading.yaml의 AutoML 자동매매 보조 설정을 읽는다."""
        try:
            import yaml as _yaml

            yaml_path = Config.BASE_DIR / "config" / "trading.yaml"
            with open(yaml_path, "r", encoding="utf-8") as file:
                trading_cfg = _yaml.safe_load(file) or {}
            automl_cfg = trading_cfg.get("automl", {})
            if not isinstance(automl_cfg, Mapping):
                logger.warning("automl 설정이 dict가 아니어서 기본값을 사용합니다.")
                return AutoMLTradingConfig()
            return build_automl_trading_config(automl_cfg)
        except Exception as exc:
            logger.warning("AutoML 자동매매 설정 로드 실패, 기본값을 사용합니다: %s", exc)
            return AutoMLTradingConfig()

    def _resolve_smart_money_signal(self, symbol: str, market: str, exchange: str) -> object:
        """실제 Smart Money 분석 파이프라인으로 symbol의 최종 신호를 계산한다."""
        from src.analysis.smart_money import (
            SignalConfig,
            analyze_multi_timeframe_patterns,
            combine_multi_timeframe_signals,
            load_smart_money_analysis_config,
        )
        from src.analysis.timeframes import MultiTimeframeFetcher

        if self._smart_money_fetcher is None:
            self._smart_money_fetcher = MultiTimeframeFetcher()

        dataset = self._smart_money_fetcher.fetch_symbol(symbol, market=market, exchange=exchange)
        frames = dataset.successful_ohlcv()
        signal_config, pattern_config = load_smart_money_analysis_config()
        if signal_config is None:
            signal_config = SignalConfig()
        reports = analyze_multi_timeframe_patterns(frames, pattern_config=pattern_config)
        return combine_multi_timeframe_signals(reports, signal_config)

    def _apply_automl_candidate_adjustment(self, all_results: pd.DataFrame) -> pd.DataFrame:
        """AutoML 결과 artifact를 selector 후보에 참고 정보/제한적 bonus로 반영한다."""
        config = self.automl_config
        if not config.is_advisory_enabled or all_results.empty:
            return all_results

        params_path = Path(config.params_path)
        if not params_path.is_absolute():
            params_path = Config.BASE_DIR / params_path

        artifacts = load_automl_artifacts_from_dir(params_path)
        if not artifacts:
            logger.info("AutoML artifact가 없어 selector 후보 보정을 생략합니다: %s", params_path)
            return all_results

        max_bonus = config.max_bonus if config.is_score_bonus_enabled else 0.0
        adjusted = apply_automl_candidate_adjustment(
            all_results,
            artifacts,
            min_fitness=config.min_fitness,
            max_bonus=max_bonus,
        )
        matched = int(adjusted.get("automl_strategy", pd.Series(dtype=object)).notna().sum())
        logger.info(
            "AutoML 후보 보정 완료: mode=%s matched=%s max_bonus=%.4f",
            config.mode,
            matched,
            max_bonus,
        )
        return adjusted

    def _apply_smart_money_candidate_filter(self, all_results: pd.DataFrame) -> pd.DataFrame:
        """Smart Money 설정에 따라 selector 후보를 참고/필터링한다."""
        config = self.smart_money_config
        if not config.is_advisory_enabled or all_results.empty:
            return all_results

        rows: list[pd.Series[Any]] = []
        for _, row in all_results.iterrows():
            updated_row = row.copy()
            symbol = str(row.get("ticker", "")).strip()
            exchange = str(row.get("exchange", "KR" if self.market == "KR" else "NASD"))

            signal_value = "UNKNOWN"
            final_decision = "포함"
            reason = "Smart Money 신호를 참고 정보로만 기록"
            selector_score = _coerce_selector_score(row.get("score", 0.0), symbol=symbol)
            updated_row["score"] = selector_score
            try:
                if not symbol:
                    signal_value = "SKIPPED"
                    updated_row["smart_money_signal"] = signal_value
                    reason = "ticker가 비어 있어 Smart Money 분석을 생략"
                else:
                    signal = self.smart_money_signal_resolver(symbol, self.market, exchange)
                    signal_value = str(getattr(signal, "signal", "UNKNOWN")).upper()
                    updated_row["smart_money_signal"] = signal_value
                    updated_row["smart_money_confidence"] = getattr(signal, "confidence", None)
                    updated_row["smart_money_score"] = getattr(signal, "score", None)

                    if (
                        config.is_filter_enabled
                        and signal_value == "BUY"
                        and config.buy_score_bonus > 0
                        and selector_score >= SMART_MONEY_BUY_BONUS_MIN_SCORE
                    ):
                        updated_row["score"] = selector_score + config.buy_score_bonus
                        reason = "Smart Money BUY bonus 반영"

                    if config.is_filter_enabled and signal_value == "SELL":
                        final_decision = "제외"
                        reason = "Smart Money SELL 신호로 신규 매수 후보 제외"
            except Exception as exc:
                signal_value = "ERROR"
                updated_row["smart_money_signal"] = "ERROR"
                updated_row["smart_money_error"] = str(exc)
                reason = f"Smart Money 분석 실패로 selector 결과 유지: {exc}"

            self._log_smart_money_candidate_decision(
                symbol=symbol,
                selector_score=selector_score,
                smart_money_signal=signal_value,
                final_decision=final_decision,
                reason=reason,
            )
            if final_decision != "제외":
                rows.append(updated_row)

        if not rows:
            return cast(pd.DataFrame, all_results.iloc[0:0].copy())
        return cast(pd.DataFrame, pd.DataFrame(rows))

    def _log_smart_money_candidate_decision(
        self,
        *,
        symbol: str,
        selector_score: float,
        smart_money_signal: str,
        final_decision: str,
        reason: str,
    ) -> None:
        """dry-run에서 Smart Money 필터 판단 근거를 로그로 남긴다."""
        if not self.dry_run:
            return
        logger.info(
            "Smart Money dry-run: symbol=%s selector_score=%.4f signal=%s final=%s reason=%s",
            symbol,
            selector_score,
            smart_money_signal,
            final_decision,
            reason,
        )

    def _warn_smart_money_holding_signal(self, position: object) -> None:
        """보유 종목 Smart Money SELL 신호를 자동 청산 없이 경고로만 남긴다."""
        config = self.smart_money_config
        if not config.is_advisory_enabled:
            return

        symbol = str(getattr(position, "symbol", "")).strip()
        if not symbol:
            logger.warning("Smart Money 보유 경고 생략: position symbol이 비어 있습니다.")
            return

        exchange = str(getattr(position, "exchange", "KR" if self.market == "KR" else "NASD"))
        try:
            signal = self.smart_money_signal_resolver(symbol, self.market, exchange)
            signal_value = str(getattr(signal, "signal", "UNKNOWN")).upper()
            if signal_value != "SELL":
                return

            confidence = getattr(signal, "confidence", None)
            score = getattr(signal, "score", None)
            message = (
                "Smart Money SELL 보유 경고: "
                f"symbol={symbol} confidence={confidence} score={score}. "
                "자동 청산은 실행하지 않습니다."
            )
            logger.warning(message)
            send_notification(message)
        except Exception as exc:
            logger.warning("Smart Money 보유 종목 분석 실패로 exit 판단만 유지합니다: %s", exc)

    def _ensure_selector_data(self) -> None:
        if getattr(self.selector, "data", None):
            return

        download_fn = getattr(self.selector, "download_data", None)
        if callable(download_fn):
            try:
                download_fn()
            except Exception as exc:
                logger.warning(f"Selector data download failed: {exc}")

    def _extract_ml_signal(self, prediction) -> Optional[int]:
        if prediction is None:
            return None
        if hasattr(prediction, "signal"):
            return int(prediction.signal)
        if isinstance(prediction, (int, float)):
            return int(prediction)
        return None

    def _normalize_ml_predictions(self, predictions, expected_len: int) -> Optional[List[int]]:
        if predictions is None or hasattr(predictions, "signal"):
            return None

        try:
            values = predictions.tolist() if hasattr(predictions, "tolist") else list(predictions)
        except TypeError:
            return None

        if len(values) != expected_len:
            return None

        signals: List[int] = []
        for value in values:
            signal = self._extract_ml_signal(value)
            if signal is None:
                return None
            signals.append(signal)
        return signals

    def _predict_ml_candidate_signals(self, strategy, all_results) -> Optional[List[int]]:
        if all_results.empty:
            return None

        try:
            batch_predictions = strategy.predict(all_results)
        except Exception:
            batch_predictions = None

        normalized = self._normalize_ml_predictions(batch_predictions, len(all_results))
        if normalized is not None:
            return normalized

        is_trained = getattr(strategy, "is_trained", False) or getattr(strategy, "_is_trained", False)
        if not is_trained:
            return None

        self._ensure_selector_data()
        selector_data = getattr(self.selector, "data", {}) or {}
        if not selector_data:
            return None

        signals: List[int] = []
        for _, row in all_results.iterrows():
            ticker = row["ticker"]
            ticker_frame = selector_data.get(ticker)
            if ticker_frame is None or ticker_frame.empty:
                signals.append(0)
                continue

            try:
                prediction = strategy.predict(ticker_frame.copy())
                signal = self._extract_ml_signal(prediction)
                signals.append(0 if signal is None else signal)
            except Exception as exc:
                logger.warning(f"ML per-symbol prediction failed for {ticker}: {exc}")
                signals.append(0)

        return signals

    def run_rebalancing(self):
        """리밸런싱 실행 (run_daily_routine Alias)"""
        self.run_daily_routine()



    def monitor_realtime(self):
        """[1분 주기] 실시간 시세 감시 및 리스크 관리"""
        try:
            # 보유 잔고 조회 (실시간 현재가 포함)
            balance = self.api_client.get_balance()
            stocks = balance.get('stocks', [])
            
            # 대시보드 데이터 내보내기 (매 분 갱신)
            self.export_dashboard_state(balance)
            
            if not stocks:
                return

            logger.info(f"실시간 감시 중... (보유: {len(stocks)}종목)")
            
            for stock in stocks:
                # ... (기존 로직)
                ticker = stock['symbol']
                current_price = float(stock['current_price'])
                avg_price = float(stock['avg_price'])
                quantity = int(stock['quantity'])
                
                if quantity <= 0: continue
                
                return_rate = (current_price - avg_price) / avg_price
                
                if return_rate <= -0.10:
                    logger.warning(f"🚨 [손절매] {ticker}: 수익률 {return_rate*100:.2f}% <= -10% -> 전량 매도")
                    self._sell_stock(ticker, quantity, stock.get('exchange'))
                    continue
                # 3. 급락 감시 (Flash Crash Protection)
                pass
                
        except Exception as e:
            logger.error(f"실시간 감시 오류: {e}")

    def export_dashboard_state(self, balance: dict = None) -> None:
        """대시보드용 상태 파일(JSON) 업데이트"""

        try:
            if balance is None:
                balance = self.api_client.get_balance()
            
            total_asset = balance.get('total_asset', 0)
            deposit = balance.get('deposit', 0)
            stocks = balance.get('stocks', [])
            stock_value = total_asset - deposit
                
            state = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "market": self.market,
                "style": self.style,
                "total_asset": total_asset,
                "deposit": deposit,
                "stocks": stocks,
                "sentiment_score": "N/A" # 추후 구현
            }
            
            # 데이터 디렉토리 생성
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            
            import json
            file_path = Config.DATA_DIR / f"dashboard_{self.market.lower()}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            
            # DB에 포트폴리오 스냅샷 저장 (일별)
            if self.db and DATABASE_AVAILABLE:
                try:
                    from datetime import date
                    snapshot = PortfolioSnapshot(
                        date=date.today().isoformat(),
                        total_asset=float(total_asset),
                        deposit=float(deposit),
                        stock_value=float(stock_value),
                        stock_count=len(stocks),
                        market=self.market
                    )
                    self.db.insert_portfolio_snapshot(snapshot)
                except Exception as e:
                    logger.debug(f"포트폴리오 스냅샷 저장 실패: {e}")
                
        except Exception as e:
            logger.error(f"대시보드 데이터 내보내기 실패: {e}")

    def check_market_sentiment(self) -> None:
        """[1시간 주기] 뉴스 감성 분석 및 악재 대응"""

        try:
            logger.info("📰 뉴스 심리 분석 시작...")
            balance = self.api_client.get_balance()
            stocks = balance.get('stocks', [])
            
            for stock in stocks:
                ticker = stock['symbol']
                qty = int(stock['quantity'])
                
                if qty <= 0: continue
                
                # 뉴스 분석
                sentiment_score = self.sentiment_analyzer.analyze_ticker(ticker)
                
                if sentiment_score <= -0.5:
                    # 악재 발생: 보유 물량 50% 매도
                    sell_qty = max(1, qty // 2)
                    logger.warning(f"🚨 [악재 감지] {ticker}: 부정 점수 {sentiment_score} -> {sell_qty}주 긴급 매도")
                    self._sell_stock(ticker, sell_qty, stock.get('exchange'))
                    
        except Exception as e:
            logger.error(f"뉴스 분석 오류: {e}")

    def _sell_stock(self, ticker: str, quantity: int, exchange: str = None) -> None:
        """매도 주문 실행 래퍼"""

        if self.dry_run:
            logger.info(f"[모의 매도] {ticker} {quantity}주 (시장가)")
        else:
            # 실제 주문 (시장가)
            exchange = exchange or ("NASD" if self.market == "US" else "KR")
            current_price = self.api_client.get_current_price(ticker) if self.market == "US" else 0
            order = Order(
                symbol=ticker,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                price=current_price,
                quantity=quantity,
                created_at=datetime.now()
            )
            if self.broker is not None:
                self.broker.place_order(order, exchange=exchange)
            else:
                self.api_client.place_order(order, exchange=exchange)
        
    def run_daily_routine(self) -> None:
        """일일 매매 루틴 실행"""

        logger.info(f"=== 일일 자동 매매 루틴 시작 ({self.market}) ===")
        
        # 0. 시장 레짐 감지
        self._regime_position_multiplier = 1.0  # 기본값 (레짐 미감지 시 변경 없음)
        if self.regime_detector:
            try:
                logger.info("0. 시장 레짐 분석 중...")
                data = self.market_data_fetcher.get_regime_input_data()
                if not data.empty:
                    current_regime = self.regime_detector.predict_regime(data.iloc[[-1]])
                    logger.info(f"현재 시장 레짐: Regime-{current_regime} (0:Bullish/Stable, 1:Volatile, 2:Crash/Bearish - Estimated)")

                    # 레짐에 따른 포지션 크기 조정 (config/trading.yaml 우선, 없으면 기본값)
                    try:
                        import yaml
                        _yaml_path = Config.BASE_DIR / "config" / "trading.yaml"
                        with open(_yaml_path, "r", encoding="utf-8") as _f:
                            _trading_cfg = yaml.safe_load(_f)
                        _regime_cfg = _trading_cfg.get("regime", {})
                    except Exception:
                        _regime_cfg = {}

                    _default_multipliers = {0: 1.0, 1: 0.6, 2: 0.4}
                    _regime_key_map = {0: "bullish", 1: "high_volatility", 2: "bear"}
                    _regime_key = _regime_key_map.get(int(current_regime), "bullish")
                    _multiplier = (
                        _regime_cfg.get(_regime_key, {}).get("position_size_multiplier")
                        or _default_multipliers.get(int(current_regime), 1.0)
                    )
                    self._regime_position_multiplier = float(_multiplier)

                    if self._regime_position_multiplier < 1.0:
                        logger.warning(
                            f"레짐 조정: {_regime_key} → 포지션 크기 {self._regime_position_multiplier*100:.0f}%로 축소"
                        )
                    else:
                        logger.info(f"레짐 조정: {_regime_key} → 포지션 크기 변경 없음 (x{self._regime_position_multiplier})")
                else:
                    logger.warning("레짐 분석을 위한 데이터가 부족합니다.")
            except Exception as e:
                logger.error(f"시장 레짐 분석 실패: {e}")

        # 1. 계좌 및 보유 종목 조회
        logger.info("1. 계좌 잔고 및 보유 종목 조회 중...")
        # 미국 주식은 NASD 등 거래소 코드 필요하지만, 잔고 조회는 통상 대표 거래소나 전체 조회가 됨.
        # API Client에서 Default로 처리됨.
        account = self.api_client.get_account_balance()
        logger.info(f"현재 보유 종목: {[p.symbol for p in account.positions]}")
        
        # 2. 종목 선정 및 점수 계산
        logger.info("2. 유니버스 분석 및 우량 종목 선정 중...")
        self._ensure_selector_data()
        if getattr(self, '_use_ml', False) and hasattr(self, '_ml_strategy'):
            logger.info(f"ML 전략 실행 중: {self._ml_strategy.name}")
            all_results = self.selector.calculate_metrics()

            # ML 모델이 학습된 상태이면 predict로 필터링
            ml_filtered = False
            if not all_results.empty:
                try:
                    ml_strategy = self._ml_strategy
                    predictions = self._predict_ml_candidate_signals(ml_strategy, all_results)
                    if predictions is not None and len(predictions) == len(all_results):
                        all_results = all_results.copy()
                        all_results["ml_signal"] = predictions
                        # Keep BUY(1) and HOLD(0) candidates, and drop SELL(-1).
                        all_results = all_results[all_results["ml_signal"] >= 0]
                        logger.info(f"ML 필터 적용: {len(all_results)}개 종목 통과")
                        ml_filtered = True
                    else:
                        logger.info("ML 모델 미학습 상태 - 기본 Selector 결과 사용")
                except Exception as e:
                    logger.warning(f"ML 전략 적용 실패, 기본 Selector 결과 사용: {e}")

            if not ml_filtered:
                logger.info("ML 필터 미적용 - 기본 Selector 결과 사용")
        else:
            all_results = self.selector.calculate_metrics()

        all_results = self._apply_automl_candidate_adjustment(all_results)
        all_results = self._apply_smart_money_candidate_filter(all_results)
        
        current_scores = {}
        if not all_results.empty:
            for _, row in all_results.iterrows():
                current_scores[row['ticker']] = row['score']
        
        top_stocks = []
        if not all_results.empty:
            top_n_df = all_results.sort_values(by='score', ascending=False).head(self.max_stocks)
            top_stocks = top_n_df.to_dict('records')
            
        target_tickers = [item['ticker'] for item in top_stocks]
        self.last_target_tickers = list(target_tickers)
        self.last_top_stocks = list(top_stocks)
        logger.info(f"선정된 목표 종목 (Top {self.max_stocks}): {target_tickers}")
        
        # 3. 출구 전략
        sold_tickers = self._process_exit_strategies(account, current_scores)
        
        # 4. 리밸런싱
        self._rebalance_portfolio(account, top_stocks, sold_tickers)
        
        # 5. 대시보드 상태 업데이트
        self.export_dashboard_state()
        
        logger.info("=== 일일 루틴 완료 ===")

    def _process_exit_strategies(self, account, current_scores: Dict[str, float]) -> List[str]:
        """출구 전략 실행 (모듈화된 Exit 전략 사용)"""
        sold_tickers = []
        logger.info("--- 출구 전략(Exit Strategies) 처리 중 ---")
        
        for position in account.positions:
            symbol = position.symbol
            if position.quantity <= 0:
                continue

                
            current_price = position.current_price
            avg_price = position.avg_price
            exchange = getattr(position, 'exchange', 'NASD')
            
            # Exit 전략 모듈 사용 (사용 가능한 경우)
            if EXIT_MODULE_AVAILABLE and self.exit_strategy is not None:
                # PositionContext 생성
                entry_date = self._entry_dates.get(symbol)
                holding_days = (datetime.now() - entry_date).days if entry_date else 0
                
                # 현재 점수 (MinScoreExit용)
                current_score = current_scores.get(symbol, 5.0)
                
                context = PositionContext(
                    symbol=symbol,
                    quantity=position.quantity,
                    avg_price=avg_price,
                    current_price=current_price,
                    high_water_mark=self.state_manager.get_high_water_mark(symbol) or current_price,
                    atr=0.0,  # 실시간 ATR은 별도 계산 필요
                    holding_days=holding_days,
                    entry_date=entry_date,
                    current_score=current_score
                )
                
                # 고점 업데이트
                self.state_manager.update_high_water_mark(symbol, current_price)
                
                # Exit 신호 체크
                signal = self.exit_strategy.check_exit(context, None)
                
                should_warn_smart_money = True
                if signal.should_exit:
                    exit_qty = int(position.quantity * signal.exit_ratio)
                    if exit_qty > 0:
                        logger.warning(f"🚨 {signal.reason} - {symbol}: {exit_qty}주 매도 (비율: {signal.exit_ratio*100:.0f}%)")
                        self._place_order(symbol, exit_qty, OrderSide.SELL, current_price, exchange)
                        should_warn_smart_money = False
                        
                        # 전량 매도인 경우 상태 정리
                        if signal.exit_ratio >= 1.0:
                            sold_tickers.append(symbol)
                            self.state_manager.clear_high_water_mark(symbol)
                            self._entry_dates.pop(symbol, None)
                if should_warn_smart_money:
                    self._warn_smart_money_holding_signal(position)
                continue
            
            # Fallback: 기존 하드코딩 로직 (Exit 모듈 미사용 시)
            if avg_price > 0:
                loss_pct = (current_price - avg_price) / avg_price
                profit_pct = loss_pct
            else:
                loss_pct = 0
                profit_pct = 0
            
            # 1. Stop Loss (-10%)
            if loss_pct < -0.10:
                logger.warning(f"🛑 손절매(STOP LOSS) 발동 {symbol}: 손실률 {loss_pct*100:.2f}%")
                self._place_order(symbol, position.quantity, OrderSide.SELL, current_price, exchange)
                sold_tickers.append(symbol)
                self.state_manager.clear_high_water_mark(symbol)
                continue

            # 2. Trailing Stop
            self.state_manager.update_high_water_mark(symbol, current_price)
            hwm = self.state_manager.get_high_water_mark(symbol)
            
            if profit_pct > 0.10:
                drop_from_hwm = (current_price - hwm) / hwm
                if drop_from_hwm < -0.05:
                    logger.warning(f"📉 트레일링 스탑(TRAILING STOP) 발동 {symbol}: 현재 수익 {profit_pct*100:.2f}%, 고점 대비 하락 {drop_from_hwm*100:.2f}%")
                    self._place_order(symbol, position.quantity, OrderSide.SELL, current_price, exchange)
                    sold_tickers.append(symbol)
                    self.state_manager.clear_high_water_mark(symbol)
                    continue

            # 3. Min Score
            score = current_scores.get(symbol)
            if score is not None and score < 1.0:
                logger.warning(f"📉 자격 미달(MIN SCORE) 발동 {symbol}: 점수 {score:.4f} < 1.0")
                self._place_order(symbol, position.quantity, OrderSide.SELL, current_price, exchange)
                sold_tickers.append(symbol)
                self.state_manager.clear_high_water_mark(symbol)
                continue

            self._warn_smart_money_holding_signal(position)
                
        return sold_tickers

    def _rebalance_portfolio(self, account, top_stocks: List[Dict], sold_tickers: List[str]) -> None:
        """포트폴리오 리밸런싱"""

        logger.info("--- 포트폴리오 리밸런싱 진행 중 ---")
        
        target_tickers = set(item['ticker'] for item in top_stocks)
        current_positions = {p.symbol: p for p in account.positions}
        
        total_equity = account.total_value 
        target_amount_per_stock = total_equity / self.max_stocks
        
        # 1. 매도
        for symbol, position in current_positions.items():
            if symbol in sold_tickers:
                continue 
            if symbol not in target_tickers:
                logger.info(f"🔄 리밸런싱 매도 (Rebalancing SELL): {symbol}")
                self._place_order(symbol, position.quantity, OrderSide.SELL, position.current_price, position.exchange)
                self.state_manager.clear_high_water_mark(symbol)
                
        if not self.dry_run:
            time.sleep(1) 
            
        # 2. 매수
        for stock in top_stocks:
            symbol = stock['ticker']
            exchange = stock.get('exchange', 'KR' if self.market == 'KR' else 'NASD')
            
            if stock['score'] < 1.0:
                continue
                
            current_price = stock['current_price']
            current_qty = 0
            if symbol in current_positions:
                current_qty = current_positions[symbol].quantity
            
            if current_price <= 0:
                continue

            # 레짐 배율 적용 (bear/high_volatility 시 포지션 축소)
            regime_multiplier = getattr(self, '_regime_position_multiplier', 1.0)
            target_qty = int((target_amount_per_stock * regime_multiplier) // current_price)
            buy_qty = target_qty - current_qty
            
            if buy_qty > 0:
                self._place_order(symbol, buy_qty, OrderSide.BUY, current_price, exchange)
                self.state_manager.update_high_water_mark(symbol, current_price)

    def _place_order(self, symbol: str, quantity: int, side: OrderSide, current_price: float, exchange: str = "NASD", reason: str = "") -> None:
        """주문 실행 래퍼"""

        if quantity <= 0:
            return
            
        logger.info(f"[{'모의투자' if self.dry_run else '실전'}] {side.name} {symbol} ({exchange}): {quantity}주 @ {current_price:,.2f}")
        
        order_success = False

        # 감사 로그: 주문 시도
        if self.audit_logger and AUDIT_LOG_AVAILABLE:
            try:
                event = AuditEvent(
                    event_type=EventType.ORDER,
                    user="system",  # 추후 실제 사용자 ID로 교체
                    action=side.name,
                    details={
                        "symbol": symbol,
                        "quantity": quantity,
                        "price": current_price,
                        "exchange": exchange,
                        "reason": reason or "리밸런싱",
                        "market": self.market,
                        "dry_run": self.dry_run
                    }
                )
                self.audit_logger.log(event)
            except Exception as e:
                logger.debug(f"감사 로그 기록 실패: {e}")
        
        if not self.dry_run:
            try:
                # 시장가 주문 (미국은 지정가로 현재가 주문)
                order = Order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET, # 내부적으로 처리됨
                    price=current_price if self.market == "US" else 0, # 미국은 현재가로 주문
                    quantity=quantity,
                    created_at=datetime.now()
                )
                if self.broker is not None:
                    ord_no = self.broker.place_order(order, exchange=exchange)
                else:
                    ord_no = self.api_client.place_order(order, exchange=exchange)
                logger.info(f"주문 완료. 주문 번호: {ord_no}")
                order_success = True
            except Exception as e:
                logger.error(f"주문 실패: {e}")
                # 오류 알림
                if self.notifier:
                    self.notifier.send_error_alert("주문 실패", f"{symbol}: {e}")
                
                # 감사 로그: 주문 실패
                if self.audit_logger and AUDIT_LOG_AVAILABLE:
                    try:
                        error_event = AuditEvent(
                            event_type=EventType.ERROR,
                            user="system",
                            action="ORDER_FAILED",
                            details={
                                "symbol": symbol,
                                "error": str(e)
                            }
                        )
                        self.audit_logger.log(error_event)
                    except:
                        pass
        else:
            order_success = True  # 모의투자는 항상 성공
        
        # 텔레그램 거래 알림 전송
        if order_success and self.notifier and TELEGRAM_AVAILABLE:
            try:
                trade = TradeAlert(
                    symbol=symbol,
                    action=side.name,
                    quantity=quantity,
                    price=current_price,
                    reason=reason or ("리밸런싱" if not reason else reason)
                )
                self.notifier.send_trade_alert(trade)
            except Exception as e:
                logger.debug(f"텔레그램 알림 전송 실패: {e}")
        
        # 디스코드/통합 알림 전송
        if order_success:
            message = f"[{'모의' if self.dry_run else '실전'}] {side.name} {symbol} {quantity}주 @ {current_price:,.2f}"
            if reason:
                message += f" ({reason})"
            send_notification(message)

        
        # DB에 거래 기록 저장
        if order_success and self.db and DATABASE_AVAILABLE:
            try:
                trade_record = TradeRecord(
                    timestamp=datetime.now().isoformat(),
                    symbol=symbol,
                    side=side.name,
                    quantity=quantity,
                    price=current_price,
                    amount=quantity * current_price,
                    reason=reason or "리밸런싱",
                    market=self.market
                )
                self.db.insert_trade(trade_record)
                logger.debug(f"거래 기록 DB 저장 완료: {symbol}")
            except Exception as e:
                logger.debug(f"DB 저장 실패: {e}")



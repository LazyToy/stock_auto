# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Korean Investment Securities (한국투자증권) REST API-based automated stock trading system with backtesting, ML/RL strategies, and multi-portfolio management. Supports KR and US markets.

## Commands

### Setup
```bash
# Install with dev dependencies (from pyproject.toml)
pip install -e ".[dev]"

# ML/RL optional dependencies (not in pyproject.toml)
pip install scikit-learn torch stable-baselines3 gymnasium

# Copy and configure API credentials
cp .env.example .env
```

### Running Tests
```bash
pytest tests/ -v                          # Full test suite with coverage
pytest tests/unit/ -v                     # Unit tests only
pytest tests/integration/ -v             # Integration tests only
pytest tests/test_backtest.py -v         # Single test file
pytest tests/ -k "test_ml_strategy" -v  # Single test by name
python run_tests.py                      # ML & RL focused test runner
```

### Code Quality
```bash
black src/ tests/ --line-length 100      # Format code
flake8 src/ tests/                       # Lint
isort src/ tests/                        # Sort imports
mypy src/                                # Type check
```

### Running the System
```bash
# Trading modes
python scripts/run_trading.py --mode single --strategy momentum --market KR
python scripts/run_trading.py --mode enhanced --strategy momentum --ai-filter ml_rf
python scripts/run_trading.py --mode multi --capital 2000000

# Backtesting
python scripts/run_backtest.py

# Dashboard
streamlit run dashboard/app.py
```

## Architecture

### Layer Structure

```
scripts/run_trading.py          ← Unified entry point (single/enhanced/multi modes)
    │
    ├── portfolio/manager.py    ← MultiPortfolioManager orchestrates strategies
    ├── trader/auto_trader.py   ← AutoTrader executes trades
    │
    ├── strategies/             ← 20+ signal generators (MA, RSI, ML, RL)
    │   └── base.py             ← BaseStrategy abstract class (all strategies inherit this)
    │
    ├── data/api_client.py      ← KIS REST API with rate limiting
    ├── data/websocket_client.py← Real-time quotes
    │
    ├── live/engine.py          ← LiveTradingEngine with market-hours checks
    ├── live/risk_manager.py    ← Position sizing & exposure limits
    │
    ├── backtest/engine.py      ← Portfolio simulation with commissions & slippage
    │
    └── analysis/               ← Supplementary signals (sentiment, regime, DART, orderflow)
```

### Key Abstractions

- **`BaseStrategy`** (`src/strategies/base.py`) — All strategies implement `generate_signal(prices) → Signal`
- **`BaseBroker`** (`src/broker/base.py`) — Broker interface; `KISBroker` is the only full implementation
- **`MultiPortfolioManager`** (`src/portfolio/manager.py`) — Runs N strategies concurrently with independent capital allocation
- **`TradingStateMachine`** (`src/trader/self_healing.py`) — Saga-pattern state machine for recovery on API failures
- **`BacktestEngine`** (`src/backtest/engine.py`) — Drives portfolio simulation; the `Portfolio` class tracks positions

### Configuration

Three config files control behavior at runtime:
- `config/universe.json` — Stock watchlist (KR & US tickers)
- `config/strategies.yaml` — Per-strategy parameters (periods, thresholds)
- `config/trading.yaml` — Risk rules (max position size, daily loss limit, circuit breaker)
- `.env` — API credentials and `TRADING_MODE=mock|real`

`src/config.py` reads `.env` and is the single source of runtime config. YAML files are loaded via `src/utils/config_loader.py`.

### ML/RL Strategies (`src/strategies/ml_strategy.py`, `src/ml/rl_strategy.py`)

- Classical ML: RandomForest, GradientBoosting, LSTM, Ensemble (scikit-learn + PyTorch)
- RL agents: DQN and PPO with a custom `TradingEnvironment` (Gym-compatible)
- Models saved/versioned via `src/ml/registry.py`; training tracked in MLflow (`src/mlops/mlflow_manager.py`)
- Hyperparameter tuning: GridSearch + Walk-Forward validation in `src/ml/tuning.py`

### Data Flow

1. `KISAPIClient` fetches OHLCV → passed to strategies as `StockPrice` dataclass
2. Strategy returns `Signal` (BUY/SELL/HOLD with confidence)
3. `RiskManager` sizes positions; `OrderManager` submits to KIS
4. `TradingStateMachine` persists state; `AuditLog` + SQLite record every action
5. Notifications dispatched via `src/utils/notification.py` (Telegram/Kakao)

### Testing Patterns

Tests use `conftest.py` fixtures for mock price data and a mock broker. `TRADING_MODE=mock` makes the KIS client return synthetic data without hitting the real API. E2E tests in `tests/e2e/` run full pipeline in mock mode.

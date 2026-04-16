## Readiness Status

This document is the concise current-status summary for the repo as of 2026-03-27.
It is intended as the practical status reference at the repo root.

### Current Bottom Line

- Mock broker: usable
- ML backtest: usable
- Real broker: still conservative/guarded

### What "usable" means right now

#### Mock broker

- `scripts/run_trading.py` defaults to mock broker + dry-run.
- Mock order submission is supported through the guarded mock-order path.
- Current tests cover the mock broker order flow and ML strategy entrypoints.

Practical stance: safe default for runtime validation and integration checks.

#### ML backtest

- `scripts/run_backtest.py` supports ML strategies (`ml_rf`, `ml_gb`, `ensemble`).
- Walk-forward mode is available and prints a symbol-level evaluation summary.
- Current tests cover ML backtest entrypoints and walk-forward reporting behavior.

Practical stance: usable for research, comparison, and offline validation.

#### Real broker

- Real broker execution is not the default path.
- Real broker usage is explicitly guarded by confirmation flags.
- The implementation remains intentionally conservative around live order submission.

Practical stance: keep treating real-broker operation as guarded/controlled, not casual day-to-day default usage.

### Operator Guidance

- Use mock broker for runtime checks and order-flow validation.
- Use ML backtest for model/strategy evaluation.
- Treat real broker flows as opt-in and high-scrutiny.


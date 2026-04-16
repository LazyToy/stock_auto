# Real Readiness Audit Update

> Date: 2026-03-27
> Base document: `REAL_READINESS_AUDIT_2026-03-26.md`
> Purpose: align operations wording with the execution-mode semantics now implemented in code

---

## 1. Terminology Update

From this point, the project should distinguish two axes:

- `broker=mock | real`
- `orders=dry-run | mock | real`

This matters because "mock account" and "dry-run" are not the same thing.

---

## 2. Current Runtime Meaning

As of 2026-03-27, shipped runtime paths now print execution mode explicitly.

- `run_trading.py`
  - default: `broker=mock, orders=dry-run`
  - `--mock-order --confirm-order-submission`: `broker=mock, orders=mock`
  - `--live --confirm-order-submission`: legacy alias for `--mock-order`
  - `--real-broker --confirm-order-submission --confirm-real-broker`: `broker=real, orders=real`
- `run_scheduler.py`
  - monitoring path: `broker=mock, orders=dry-run`
- `scripts/experiments/run_auto_trading.py`
  - `broker=mock, orders=dry-run`
- `scripts/experiments/run_us_trading.py`
  - `broker=mock, orders=dry-run`
- `scripts/experiments/run_us_growth.py`
  - `broker=mock, orders=dry-run`
- `scripts/experiments/run_live.py`
  - default: `broker=mock, orders=dry-run`
  - `--mock-order --confirm-order-submission`: `broker=mock, orders=mock`
  - `--live --confirm-order-submission`: legacy alias for `--mock-order`
  - `--real-broker --confirm-order-submission --confirm-real-broker`: `broker=real, orders=real`
  - `--mode mock|real`: legacy alias layer over the same execution model

Important clarification:

- `run_trading.py --live` does not mean "real broker live trading".
- It currently means "submit orders through the mock broker path".

---

## 3. Readiness Interpretation

The readiness conclusions in `REAL_READINESS_AUDIT_2026-03-26.md` still stand.

- reliable traditional backtesting: partially usable
- ML backtesting: not ready
- dry-run simulation: partially usable
- mock broker order flow: still incomplete
- live real-broker trading: not ready

What changed is wording clarity, not readiness status.

Additional implementation note as of 2026-03-27:

- ML walk-forward backtest output now includes symbol/period context and runtime evaluation fields such as trained predictions, coverage, accuracy, and retrain count.
- Runtime ML trading now attempts to load the latest saved model for the selected market/strategy and falls back safely if loading fails.
- `run_trading.py --compare-ml` is available as a mock/runtime comparison helper for `ml_rf`, `ml_gb`, and `ensemble`.

---

## 4. Operational Guidance

When reading logs or running scripts, interpret modes like this:

- `broker=mock, orders=dry-run`
  - no order submission
  - strategy and rebalance logic only
- `broker=mock, orders=mock`
  - requires `--confirm-order-submission`
  - order submission is attempted on the mock broker path
  - this is closer to "mock-order" than "paper simulation"
- `broker=real, orders=real`
  - requires `--real-broker --confirm-order-submission --confirm-real-broker`
  - not the default shipped path
  - should not be assumed ready from current code alone
  - `scripts/experiments/run_live.py` still accepts the older `--mode real` alias, but it is now mapped into the same confirmation model

---

## 5. CLI Safety State

The CLI now exposes separate operator flags:

- `--dry-run`
- `--mock-order`
- `--confirm-order-submission`
- `--real-broker`
- `--confirm-real-broker`

This is a safety improvement, not a readiness change.

- `--mock-order` is blocked unless `--confirm-order-submission` is also provided.
- `--real-broker` is blocked unless both `--confirm-order-submission` and `--confirm-real-broker` are provided.
- `--live` is still accepted only as a backward-compatible alias for `--mock-order`.
- `scripts/experiments/run_live.py --mode real` is blocked unless `--confirm-real-broker` is also provided.
- `scripts/experiments/run_live.py` now uses the same `broker/orders` model as `run_trading.py`, with `--mode mock|real` kept only as a legacy alias.

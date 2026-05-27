# OHLCV File Fixtures

This directory is reserved for reusable OHLCV file fixtures used by later Smart
Money MTF PRs.

PR-01 keeps the fixture data in `tests/fixtures/ohlcv_factory.py` so boundary
conditions can be generated deterministically without committing sample CSV
files before the downstream detector contracts are fixed.

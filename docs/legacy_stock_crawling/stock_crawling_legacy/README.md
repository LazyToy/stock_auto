# stock_crawling legacy notes

This directory now contains legacy source material from the old crawling project.
The active implementation has been migrated into the root `stock_auto` package
under `src/crawling/`.

## Current runner

Run crawling from the root project:

```powershell
python -m src.crawling.run_daily --dry-run
python -m src.crawling.run_daily --mode all
python -m src.crawling.run_daily --mode kr
python -m src.crawling.run_daily --mode us
python -m src.crawling.run_daily --mode snapshots
python -m src.crawling.run_daily --mode backfill
python -m src.crawling.run_daily --mode backtest
```

The Streamlit dashboard uses the same `src.crawling.run_daily` entrypoint.
Google Sheets result lookup is implemented in Python by
`src/crawling/sheets_reader.py`.

## Phase 6 cleanup

The old Node, React, and TypeScript runner surface has been removed.
Historical planning/result notes were moved to `docs/legacy_stock_crawling/`.

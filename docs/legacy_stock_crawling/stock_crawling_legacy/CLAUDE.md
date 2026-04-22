# CLAUDE.md

This directory is legacy source material from the old stock_crawling project.
The merged stock_auto project now runs crawling through the root Python package.

## Current runner

Use the root project environment and invoke:

```powershell
python -m src.crawling.run_daily --dry-run
python -m src.crawling.run_daily --mode all
python -m src.crawling.run_daily --mode kr
python -m src.crawling.run_daily --mode us
```

The active implementation lives under `src/crawling/`.
The Streamlit execution UI builds the same `src.crawling.run_daily` command.
Google Sheets results are read by Python code in `src/crawling/sheets_reader.py`.

## Phase 6 state

The old Node, React, and TypeScript runner surface has been removed from this
directory. Do not add new runner wrappers here; add Python package entrypoints
or tests under the root project instead.

# StockCrawling schedule guide

The scheduled tasks now call the root Python package runner:

```powershell
python -m src.crawling.run_daily --mode kr
python -m src.crawling.run_daily --mode us
```

## Tasks

| Task | Time | Mode |
| --- | --- | --- |
| StockCrawling_KR_Daily | 15:40 KST | `kr` |
| StockCrawling_US_Daily | 06:10 KST | `us` |

## Install

Run from `stock_crawling/scripts` in an administrator PowerShell:

```powershell
.\install_schedule.ps1
.\install_schedule.ps1 -Force
```

## Verify

```powershell
.\verify_schedule.ps1
```

## Logs

```powershell
$today = Get-Date -Format "yyyyMMdd"
Get-Content "..\..\logs\crawling\run_daily_kr_$today.log" -Tail 50
Get-Content "..\..\logs\crawling\run_daily_us_$today.log" -Tail 50
```

## Manual run

Run from the root project:

```powershell
python -m src.crawling.run_daily --mode kr
python -m src.crawling.run_daily --mode us
```

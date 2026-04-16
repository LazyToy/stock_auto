"""Stock selection helpers used by AutoTrader."""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - optional dependency fallback
    yf = None

logger = logging.getLogger(__name__)


def _require_yfinance() -> None:
    if yf is None:
        raise RuntimeError("yfinance is required for StockSelector")


class StockSelector:
    def __init__(
        self,
        tickers: List[str],
        period: str = "6mo",
        benchmark: str = "^KS11",
        style: str = "VALUE",
    ):
        self.tickers = tickers
        self.period = period
        self.benchmark = benchmark
        self.style = style.upper()
        self.data: Dict[str, pd.DataFrame] = {}
        self.market_data: Optional[pd.DataFrame] = None

    def download_data(self):
        _require_yfinance()
        self.data = {}
        self.market_data = None

        market = yf.download(
            self.benchmark,
            period=self.period,
            progress=False,
            auto_adjust=False,
        )
        if len(market) > 0:
            self.market_data = self._preprocess_dataframe(market)

        for ticker in self.tickers:
            try:
                df = yf.download(
                    ticker,
                    period=self.period,
                    progress=False,
                    auto_adjust=False,
                )
                if len(df) > 0:
                    self.data[ticker] = self._preprocess_dataframe(df)
            except Exception as exc:
                logger.warning("Ticker download failed for %s: %s", ticker, exc)
            time.sleep(0.01)

    def _preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame.columns = [str(column).lower() for column in frame.columns]
        if "adj close" in frame.columns and "close" not in frame.columns:
            frame.rename(columns={"adj close": "close"}, inplace=True)
        return frame

    def get_fundamentals(self, ticker: str) -> Dict:
        _require_yfinance()
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}

            yf_exchange = info.get("exchange", "")
            if yf_exchange in {"NMS", "NGM", "NCM", "KDQ"}:
                exchange = "NASD"
            elif yf_exchange in {"NYQ", "NYS", "KSC"}:
                exchange = "NYSE"
            else:
                exchange = "AMEX"

            pe = info.get("forwardPE") or info.get("trailingPE")
            pb = info.get("priceToBook")
            roe = info.get("returnOnEquity")
            psr = info.get("priceToSalesTrailing12Months")
            market_cap = info.get("marketCap")
            debt_to_equity = info.get("debtToEquity")
            revenue_growth = info.get("revenueGrowth")
            gross_profits = info.get("grossProfits")
            total_assets = info.get("totalAssets")

            if gross_profits is None:
                financials = getattr(stock, "financials", None)
                if financials is not None and "Gross Profit" in financials.index:
                    gross_profits = financials.loc["Gross Profit"].iloc[0]

            if total_assets is None:
                balance_sheet = getattr(stock, "balance_sheet", None)
                if balance_sheet is not None and "Total Assets" in balance_sheet.index:
                    total_assets = balance_sheet.loc["Total Assets"].iloc[0]

            gpa = None
            if gross_profits and total_assets and total_assets > 0:
                gpa = gross_profits / total_assets

            return {
                "pe": pe,
                "pb": pb,
                "roe": roe,
                "psr": psr,
                "market_cap": market_cap,
                "debt_to_equity": debt_to_equity,
                "revenue_growth": revenue_growth,
                "gpa": gpa,
                "exchange": exchange,
            }
        except Exception:
            return {
                "pe": None,
                "pb": None,
                "roe": None,
                "psr": None,
                "market_cap": None,
                "debt_to_equity": None,
                "revenue_growth": None,
                "gpa": None,
                "exchange": "NASD",
            }

    def _calculate_value_score(self, momentum, volatility, volume_ratio, fund) -> float:
        raw_score = momentum / volatility if volatility > 0 else 0.0
        volume_multiplier = min(1.2, max(0.8, volume_ratio))

        factor_multiplier = 1.0
        if fund["pe"] and 0 < fund["pe"] < 20:
            factor_multiplier += 0.1
        if fund["roe"] and fund["roe"] > 0.1:
            factor_multiplier += 0.1
        if fund["gpa"] and fund["gpa"] > 0.15:
            factor_multiplier += 0.1
        if fund["revenue_growth"] and fund["revenue_growth"] > 0.1:
            factor_multiplier += 0.1
        if fund["debt_to_equity"] and fund["debt_to_equity"] > 200:
            factor_multiplier -= 0.2
        if (fund["pe"] and fund["pe"] < 0) or (fund["roe"] and fund["roe"] < 0):
            factor_multiplier -= 0.2

        return raw_score * volume_multiplier * factor_multiplier

    def _calculate_growth_score(self, momentum, volatility, volume_ratio, fund) -> float:
        adjusted_volatility = max(0.1, volatility * 0.3)
        raw_score = (momentum * 2.0) / adjusted_volatility
        volume_multiplier = min(1.5, max(0.8, volume_ratio))

        factor_multiplier = 1.0
        revenue_growth = fund.get("revenue_growth")
        if revenue_growth is not None:
            if revenue_growth > 0.50:
                factor_multiplier += 1.0
            elif revenue_growth > 0.30:
                factor_multiplier += 0.5
            elif revenue_growth > 0.15:
                factor_multiplier += 0.2
            elif revenue_growth < 0.05:
                factor_multiplier -= 0.5
            elif revenue_growth < 0:
                factor_multiplier -= 0.8

        psr = fund.get("psr")
        if psr is not None:
            if psr < 3:
                factor_multiplier += 0.2
            elif psr > 30:
                factor_multiplier -= 0.3

        market_cap = fund.get("market_cap")
        if market_cap is not None and market_cap < 50_000_000_000 and revenue_growth and revenue_growth > 0.2:
            factor_multiplier += 0.3

        return raw_score * volume_multiplier * factor_multiplier

    def calculate_metrics(self) -> pd.DataFrame:
        results = []

        market_return = 0.0
        if self.market_data is not None and "close" in self.market_data.columns and len(self.market_data) > 1:
            market_close = self.market_data["close"].astype(float).to_numpy()
            if market_close[0] != 0:
                market_return = (market_close[-1] - market_close[0]) / market_close[0]

        for ticker, df in self.data.items():
            if len(df) < 20 or "close" not in df.columns or "volume" not in df.columns:
                continue

            try:
                close_prices = df["close"].astype(float).to_numpy()
                start_price = float(close_prices[0])
                end_price = float(close_prices[-1])
                if start_price <= 0:
                    continue

                momentum = (end_price - start_price) / start_price
                volatility = float(df["close"].pct_change().std())
                volume_ma_short = float(df["volume"].tail(20).mean())
                volume_ma_long = float(df["volume"].tail(60).mean()) if len(df) >= 60 else volume_ma_short
                volume_ratio = volume_ma_short / volume_ma_long if volume_ma_long > 0 else 1.0
                relative_strength = momentum - market_return
                fundamentals = self.get_fundamentals(ticker)

                if self.style == "GROWTH":
                    score = self._calculate_growth_score(
                        momentum, volatility, volume_ratio, fundamentals
                    )
                else:
                    score = self._calculate_value_score(
                        momentum, volatility, volume_ratio, fundamentals
                    )

                results.append(
                    {
                        "ticker": ticker,
                        "score": score,
                        "momentum": momentum,
                        "volatility": volatility,
                        "volume_ratio": volume_ratio,
                        "relative_strength": relative_strength,
                        "exchange": fundamentals.get("exchange", "KR"),
                        "current_price": end_price,
                        "pe": fundamentals.get("pe"),
                        "pb": fundamentals.get("pb"),
                        "roe": fundamentals.get("roe"),
                        "psr": fundamentals.get("psr"),
                        "gpa": fundamentals.get("gpa"),
                        "revenue_growth": fundamentals.get("revenue_growth"),
                        "debt_to_equity": fundamentals.get("debt_to_equity"),
                    }
                )
            except Exception as exc:
                logger.warning("Metric calculation failed for %s: %s", ticker, exc)

        if not results:
            return pd.DataFrame(columns=["ticker", "score", "exchange", "current_price"])

        result_df = pd.DataFrame(results)
        return result_df.sort_values("score", ascending=False).reset_index(drop=True)

    def select_top_n(self, n: int = 5) -> List[Dict]:
        if not self.data:
            self.download_data()
        metrics = self.calculate_metrics()
        if metrics.empty:
            return []
        return metrics.head(n).to_dict("records")

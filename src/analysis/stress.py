import pandas as pd
import numpy as np
import os
from typing import Dict, List, Any, Optional
import logging
from src.analysis.market_data import MarketDataFetcher

logger = logging.getLogger("StressTester")

class Scenario:
    def __init__(self, name: str, start_date: str, end_date: str, description: str):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.description = description

class StressTester:
    """
    포트폴리오 스트레스 테스트 시뮬레이터
    """
    SCENARIOS = {
        "2008_Financial_Crisis": Scenario("2008 Financial Crisis", "2008-09-01", "2008-11-30", "Lehman Brothers Bankruptcy"),
        "2020_Covid_Crash": Scenario("2020 Covid Crash", "2020-02-19", "2020-03-23", "Pandemic onset"),
        "2022_Inflation_Shock": Scenario("2022 Inflation Shock", "2022-01-01", "2022-10-14", "Aggressive Rate Hikes")
    }
    SCENARIO_PROXY_RETURNS = {
        "2008_Financial_Crisis": -0.30,
        "2020_Covid_Crash": -0.34,
        "2022_Inflation_Shock": -0.25,
    }

    def __init__(self):
        self.market_fetcher = MarketDataFetcher()
        self._configure_yfinance_cache()

    def _configure_yfinance_cache(self):
        """yfinance 캐시 경로를 작업 디렉터리 안으로 고정한다."""
        try:
            import yfinance as yf

            cache_dir = os.path.join(os.getcwd(), ".yf-cache")
            os.makedirs(cache_dir, exist_ok=True)
            if hasattr(yf, "set_tz_cache_location"):
                yf.set_tz_cache_location(cache_dir)
        except Exception as exc:
            logger.warning(f"yfinance 캐시 경로 설정 실패: {exc}")

    def _extract_close_series(self, data: pd.DataFrame, ticker: str) -> pd.Series:
        """다운로드 결과에서 종가 시리즈를 안전하게 추출한다."""
        if isinstance(data.columns, pd.MultiIndex):
            return data["Close"][ticker].dropna()
        return data["Close"].dropna()

    def _get_proxy_return(self, scenario_name: str) -> float:
        """다운로드 실패 시 사용할 시나리오 프록시 수익률을 반환한다."""
        return self.SCENARIO_PROXY_RETURNS.get(scenario_name, -0.20)

    def calculate_risk_metrics(self, returns: pd.Series) -> Dict[str, float]:
        """
        수익률 시리즈를 기반으로 리스크 지표 계산
        """
        if returns.empty:
            return {}

        metrics = {}
        
        # Empirical VaR (Historical Simulation method)
        metrics['VaR_95'] = np.percentile(returns, 5)
        metrics['VaR_99'] = np.percentile(returns, 1)
        
        # CVaR (Expected Shortfall) - Average of losses exceeding VaR 95
        cvar_mask = returns <= metrics['VaR_95']
        metrics['CVaR_95'] = returns[cvar_mask].mean() if cvar_mask.any() else 0.0
        
        # Max Drawdown
        cum_returns = (1 + returns).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        metrics['Max_Drawdown'] = drawdown.min()
        
        return metrics

    def simulate_scenario(self, portfolio: Dict[str, float], total_value: float, scenario_name: str) -> Dict[str, Any]:
        """
        특정 시나리오에서의 포트폴리오 성과 시뮬레이션
        Args:
            portfolio: {ticker: weight} (e.g. {'AAPL': 0.5, 'MSFT': 0.5})
            total_value: Current portfolio value
            scenario_name: Key in SCENARIOS
        """
        scenario = self.SCENARIOS.get(scenario_name)
        if not scenario:
            return {"error": "Scenario not found"}
            
        # Fetch historical returns for each asset in portfolio
        scenario_returns = {}
        proxy_used = False
        notes = []
        
        for ticker, weight in portfolio.items():
            try:
                import yfinance as yf

                data = yf.download(
                    ticker,
                    start=scenario.start_date,
                    end=scenario.end_date,
                    progress=False,
                    auto_adjust=False,
                    threads=False,
                )

                if not data.empty:
                    close = self._extract_close_series(data, ticker)
                    if len(close) >= 2:
                        ret = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
                        scenario_returns[ticker] = float(ret)
                        continue

                proxy_used = True
                proxy_return = self._get_proxy_return(scenario_name)
                scenario_returns[ticker] = proxy_return
                notes.append(f"{ticker}: 시나리오 프록시 수익률 {proxy_return:.2%} 적용")
                logger.warning(f"{ticker} 데이터 다운로드 실패. 프록시 수익률 적용: {proxy_return:.2%}")
            except Exception as e:
                proxy_used = True
                proxy_return = self._get_proxy_return(scenario_name)
                scenario_returns[ticker] = proxy_return
                notes.append(f"{ticker}: 데이터 다운로드 실패로 프록시 수익률 {proxy_return:.2%} 적용")
                logger.warning(f"{ticker} 데이터 다운로드 예외 발생. 프록시 수익률 적용: {e}")

        result = self._calculate_impact(portfolio, total_value, scenario_returns)
        if proxy_used:
            result["proxy_used"] = True
            result["notes"] = notes
        return result

    def _calculate_impact(self, portfolio: Dict[str, float], total_value: float, asset_returns: Dict[str, float]) -> Dict[str, Any]:
        """
        자산별 수익률을 바탕으로 포트폴리오 충격 계산
        """
        portfolio_return = 0.0
        details = {}
        
        for ticker, weight in portfolio.items():
            ret = asset_returns.get(ticker, 0.0)
            portfolio_return += weight * ret
            details[ticker] = ret
            
        loss_amount = total_value * portfolio_return
        
        return {
            "scenario": "Custom/Simulation",
            "portfolio_return": portfolio_return,
            "total_loss_amount": loss_amount,
            "details": details
        }

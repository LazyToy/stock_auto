import unittest
from unittest import mock
import pandas as pd
import numpy as np
from src.analysis.stress import StressTester, Scenario

class TestStressTester(unittest.TestCase):
    def setUp(self):
        self.tester = StressTester()
        
    def test_calculate_risk_metrics(self):
        """리스크 지표 계산 테스트 (VaR, MaxDD)"""
        # Create dummy returns: Normal distribution
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0, 0.01, 100))
        # Introduce a large loss for MaxDD
        returns.iloc[50] = -0.05
        
        metrics = self.tester.calculate_risk_metrics(returns)
        
        self.assertIn('VaR_95', metrics)
        self.assertIn('VaR_99', metrics)
        self.assertIn('Max_Drawdown', metrics)
        
        # VaR should be negative
        self.assertLess(metrics['VaR_95'], 0)
        
    def test_simulate_scenario_logic(self):
        """시나리오 시뮬레이션 로직 테스트"""
        # Portfolio: 50% Asset A, 50% Asset B
        portfolio = {'A': 0.5, 'B': 0.5}
        total_value = 10000
        
        # Scenario Data (Mock): A dropped 10%, B dropped 20%
        # We need to mock the data fetching part.
        # Let's assume simulate_scenario accepts a custom return map for testing
        
        scenario_returns = {
            'A': -0.10,
            'B': -0.20
        }
        
        # Expected Loss: 0.5 * -10% + 0.5 * -20% = -15%
        # -15% of 10000 = -1500
        
        impact = self.tester._calculate_impact(portfolio, total_value, scenario_returns)
        
        self.assertAlmostEqual(impact['total_loss_amount'], -1500)
        self.assertAlmostEqual(impact['portfolio_return'], -0.15)

    @mock.patch('yfinance.download')
    def test_simulate_scenario_error(self, mock_yf):
        """데이터 다운로드 실패 시 프록시 수익률로 폴백하는지 확인"""
        portfolio = {'A': 1.0}
        total_value = 10000
        mock_yf.side_effect = Exception("Mock DB locked")
        result = self.tester.simulate_scenario(portfolio, total_value, '2008_Financial_Crisis')
        self.assertNotIn("error", result)
        self.assertTrue(result["proxy_used"])
        self.assertAlmostEqual(result["portfolio_return"], -0.30)
        self.assertAlmostEqual(result["total_loss_amount"], -3000)
        self.assertEqual(result["path"][0]["date"], "2008-09-01")
        self.assertEqual(result["path"][-1]["date"], "2008-11-30")

    @mock.patch('yfinance.download')
    def test_simulate_scenario_returns_path_and_risk_metrics(self, mock_yf):
        """시나리오 기간 중간 경로와 최대 낙폭을 함께 반환한다."""
        dates = pd.to_datetime(["2020-02-19", "2020-02-20", "2020-02-21", "2020-02-22"])
        prices = {
            "A": pd.DataFrame({"Close": [100.0, 90.0, 80.0, 95.0]}, index=dates),
            "B": pd.DataFrame({"Close": [100.0, 100.0, 90.0, 100.0]}, index=dates),
        }
        mock_yf.side_effect = lambda ticker, **kwargs: prices[ticker]

        result = self.tester.simulate_scenario({"A": 0.5, "B": 0.5}, 10000, "2020_Covid_Crash")

        self.assertAlmostEqual(result["portfolio_return"], -0.025)
        self.assertIn("path", result)
        self.assertEqual(len(result["path"]), 4)
        self.assertAlmostEqual(result["path"][0]["portfolio_value"], 10000.0)
        self.assertAlmostEqual(result["path"][2]["portfolio_return"], -0.15)
        self.assertIn("asset_price_paths", result)
        self.assertEqual(result["asset_price_paths"][0]["symbol"], "A")
        self.assertEqual(result["asset_price_paths"][0]["date"], "2020-02-19")
        self.assertAlmostEqual(result["asset_price_paths"][0]["close"], 100.0)
        self.assertAlmostEqual(result["asset_price_paths"][2]["return"], -0.20)
        self.assertIn("risk_metrics", result)
        self.assertAlmostEqual(result["risk_metrics"]["Max_Drawdown"], -0.15)
        self.assertNotIn("bootstrap_summary", result)

    @mock.patch('yfinance.download')
    def test_simulate_scenario_enters_at_previous_close_and_reports_high_low(self, mock_yf):
        """시나리오 시작 전 거래일 종가로 진입하고 기간 고가/저가를 반환한다."""
        dates = pd.to_datetime(["2020-02-18", "2020-02-19", "2020-02-20", "2020-03-23"])

        def fake_download(ticker, **kwargs):
            if ticker == "KRW=X":
                return pd.DataFrame({"Close": [1.0, 1.0, 1.0, 1.0]}, index=dates)
            return pd.DataFrame(
                {
                    "Close": [100.0, 120.0, 90.0, 110.0],
                    "High": [101.0, 125.0, 130.0, 115.0],
                    "Low": [99.0, 118.0, 85.0, 80.0],
                },
                index=dates,
            )

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_scenario({"A": 1.0}, 10000, "2020_Covid_Crash")

        self.assertAlmostEqual(result["portfolio_return"], 0.10)
        self.assertEqual(result["path"][0]["date"], "2020-02-18")
        self.assertAlmostEqual(result["path"][0]["portfolio_return"], 0.0)
        self.assertAlmostEqual(result["path"][1]["portfolio_return"], 0.20)
        extreme = result["asset_extremes"]["A"]
        self.assertEqual(extreme["entry_date"], "2020-02-18")
        self.assertAlmostEqual(extreme["entry_close"], 100.0)
        self.assertAlmostEqual(extreme["scenario_high"], 130.0)
        self.assertAlmostEqual(extreme["scenario_low"], 80.0)
        self.assertAlmostEqual(extreme["scenario_high_return"], 0.30)
        self.assertAlmostEqual(extreme["scenario_low_return"], -0.20)
        self.assertAlmostEqual(result["portfolio_extremes"]["highest_return"], 0.20)
        self.assertAlmostEqual(result["portfolio_extremes"]["lowest_return"], -0.10)

    @mock.patch('yfinance.download')
    def test_simulate_scenario_reports_data_quality_for_partial_proxy(self, mock_yf):
        """일부 종목만 프록시를 쓰면 품질 지표와 프록시 비중을 반환한다."""
        dates = pd.to_datetime(["2020-02-19", "2020-03-23"])

        def fake_download(ticker, **kwargs):
            if ticker == "A":
                return pd.DataFrame({"Close": [100.0, 110.0]}, index=dates)
            return pd.DataFrame()

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_scenario({"A": 0.5, "B": 0.5}, 10000, "2020_Covid_Crash")

        self.assertTrue(result["proxy_used"])
        self.assertAlmostEqual(result["portfolio_return"], -0.12)
        self.assertEqual(result["data_quality"]["real_data_count"], 1)
        self.assertEqual(result["data_quality"]["proxy_count"], 1)
        self.assertAlmostEqual(result["data_quality"]["proxy_weight"], 0.5)
        self.assertEqual(result["data_quality"]["level"], "LOW")
        self.assertEqual(result["risk_classification"], "MEDIUM_DATA_LIMITED")

    def test_extract_close_series_supports_ticker_first_multiindex(self):
        """yfinance가 ticker-first MultiIndex를 반환해도 Close를 추출한다."""
        dates = pd.to_datetime(["2020-01-01", "2020-01-02"])
        columns = pd.MultiIndex.from_tuples([
            ("AAPL", "Open"),
            ("AAPL", "Close"),
        ])
        data = pd.DataFrame([[99.0, 100.0], [100.0, 105.0]], index=dates, columns=columns)

        close = self.tester._extract_close_series(data, "AAPL")

        self.assertEqual(close.tolist(), [100.0, 105.0])

    def test_extract_close_series_supports_close_first_single_ticker_fallback(self):
        """요청 ticker가 컬럼에 없어도 단일 Close 컬럼이면 해당 값을 사용한다."""
        dates = pd.to_datetime(["2020-01-01", "2020-01-02"])
        columns = pd.MultiIndex.from_tuples([
            ("Close", "AAPL.US"),
        ])
        data = pd.DataFrame([[100.0], [105.0]], index=dates, columns=columns)

        close = self.tester._extract_close_series(data, "AAPL")

        self.assertEqual(close.tolist(), [100.0, 105.0])

    def test_simulate_hypothetical_shock_uses_portfolio_and_asset_shocks(self):
        """가상 충격은 기본 포트폴리오 충격과 종목별 override를 함께 지원한다."""
        result = self.tester.simulate_hypothetical_shock(
            {"A": 0.7, "B": 0.3},
            10000,
            shock_return=-0.20,
            asset_shocks={"B": -0.50},
            scenario_name="Tech selloff",
        )

        self.assertEqual(result["scenario_type"], "hypothetical")
        self.assertAlmostEqual(result["portfolio_return"], -0.29)
        self.assertAlmostEqual(result["total_loss_amount"], -2900)
        self.assertEqual(result["details"], {"A": -0.20, "B": -0.50})
        self.assertEqual(result["data_quality"]["level"], "SYNTHETIC")
        self.assertEqual(result["data_quality"]["real_data_count"], 0)

    def test_available_scenarios_excludes_synthetic_uniform_shocks(self):
        """시나리오 선택 목록에는 실제 기간 기반 시나리오만 노출한다."""
        scenarios = self.tester.available_scenarios()

        self.assertNotIn("Broad_Equity_Shock_20", scenarios)
        self.assertNotIn("Growth_Rate_Shock", scenarios)
        self.assertTrue(all(scenario.scenario_type == "historical" for scenario in scenarios.values()))

    def test_available_scenarios_includes_rate_and_tariff_shocks(self):
        """장기금리 급등과 Liberation Day 관세 충격 시나리오를 선택할 수 있다."""
        scenarios = self.tester.available_scenarios()

        self.assertIn("2026_May_Long_Rate_Shock", scenarios)
        self.assertEqual(scenarios["2026_May_Long_Rate_Shock"].start_date, "2026-05-15")
        self.assertEqual(scenarios["2026_May_Long_Rate_Shock"].end_date, "2026-05-22")
        self.assertIn("2025_Liberation_Day_Tariff_Shock", scenarios)
        self.assertEqual(scenarios["2025_Liberation_Day_Tariff_Shock"].start_date, "2025-04-03")
        self.assertEqual(scenarios["2025_Liberation_Day_Tariff_Shock"].end_date, "2025-04-08")

    @mock.patch('yfinance.download')
    def test_new_real_event_scenarios_use_historical_price_paths(self, mock_yf):
        """추가 실제 사건 시나리오는 고정 충격이 아니라 기간 가격 경로로 계산한다."""
        dates = pd.to_datetime(["2025-04-02", "2025-04-03", "2025-04-04", "2025-04-08"])

        def fake_download(ticker, **kwargs):
            if ticker == "KRW=X":
                return pd.DataFrame({"Close": [1.0, 1.0, 1.0, 1.0]}, index=dates)
            return pd.DataFrame(
                {
                    "Close": [100.0, 95.0, 90.0, 88.0],
                    "High": [101.0, 96.0, 92.0, 90.0],
                    "Low": [99.0, 93.0, 87.0, 86.0],
                },
                index=dates,
            )

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_named_scenario(
            {"SPY": 1.0},
            10000,
            "2025_Liberation_Day_Tariff_Shock",
        )

        self.assertEqual(result["scenario_type"], "historical")
        self.assertAlmostEqual(result["details"]["SPY"], -0.12)
        self.assertEqual(result["path"][0]["date"], "2025-04-02")
        self.assertIn("asset_price_paths", result)

    @mock.patch('yfinance.download')
    def test_us_holdings_are_converted_to_krw_with_historical_fx(self, mock_yf):
        """해외 주식은 시나리오 당시 USD/KRW 환율을 반영해 원화 수익률을 계산한다."""
        dates = pd.to_datetime(["2020-02-18", "2020-02-19", "2020-03-23"])

        def fake_download(ticker, **kwargs):
            if ticker == "AAPL":
                return pd.DataFrame(
                    {"Close": [100.0, 100.0, 100.0], "High": [100.0, 100.0, 100.0], "Low": [100.0, 100.0, 100.0]},
                    index=dates,
                )
            if ticker == "KRW=X":
                return pd.DataFrame({"Close": [1000.0, 1000.0, 1100.0]}, index=dates)
            return pd.DataFrame()

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_scenario({"AAPL": 1.0}, 10000, "2020_Covid_Crash")

        self.assertAlmostEqual(result["details"]["AAPL"], 0.10)
        self.assertEqual(result["fx_conversion"]["currency"], "KRW")
        self.assertTrue(result["fx_conversion"]["used"])
        self.assertAlmostEqual(result["asset_price_paths"][0]["close_krw"], 100000.0)
        self.assertAlmostEqual(result["asset_price_paths"][-1]["close_krw"], 110000.0)

    @mock.patch('yfinance.download')
    def test_pre_listing_holdings_are_excluded_as_cash(self, mock_yf):
        """시나리오 당시 상장 전 종목은 현금 비중으로 두고 알림 정보에 포함한다."""
        future_dates = pd.to_datetime(["2021-01-04", "2021-01-05"])

        def fake_download(ticker, **kwargs):
            if kwargs.get("period") == "max":
                return pd.DataFrame({"Close": [10.0, 11.0]}, index=future_dates)
            return pd.DataFrame()

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_scenario({"NEW": 0.4, "CASHLIKE": 0.6}, 10000, "2020_Covid_Crash")

        self.assertAlmostEqual(result["details"]["NEW"], 0.0)
        self.assertAlmostEqual(result["details"]["CASHLIKE"], 0.0)
        self.assertAlmostEqual(result["portfolio_return"], 0.0)
        self.assertEqual(result["excluded_assets"][0]["symbol"], "NEW")
        self.assertEqual(result["excluded_assets"][0]["treatment"], "cash")

    @mock.patch('yfinance.Ticker')
    @mock.patch('yfinance.download')
    def test_missing_listed_holding_uses_sector_proxy_etf(self, mock_yf, mock_ticker):
        """데이터가 누락된 상장 종목은 섹터에 맞는 대표 ETF 경로로 대체한다."""
        scenario_dates = pd.to_datetime(["2020-02-18", "2020-02-19", "2020-03-23"])
        old_dates = pd.to_datetime(["2010-01-04", "2010-01-05"])
        mock_ticker.return_value.info = {"sector": "Technology"}

        def fake_download(ticker, **kwargs):
            if ticker == "AAPL" and kwargs.get("period") == "max":
                return pd.DataFrame({"Close": [10.0, 11.0]}, index=old_dates)
            if ticker == "AAPL":
                return pd.DataFrame()
            if ticker == "XLK":
                return pd.DataFrame(
                    {"Close": [100.0, 95.0, 80.0], "High": [100.0, 96.0, 82.0], "Low": [99.0, 94.0, 78.0]},
                    index=scenario_dates,
                )
            if ticker == "KRW=X":
                return pd.DataFrame({"Close": [1000.0, 1000.0, 1000.0]}, index=scenario_dates)
            return pd.DataFrame()

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_scenario({"AAPL": 1.0}, 10000, "2020_Covid_Crash")

        self.assertTrue(result["proxy_used"])
        self.assertAlmostEqual(result["details"]["AAPL"], -0.20)
        self.assertEqual(result["proxy_assets"][0]["proxy_symbol"], "XLK")
        self.assertEqual(result["proxy_assets"][0]["sector"], "Technology")

    @mock.patch('yfinance.download')
    def test_macro_summary_and_benchmarks_are_always_reported(self, mock_yf):
        """매크로 변수와 벤치마크 비교는 데이터 없음 상태라도 결과에 포함한다."""
        dates = pd.to_datetime(["2020-02-18", "2020-02-19", "2020-02-20", "2020-03-23"])

        def fake_download(ticker, **kwargs):
            if ticker == "A":
                return pd.DataFrame(
                    {"Close": [100.0, 90.0, 85.0, 80.0], "High": [100.0, 91.0, 86.0, 81.0], "Low": [99.0, 88.0, 84.0, 78.0]},
                    index=dates,
                )
            if ticker in {"KRW=X", "^VIX", "^TNX", "SPY"}:
                return pd.DataFrame({"Close": [100.0, 110.0, 115.0, 120.0]}, index=dates)
            return pd.DataFrame()

        mock_yf.side_effect = fake_download

        result = self.tester.simulate_scenario({"A": 1.0}, 10000, "2020_Covid_Crash")

        self.assertIn("macro_summary", result)
        self.assertEqual(len(result["macro_summary"]["items"]), 4)
        self.assertTrue(any(item["status"] == "데이터 없음" for item in result["macro_summary"]["items"]))
        self.assertIn("benchmark_comparison", result)
        self.assertTrue(any(row["symbol"] == "SPY" and row["status"] == "OK" for row in result["benchmark_comparison"]))
        self.assertIn("benchmark_price_paths", result)
        self.assertTrue(any(row["symbol"] == "SPY" for row in result["benchmark_price_paths"]))
        self.assertAlmostEqual(result["benchmark_price_paths"][0]["indexed_price"], 100.0)
        self.assertIn("macro_paths", result)
        self.assertTrue(any(row["symbol"] == "^VIX" for row in result["macro_paths"]))
        self.assertAlmostEqual(result["macro_paths"][0]["indexed_value"], 100.0)

    @mock.patch('yfinance.download')
    def test_2026_us_iran_war_scenario_uses_actual_historical_period(self, mock_yf):
        """2026 미국-이란 전쟁/호르무즈 충격 시나리오를 선택할 수 있다."""
        scenarios = self.tester.available_scenarios()
        dates = pd.to_datetime(["2026-02-27", "2026-03-02", "2026-03-03", "2026-05-22"])
        prices = {
            "AAPL": pd.DataFrame(
                {
                    "Close": [100.0, 95.0, 90.0, 92.0],
                    "High": [101.0, 97.0, 94.0, 95.0],
                    "Low": [99.0, 93.0, 88.0, 91.0],
                },
                index=dates,
            ),
            "XLE": pd.DataFrame(
                {
                    "Close": [50.0, 55.0, 57.0, 60.0],
                    "High": [51.0, 56.0, 58.0, 62.0],
                    "Low": [49.0, 54.0, 56.0, 59.0],
                },
                index=dates,
            ),
        }
        mock_yf.side_effect = lambda ticker, **kwargs: prices[ticker]

        self.assertIn("2026_US_Iran_War_Hormuz_Shock", scenarios)
        result = self.tester.simulate_named_scenario(
            {"AAPL": 0.5, "XLE": 0.5},
            10000,
            "2026_US_Iran_War_Hormuz_Shock",
        )

        self.assertEqual(result["scenario_type"], "historical")
        self.assertAlmostEqual(result["details"]["AAPL"], -0.08)
        self.assertAlmostEqual(result["details"]["XLE"], 0.20)
        self.assertAlmostEqual(result["portfolio_return"], 0.06)
        self.assertEqual(result["path"][0]["date"], "2026-02-27")
        self.assertTrue(any(row["symbol"] == "XLE" for row in result["asset_price_paths"]))

    @mock.patch('yfinance.download')
    def test_2026_us_iran_war_scenario_uses_asset_proxy_when_data_is_missing(self, mock_yf):
        """Known energy/gold proxies should keep scenario-specific shocks if price data is missing."""
        mock_yf.return_value = pd.DataFrame()

        result = self.tester.simulate_named_scenario(
            {"XLE": 1.0},
            10000,
            "2026_US_Iran_War_Hormuz_Shock",
        )

        self.assertTrue(result["proxy_used"])
        self.assertAlmostEqual(result["details"]["XLE"], 0.12)
        self.assertAlmostEqual(result["portfolio_return"], 0.12)

    def test_classify_stress_risk_uses_path_metrics_and_data_quality(self):
        """위험 판정은 기간 수익률뿐 아니라 경로 손실과 데이터 품질을 반영한다."""
        self.assertEqual(
            self.tester.classify_stress_risk(
                -0.05,
                risk_metrics={"Max_Drawdown": -0.22},
                data_quality={"level": "HIGH"},
            ),
            "HIGH",
        )
        self.assertEqual(
            self.tester.classify_stress_risk(
                -0.05,
                risk_metrics={"Max_Drawdown": -0.05},
                data_quality={"level": "LOW"},
            ),
            "DATA_LIMITED",
        )
        self.assertEqual(
            self.tester.classify_stress_risk(
                -0.30,
                risk_metrics={"Max_Drawdown": -0.30},
                data_quality={"level": "LOW"},
            ),
            "HIGH_DATA_LIMITED",
        )


if __name__ == '__main__':
    unittest.main()

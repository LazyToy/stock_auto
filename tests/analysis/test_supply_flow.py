import pandas as pd

from src.analysis.growth_stock_finder import GrowthStock, HybridGrowthStockFinder
from src.analysis.supply_flow import SupplyFlowAnalysis, SupplyFlowProvider


def test_supply_flow_uses_naver_records_before_pykrx_fallback():
    pykrx_calls = []
    provider = SupplyFlowProvider(
        naver_fetcher=lambda ticker: [
            {"date": "2026.05.26", "foreign": 1200, "institution": 800},
            {"date": "2026.05.25", "foreign": 900, "institution": 400},
            {"date": "2026.05.22", "foreign": 600, "institution": -100},
        ],
        pykrx_fetcher=lambda ticker: pykrx_calls.append(ticker) or [],
    )

    analysis = provider.analyze("036540.KQ")

    assert analysis.source == "naver"
    assert analysis.flow_unit == "주"
    assert analysis.ticker == "036540"
    assert analysis.foreign_5d_sum == 2700
    assert analysis.institution_5d_sum == 1100
    assert analysis.smart_money_5d_sum == 3800
    assert analysis.score > 0
    assert pykrx_calls == []


def test_supply_flow_falls_back_to_pykrx_when_naver_is_empty():
    pykrx_frame = pd.DataFrame(
        {
            "외국인합계": [1000, 700, -100],
            "기관합계": [500, 300, 100],
        },
        index=pd.to_datetime(["2026-05-26", "2026-05-25", "2026-05-22"]),
    )
    provider = SupplyFlowProvider(
        naver_fetcher=lambda ticker: [],
        pykrx_fetcher=lambda ticker: pykrx_frame,
    )

    analysis = provider.analyze("036540")

    assert analysis.source == "pykrx"
    assert analysis.flow_unit == "KRW"
    assert analysis.latest_foreign == 1000
    assert analysis.latest_institution == 500
    assert analysis.smart_money_5d_sum == 2500
    assert analysis.score > 0


def test_supply_flow_detects_buy_reversal_as_positive_signal():
    provider = SupplyFlowProvider(
        naver_fetcher=lambda ticker: [
            {"date": "2026.05.26", "foreign": 1500, "institution": 200},
            {"date": "2026.05.25", "foreign": -300, "institution": 100},
            {"date": "2026.05.22", "foreign": -400, "institution": 100},
            {"date": "2026.05.21", "foreign": -500, "institution": 100},
            {"date": "2026.05.20", "foreign": -200, "institution": 100},
            {"date": "2026.05.19", "foreign": -100, "institution": 100},
        ],
        pykrx_fetcher=lambda ticker: [],
    )

    analysis = provider.analyze("036540")

    assert "외국인매수전환" in analysis.reversal_types
    assert analysis.score >= 0.5
    assert "외국인매수전환" in analysis.reason


def test_growth_finder_applies_supply_flow_to_kr_candidates():
    class FakeFlowProvider:
        def __init__(self):
            self.calls = []

        def analyze(self, symbol):
            self.calls.append(symbol)
            return SupplyFlowAnalysis(
                ticker=symbol,
                source="naver",
                score=0.8,
                latest_foreign=1200,
                latest_institution=300,
                foreign_5d_sum=3500,
                institution_5d_sum=900,
                smart_money_5d_sum=4400,
                flow_unit="주",
                positive_days_5d=4,
                reversal_types=["기관매수전환"],
                reason="기관매수전환, 5일 수급 +4,400 주",
            )

    class Finder(HybridGrowthStockFinder):
        def _screen_with_yfinance(self, symbols):
            return [
                GrowthStock(
                    symbol="036540",
                    name="테스트",
                    sector="반도체",
                    growth_score=7.0,
                    financial_health="Good",
                    reason="매출 성장률 20.0%",
                    market_cap="중형주",
                )
            ]

    flow_provider = FakeFlowProvider()
    finder = Finder(flow_provider=flow_provider)

    results = finder.search_growth_stocks(
        market="KR",
        top_n=1,
        candidate_mode="static",
    )
    row = finder.to_dataframe_dict()[0]

    assert flow_provider.calls == ["036540"]
    assert results[0].growth_score == 7.8
    assert results[0].supply_flow_score == 0.8
    assert results[0].supply_flow_source == "naver"
    assert results[0].supply_flow_unit == "주"
    assert "수급 0.8" in results[0].reason
    assert row["수급점수"] == 0.8
    assert row["5일스마트머니순매수"] == 4400
    assert row["수급단위"] == "주"

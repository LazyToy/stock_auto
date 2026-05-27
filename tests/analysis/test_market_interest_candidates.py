import pandas as pd

from src.analysis.growth_stock_finder import GrowthStock, HybridGrowthStockFinder
from src.analysis.market_interest import MarketInterestCandidate, MarketInterestCandidateProvider


def _history(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-04-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "Close": closes,
            "High": [value * 1.01 for value in closes],
            "Volume": volumes,
        },
        index=dates,
    )


def test_market_interest_ranks_sustained_attention_above_one_day_spike():
    market_frame = pd.DataFrame(
        [
            {
                "Code": "111111",
                "Name": "꾸준성장",
                "Market": "KOSDAQ",
                "Close": 125,
                "ChagesRatio": 3.2,
                "Amount": 150_000_000_000,
                "Marcap": 800_000_000_000,
                "Volume": 3_000_000,
            },
            {
                "Code": "222222",
                "Name": "당일급등",
                "Market": "KOSDAQ",
                "Close": 112,
                "ChagesRatio": 18.0,
                "Amount": 180_000_000_000,
                "Marcap": 700_000_000_000,
                "Volume": 9_000_000,
            },
        ]
    )
    histories = {
        "111111.KQ": _history(
            [100 + i for i in range(26)],
            [1_000_000] * 20 + [3_000_000] * 6,
        ),
        "222222.KQ": _history(
            [100] * 25 + [112],
            [1_000_000] * 25 + [9_000_000],
        ),
    }

    provider = MarketInterestCandidateProvider(
        kr_market_fetcher=lambda: market_frame,
        history_fetcher=lambda symbol: histories[symbol],
    )

    candidates = provider.build_candidates("KR", limit=2, prefilter_limit=2)

    assert [candidate.symbol for candidate in candidates] == ["111111.KQ", "222222.KQ"]
    assert candidates[0].current_price == 125
    assert candidates[0].price_currency == "KRW"
    assert candidates[0].momentum_20d > candidates[1].momentum_20d
    assert candidates[0].volume_ratio_20d > 1.0


def test_market_interest_penalizes_overheated_recent_runner():
    market_frame = pd.DataFrame(
        [
            {
                "ticker": "STEADY",
                "name": "Steady Compounder",
                "sector": "Technology",
                "close": 130,
                "change": 2.0,
                "volume_value": 80_000_000,
                "market_cap": 2_000_000_000,
                "volume": 2_000_000,
            },
            {
                "ticker": "SPIKE",
                "name": "Single Day Spike",
                "sector": "Technology",
                "close": 125,
                "change": 24.0,
                "volume_value": 400_000_000,
                "market_cap": 2_000_000_000,
                "volume": 15_000_000,
            },
        ]
    )
    histories = {
        "STEADY": _history(
            [100 + i for i in range(31)],
            [1_000_000] * 20 + [2_000_000] * 11,
        ),
        "SPIKE": _history(
            [100] * 29 + [101, 125],
            [1_000_000] * 29 + [1_100_000, 15_000_000],
        ),
    }

    provider = MarketInterestCandidateProvider(
        us_market_fetcher=lambda: market_frame,
        history_fetcher=lambda symbol: histories[symbol],
    )

    candidates = provider.build_candidates("US", limit=2, prefilter_limit=2)

    assert [candidate.symbol for candidate in candidates] == ["STEADY", "SPIKE"]
    assert candidates[1].overheat_penalty < 0
    assert "overheat" in candidates[1].reason


def test_market_interest_adds_sector_relative_rank():
    market_frame = pd.DataFrame(
        [
            {
                "ticker": "BEST",
                "name": "Best In Sector",
                "sector": "Technology",
                "close": 140,
                "change": 2.0,
                "volume_value": 120_000_000,
                "market_cap": 2_000_000_000,
                "volume": 2_000_000,
            },
            {
                "ticker": "MID",
                "name": "Middle In Sector",
                "sector": "Technology",
                "close": 120,
                "change": 1.0,
                "volume_value": 90_000_000,
                "market_cap": 2_000_000_000,
                "volume": 1_500_000,
            },
            {
                "ticker": "OTHER",
                "name": "Other Sector Leader",
                "sector": "Healthcare",
                "close": 125,
                "change": 1.0,
                "volume_value": 80_000_000,
                "market_cap": 2_000_000_000,
                "volume": 1_300_000,
            },
        ]
    )
    histories = {
        "BEST": _history([100 + i * 2 for i in range(31)], [1_000_000] * 20 + [2_000_000] * 11),
        "MID": _history([100 + i for i in range(31)], [1_000_000] * 20 + [1_500_000] * 11),
        "OTHER": _history([100 + i for i in range(31)], [1_000_000] * 20 + [1_300_000] * 11),
    }
    provider = MarketInterestCandidateProvider(
        us_market_fetcher=lambda: market_frame,
        history_fetcher=lambda symbol: histories[symbol],
    )

    candidates = provider.build_candidates("US", limit=3, prefilter_limit=3)
    by_symbol = {candidate.symbol: candidate for candidate in candidates}

    assert by_symbol["BEST"].sector_rank == 1
    assert by_symbol["BEST"].current_price == 140
    assert by_symbol["BEST"].price_currency == "USD"
    assert by_symbol["BEST"].sector_count == 2
    assert by_symbol["BEST"].sector_percentile == 1.0
    assert by_symbol["MID"].sector_rank == 2
    assert by_symbol["OTHER"].sector_rank == 1


def test_growth_finder_uses_market_candidates_before_financial_screening():
    class FakeProvider:
        def __init__(self):
            self.calls = []

        def build_candidates(
            self,
            market: str,
            *,
            limit: int,
            prefilter_limit: int,
            interest_window_days: int,
        ):
            self.calls.append((market, limit, prefilter_limit, interest_window_days))
            return [
                MarketInterestCandidate(symbol="AAA", name="Alpha", market="US", sector="Tech", interest_score=9.0),
                MarketInterestCandidate(symbol="BBB", name="Beta", market="US", sector="Health", interest_score=8.0),
                MarketInterestCandidate(symbol="CCC", name="Gamma", market="US", sector="Energy", interest_score=7.0),
            ]

    class CapturingFinder(HybridGrowthStockFinder):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.screened_symbols = []

        def _screen_with_yfinance(self, symbols):
            self.screened_symbols = list(symbols)
            return [
                GrowthStock(
                    symbol=symbol,
                    name=symbol,
                    sector="Tech",
                    growth_score=9.0 - index,
                    financial_health="Good",
                    reason="test",
                    market_cap="중형주",
                )
                for index, symbol in enumerate(symbols)
            ]

    provider = FakeProvider()
    finder = CapturingFinder(candidate_provider=provider)

    results = finder.search_growth_stocks(
        market="US",
        top_n=1,
        candidate_mode="market",
        candidate_limit=2,
        prefilter_limit=3,
        interest_window_days=60,
    )

    assert provider.calls == [("US", 2, 3, 60)]
    assert finder.screened_symbols == ["AAA", "BBB"]
    assert [stock.symbol for stock in results] == ["AAA"]


def test_growth_finder_copies_market_candidate_price_and_currency():
    class FakeProvider:
        def build_candidates(self, market, *, limit, prefilter_limit, interest_window_days):
            return [
                MarketInterestCandidate(
                    symbol="AAA",
                    name="Alpha",
                    market="US",
                    sector="Tech",
                    interest_score=9.0,
                    current_price=1234.5,
                    price_currency="USD",
                )
            ]

    class Finder(HybridGrowthStockFinder):
        def _screen_with_yfinance(self, symbols):
            return [
                GrowthStock(
                    symbol="AAA",
                    name="Alpha",
                    sector="Tech",
                    growth_score=7.0,
                    financial_health="Good",
                    reason="test",
                    market_cap="중형주",
                )
            ]

    finder = Finder(candidate_provider=FakeProvider())

    stock = finder.search_growth_stocks(market="US", top_n=1, candidate_mode="market")[0]
    row = finder.to_dataframe_dict()[0]

    assert stock.current_price == 1234.5
    assert stock.price_currency == "USD"
    assert row["현재가"] == "1,234.50 USD"


def test_interest_window_changes_momentum_metric_and_reason():
    market_frame = pd.DataFrame(
        [
            {
                "ticker": "LONG",
                "name": "Long Trend",
                "sector": "Technology",
                "close": 180,
                "change": 1.0,
                "volume_value": 90_000_000,
                "market_cap": 3_000_000_000,
                "volume": 3_000_000,
            }
        ]
    )
    histories = {
        "LONG": _history(
            [100 + i for i in range(70)],
            [1_000_000] * 45 + [2_000_000] * 25,
        )
    }

    provider = MarketInterestCandidateProvider(
        us_market_fetcher=lambda: market_frame,
        history_fetcher=lambda symbol: histories[symbol],
    )

    candidate = provider.build_candidates(
        "US",
        limit=1,
        prefilter_limit=1,
        interest_window_days=60,
    )[0]

    assert candidate.interest_window_days == 60
    assert candidate.momentum_window is not None
    assert candidate.momentum_window > candidate.momentum_20d
    assert "60d momentum" in candidate.reason


def test_score_breakdown_penalizes_low_confidence_financial_data():
    finder = HybridGrowthStockFinder()

    complete = finder._calculate_score_breakdown(
        revenue_growth=25,
        profit_margin=12,
        debt_to_equity=70,
        current_ratio=1.8,
        pe_ratio=20,
    )
    sparse = finder._calculate_score_breakdown(
        revenue_growth=None,
        profit_margin=None,
        debt_to_equity=None,
        current_ratio=None,
        pe_ratio=None,
    )

    assert complete["data_confidence"] == 1.0
    assert sparse["data_confidence"] < 0.5
    assert sparse["risk_penalty"] < 0
    assert complete["total_score"] > sparse["total_score"]


def test_financial_persistence_scores_multi_year_growth():
    finder = HybridGrowthStockFinder()
    financials = pd.DataFrame(
        {
            "2025": [160.0, 24.0],
            "2024": [130.0, 12.0],
            "2023": [100.0, -5.0],
            "2022": [80.0, -10.0],
        },
        index=["Total Revenue", "Operating Income"],
    )

    persistence = finder._calculate_financial_persistence(financials)
    score = finder._calculate_score_breakdown(
        revenue_growth=25,
        profit_margin=12,
        debt_to_equity=70,
        current_ratio=1.8,
        pe_ratio=20,
        financial_persistence_score=persistence["financial_persistence_score"],
    )

    assert persistence["revenue_cagr_3y"] > 20
    assert persistence["operating_income_trend"] > 0
    assert persistence["financial_persistence_score"] > 0
    assert score["financial_persistence_score"] == persistence["financial_persistence_score"]


def test_dataframe_conversion_tolerates_old_growth_stock_objects():
    class OldGrowthStock:
        symbol = "OLD"
        name = "Old Corp"
        sector = "Tech"
        growth_score = 7.0
        financial_health = "Good"
        market_cap = "중형주"
        revenue_growth = 20.0
        profit_margin = 10.0
        debt_to_equity = None
        current_ratio = None
        pe_ratio = None
        news_sentiment = ""
        reason = "old object"

    finder = HybridGrowthStockFinder()
    finder.cached_results = [OldGrowthStock()]

    analysis = finder.get_sector_analysis()
    row = finder.to_dataframe_dict()[0]

    assert analysis["avg_data_confidence"] == 0.0
    assert row["데이터신뢰도"] == 0.0
    assert row["시장관심도"] is None

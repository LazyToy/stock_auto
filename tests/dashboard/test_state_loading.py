import unittest
from unittest import mock
import os
import tempfile

import dashboard.stress_helpers as stress_helpers
from dashboard.state_loader import load_state
from dashboard.stress_helpers import (
    STRESS_RESULT_CURRENCY,
    build_existing_portfolio_weights,
    format_krw_input_amount,
    format_stress_amount,
    infer_portfolio_currency,
    infer_symbol_currency,
    normalize_portfolio_weights,
    portfolio_rows_to_weights,
    portfolio_weights_to_rows,
    parse_krw_input_amount,
    parse_portfolio_text,
    validate_portfolio_weights,
)


class TestDashboardStateLoading(unittest.TestCase):
    @mock.patch('dashboard.state_loader.os.path.exists')
    @mock.patch('builtins.open', new_callable=mock.mock_open)
    @mock.patch('dashboard.state_loader.json.load')
    def test_load_state_merges_high_water_marks(self, mock_json_load, mock_file, mock_exists):
        """dashboard_state_file에 high_water_marks가 없을 때 trading_state.json에서 병합되는지 확인"""
        mock_exists.return_value = True
        mock_json_load.side_effect = [
            {'timestamp': '2026-01-01', 'market': 'KR'},
            {'high_water_marks': {'NVDA': 100, 'AAPL': 50}}
        ]

        state = load_state('KR')
        self.assertIn('high_water_marks', state)
        self.assertEqual(state['high_water_marks'], {'NVDA': 100, 'AAPL': 50})

    def test_build_existing_portfolio_weights_adds_ks_suffix(self):
        """기존 포트폴리오 로더가 한국 종목에 .KS를 붙이는지 확인"""
        state = {
            'high_water_marks': {
                'NVDA': 100,
                '005930': 200,
                '000660': 300,
            }
        }
        weights = build_existing_portfolio_weights(state)
        self.assertEqual(set(weights.keys()), {'NVDA', '005930.KS', '000660.KS'})
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_infer_symbol_currency_labels_quote_currency(self):
        """종목 표/차트에 표시할 거래소 기준 통화를 추정한다."""
        self.assertEqual(infer_symbol_currency('005930.KS'), 'KRW')
        self.assertEqual(infer_symbol_currency('123456'), 'KRW')
        self.assertEqual(infer_symbol_currency('AAPL'), 'USD')

    def test_infer_portfolio_currency_detects_mixed_quotes(self):
        """혼합 통화 포트폴리오는 환산 없이 입력 통화 기준임을 표시한다."""
        self.assertEqual(infer_portfolio_currency({'AAPL': 0.5, 'MSFT': 0.5}), 'USD')
        self.assertEqual(infer_portfolio_currency({'005930.KS': 1.0}), 'KRW')
        self.assertEqual(infer_portfolio_currency({'AAPL': 0.5, '005930.KS': 0.5}), 'INPUT')

    def test_format_stress_amount_uses_currency_labels(self):
        """Stress Test 금액 표기는 통화별 형식을 사용한다."""
        self.assertEqual(format_stress_amount(1234.56, 'KRW'), '₩1,235')
        self.assertEqual(format_stress_amount(1234.56, 'USD'), '$1,234.56')
        self.assertEqual(format_stress_amount(1234.56, 'INPUT'), '1,234.56 (입력 통화)')

    def test_stress_result_currency_is_krw(self):
        """Simulation Results의 포트폴리오 금액 표기는 원화로 고정한다."""
        self.assertEqual(STRESS_RESULT_CURRENCY, 'KRW')

    def test_krw_input_amount_formats_and_parses_commas(self):
        """총 포트폴리오 가치 입력은 천 단위 쉼표를 표시하고 파싱한다."""
        self.assertEqual(format_krw_input_amount(10000000), '10,000,000')
        self.assertEqual(parse_krw_input_amount('10,000,000'), 10000000)
        self.assertEqual(parse_krw_input_amount(' 1,234,567 '), 1234567)

    def test_display_number_formatter_adds_commas(self):
        formatter = getattr(stress_helpers, "format_display_number", None)
        self.assertIsNotNone(formatter)
        self.assertEqual(formatter(1234567.891, digits=2), "1,234,567.89")
        self.assertEqual(formatter(1234567.0, digits=0), "1,234,567")
        self.assertEqual(formatter(None), "N/A")

    def test_macro_path_rows_are_split_for_readable_charts(self):
        splitter = getattr(stress_helpers, "split_macro_path_rows", None)
        self.assertIsNotNone(splitter)
        rows = [
            {"symbol": "KRW=X", "name": "USD/KRW", "value": 1350},
            {"symbol": "^VIX", "name": "VIX", "value": 25},
            {"symbol": "CL=F", "name": "WTI Oil", "value": 70},
        ]

        usdkrw_rows, other_rows = splitter(rows)

        self.assertEqual([row["symbol"] for row in usdkrw_rows], ["KRW=X"])
        self.assertEqual([row["symbol"] for row in other_rows], ["^VIX", "CL=F"])

    def test_benchmark_traces_start_hidden_until_legend_click(self):
        import plotly.graph_objects as go

        hider = getattr(stress_helpers, "hide_benchmark_traces_by_default", None)
        self.assertIsNotNone(hider)
        fig = go.Figure()
        fig.add_scatter(name="Holding: AAPL", x=[1], y=[1])
        fig.add_scatter(name="Benchmark: SPY (S&P 500)", x=[1], y=[1])

        hider(fig)

        self.assertIsNone(fig.data[0].visible)
        self.assertEqual(fig.data[1].visible, "legendonly")

    def test_stress_portfolio_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = os.path.join(tmp_dir, "stress_portfolios.json")

            stress_helpers.save_stress_portfolio(
                "Core US",
                {"AAPL": 0.3, "MSFT": 0.7},
                store_path=store_path,
            )
            saved = stress_helpers.load_stress_portfolios(store_path=store_path)

        self.assertEqual(saved, {"Core US": {"AAPL": 0.3, "MSFT": 0.7}})

    def test_stress_portfolio_save_rejects_blank_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = os.path.join(tmp_dir, "stress_portfolios.json")

            with self.assertRaises(ValueError):
                stress_helpers.save_stress_portfolio(
                    " ",
                    {"AAPL": 1.0},
                    store_path=store_path,
                )

    def test_krw_input_amount_rejects_invalid_text(self):
        """숫자와 쉼표 이외의 총 포트폴리오 가치 입력은 거부한다."""
        with self.assertRaises(ValueError):
            parse_krw_input_amount('10만원')

    def test_parse_portfolio_text_raises_on_invalid_weight(self):
        """잘못된 비율 입력 시 ValueError를 발생시키는지 확인"""
        with self.assertRaises(ValueError):
            parse_portfolio_text('AAPL:foo\nMSFT:0.5')

    def test_portfolio_rows_to_weights_parses_percent_table(self):
        """UI 표 입력은 비중 퍼센트를 0~1 비중으로 변환한다."""
        rows = [
            {'Symbol': ' AAPL ', 'Weight (%)': 30},
            {'Symbol': 'MSFT', 'Weight (%)': 30},
            {'Symbol': 'GOOGL', 'Weight (%)': 40},
            {'Symbol': '', 'Weight (%)': None},
        ]

        weights = portfolio_rows_to_weights(rows)

        self.assertEqual(weights, {'AAPL': 0.3, 'MSFT': 0.3, 'GOOGL': 0.4})

    def test_portfolio_rows_to_weights_raises_on_invalid_percent(self):
        """UI 표 입력의 비중이 숫자가 아니면 ValueError를 발생시킨다."""
        with self.assertRaises(ValueError):
            portfolio_rows_to_weights([{'Symbol': 'AAPL', 'Weight (%)': 'oops'}])

    def test_portfolio_weights_to_rows_returns_percent_rows(self):
        """비중 딕셔너리는 data editor 기본 행으로 변환된다."""
        rows = portfolio_weights_to_rows({'AAPL': 0.3, 'MSFT': 0.7})

        self.assertEqual(rows[0]['Symbol'], 'AAPL')
        self.assertAlmostEqual(rows[0]['Weight (%)'], 30.0)

    def test_validate_portfolio_weights_requires_near_one_total(self):
        """비중 합계가 1에서 벗어나면 검증 결과에 경고를 담는다."""
        result = validate_portfolio_weights({'AAPL': 0.8, 'MSFT': 0.8})

        self.assertFalse(result['is_valid'])
        self.assertTrue(result['can_normalize'])
        self.assertAlmostEqual(result['total_weight'], 1.6)
        self.assertTrue(result['warnings'])

    def test_validate_portfolio_weights_blocks_negative_weights(self):
        """음수 비중은 자동 정규화 대상이 아니라 실행 차단 대상이다."""
        result = validate_portfolio_weights({'AAPL': -0.5, 'MSFT': 1.5})

        self.assertFalse(result['is_valid'])
        self.assertFalse(result['can_normalize'])
        self.assertTrue(any('음수' in warning for warning in result['warnings']))

    def test_normalize_portfolio_weights_scales_positive_weights_to_one(self):
        """비중 정규화는 상대 비중을 보존하고 합계를 1로 맞춘다."""
        weights = normalize_portfolio_weights({'AAPL': 2.0, 'MSFT': 1.0})

        self.assertAlmostEqual(weights['AAPL'], 2 / 3)
        self.assertAlmostEqual(weights['MSFT'], 1 / 3)
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_build_existing_portfolio_weights_prefers_stock_market_values(self):
        """기존 포트폴리오는 가능하면 보유 종목 평가액으로 비중을 계산한다."""
        state = {
            'stocks': [
                {'symbol': 'AAPL', 'quantity': 2, 'current_price': 100},
                {'symbol': 'MSFT', 'quantity': 1, 'current_price': 300},
            ],
            'high_water_marks': {'SHOULD_NOT_USE': 1},
        }

        weights = build_existing_portfolio_weights(state)

        self.assertEqual(set(weights.keys()), {'AAPL', 'MSFT'})
        self.assertAlmostEqual(weights['AAPL'], 0.4)
        self.assertAlmostEqual(weights['MSFT'], 0.6)

    def test_build_existing_portfolio_weights_falls_back_when_eval_amt_is_invalid(self):
        """평가액 필드가 깨져 있으면 현재가와 수량으로 평가액을 계산한다."""
        state = {
            'stocks': [
                {'symbol': 'AAPL', 'eval_amt': 'N/A', 'quantity': 2, 'current_price': 100},
                {'symbol': 'MSFT', 'eval_amt': '', 'quantity': 1, 'current_price': 300},
            ],
        }

        weights = build_existing_portfolio_weights(state)

        self.assertAlmostEqual(weights['AAPL'], 0.4)
        self.assertAlmostEqual(weights['MSFT'], 0.6)

if __name__ == '__main__':
    unittest.main()

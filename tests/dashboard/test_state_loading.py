import unittest
from unittest import mock

from dashboard.state_loader import load_state
from dashboard.stress_helpers import build_existing_portfolio_weights, parse_portfolio_text


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

    def test_parse_portfolio_text_raises_on_invalid_weight(self):
        """잘못된 비율 입력 시 ValueError를 발생시키는지 확인"""
        with self.assertRaises(ValueError):
            parse_portfolio_text('AAPL:foo\nMSFT:0.5')

if __name__ == '__main__':
    unittest.main()

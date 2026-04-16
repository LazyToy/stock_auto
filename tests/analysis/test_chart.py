import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.analysis.chart import ChartGenerator

PNG_HEADER = bytes([137]) + b"PNG"
PNG_FAKE = PNG_HEADER + b"fake"


class _FontEntry:
    def __init__(self, name: str):
        self.name = name


class TestChartGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = ChartGenerator()
        dates = pd.date_range(start="2024-01-01", periods=50, freq="D")
        self.dummy_data = pd.DataFrame(
            {
                "Open": np.linspace(100, 150, 50),
                "High": np.linspace(105, 155, 50),
                "Low": np.linspace(95, 145, 50),
                "Close": np.linspace(102, 152, 50),
                "Volume": np.random.randint(1000, 2000, 50),
            },
            index=dates,
        )

    def test_generate_chart_image(self):
        """차트 이미지 생성 테스트"""
        image_bytes = self.generator.generate_chart(self.dummy_data, title="Test Chart")

        self.assertIsNotNone(image_bytes)
        assert image_bytes is not None
        self.assertIsInstance(image_bytes, bytes)
        self.assertGreater(len(image_bytes), 0)
        self.assertTrue(image_bytes.startswith(PNG_HEADER))

    def test_generate_chart_uses_hangul_capable_font_for_korean_title(self):
        """한글 제목이면 mplfinance 스타일 rc에 한글 폰트를 주입해야 한다."""
        styled = {"style_name": "hangul-test"}

        def fake_plot(*args, **kwargs):
            self.assertIs(kwargs["style"], styled)
            kwargs["savefig"]["fname"].write(PNG_FAKE)

        with patch(
            "src.analysis.chart.font_manager.fontManager.ttflist",
            [_FontEntry("Malgun Gothic"), _FontEntry("DejaVu Sans")],
        ), patch("src.analysis.chart.mpf.make_mpf_style", return_value=styled) as make_style, patch("src.analysis.chart.mpf.plot", side_effect=fake_plot):
            image_bytes = self.generator.generate_chart(
                self.dummy_data,
                title="005930 (삼성전자) 분석",
            )

        make_style.assert_called_once_with(
            base_mpf_style="yahoo",
            rc={"font.family": "Malgun Gothic", "axes.unicode_minus": False},
        )
        self.assertEqual(image_bytes, PNG_FAKE)

    def test_empty_data(self):
        """빈 데이터 처리 테스트"""
        empty_df = pd.DataFrame()
        result = self.generator.generate_chart(empty_df)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

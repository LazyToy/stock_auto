import io
import logging
from functools import lru_cache
from typing import Optional

from matplotlib import font_manager
import mplfinance as mpf
import pandas as pd

logger = logging.getLogger("ChartGenerator")

HANGUL_FONT_CANDIDATES = (
    "Malgun Gothic",
    "AppleGothic",
    "NanumGothic",
    "Noto Sans KR",
    "Noto Sans CJK KR",
)


@lru_cache(maxsize=1)
def _select_hangul_font() -> Optional[str]:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in HANGUL_FONT_CANDIDATES:
        if candidate in available_fonts:
            return candidate
    return None


def _contains_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


def _build_font_rc_params(title: str) -> dict[str, object]:
    if not title or not _contains_hangul(title):
        return {}

    font_name = _select_hangul_font()
    if not font_name:
        return {}

    return {
        "font.family": font_name,
        "axes.unicode_minus": False,
    }


class ChartGenerator:
    """주가 차트 이미지 생성기 (For Multimodal Analysis)"""

    def __init__(self, style: str = "yahoo"):
        self.style = style

    def generate_chart(self, df: pd.DataFrame, title: str = "Stock Chart", period: str = "Daily") -> Optional[bytes]:
        """
        OHLCV 데이터프레임을 받아 캔들스틱 차트 이미지를 bytes로 반환
        Args:
            df: OHLCV 컬럼이 있는 DataFrame (Index는 DatetimeIndex)
            title: 차트 제목
        Returns:
            bytes: PNG 이미지 데이터 (실패 시 None)
        """
        if df.empty:
            logger.warning("차트 생성 실패: 데이터가 비어있습니다.")
            return None

        try:
            if not isinstance(df.index, pd.DatetimeIndex):
                if "Date" in df.columns:
                    df = df.set_index("Date")
                df.index = pd.to_datetime(df.index)

            buf = io.BytesIO()
            rc_params = _build_font_rc_params(title)
            plot_style: str | dict[str, object] = self.style
            if rc_params:
                plot_style = mpf.make_mpf_style(base_mpf_style=self.style, rc=rc_params)

            mpf.plot(
                df,
                type="candle",
                style=plot_style,
                title=title,
                ylabel="Price",
                volume=True,
                mav=(20, 60),
                savefig=dict(fname=buf, dpi=100, bbox_inches="tight", format="png"),
            )

            buf.seek(0)
            return buf.read()

        except Exception as e:
            logger.error(f"차트 이미지 생성 중 오류: {e}")
            return None

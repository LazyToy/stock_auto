"""Smart Money 분석 데이터 모델

PR-02: 스윙 프랙탈, 시장구조, 구조 돌파 dataclass 및 enum 정의.
PR-03: Fair Value Gap (FVG) dataclass 및 enum 정의 추가.

설계 원칙:
    - 이 파일은 public dataclass와 enum만 포함한다.
    - 탐지 로직은 포함하지 않는다.
    - 후속 PR(FVG, OrderBlock 등)의 모델도 이 파일에 추가한다."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ────────────────────────────────────────────────────────────
# Enum 정의
# ────────────────────────────────────────────────────────────


class SwingType(str, Enum):
    """스윙 포인트 유형"""

    HIGH = "HIGH"  # 스윙 하이 (고점)
    LOW = "LOW"  # 스윙 로우 (저점)


class MarketStructure(str, Enum):
    """시장 구조 방향

    Attributes:
        BULLISH: 상승 구조 (Higher High + Higher Low 반복)
        BEARISH: 하락 구조 (Lower High + Lower Low 반복)
        RANGE: 박스권/혼조 구조
    """

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"


class BreakType(str, Enum):
    """구조 돌파 유형

    Attributes:
        BOS: Break of Structure — 기존 추세 방향과 동일한 돌파 (추세 지속)
        CHOCH: Change of Character — 기존 추세를 역전하는 돌파 (추세 전환)
    """

    BOS = "BOS"  # Break of Structure
    CHOCH = "CHOCH"  # Change of Character


class FVGDirection(str, Enum):
    """FVG 방향

    Attributes:
        BULLISH: 상승 FVG (캔들 i-2의 high < 캔들 i의 low → 갭 상방)
        BEARISH: 하락 FVG (캔들 i-2의 low > 캔들 i의 high → 갭 하방)
    """

    BULLISH = "BULLISH"  # 상승 FVG
    BEARISH = "BEARISH"  # 하락 FVG


class FVGStatus(str, Enum):
    """FVG 상태

    Attributes:
        OPEN: 갭이 아직 가격에 접촉되지 않은 상태
        TOUCHED: 가격이 갭 범위에 진입한 상태
        FILLED: 갭 범위가 완전히 메워진 상태
    """

    OPEN = "OPEN"  # 미접촉
    TOUCHED = "TOUCHED"  # 갭 범위 진입
    FILLED = "FILLED"  # 완전 메움


class OrderBlockDirection(str, Enum):
    """캔들 오더블록 방향"""

    BULLISH = "BULLISH"  # 상승 오더블록
    BEARISH = "BEARISH"  # 하락 오더블록


class OrderBlockStatus(str, Enum):
    """캔들 오더블록 상태

    Attributes:
        FRESH: 생성 이후 아직 zone에 재진입하지 않은 상태
        MITIGATED: 가격이 zone에 재진입한 상태
        INVALIDATED: 가격이 zone 반대편을 돌파해 무효화된 상태
    """

    FRESH = "FRESH"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"


class LiquiditySweepDirection(str, Enum):
    """liquidity sweep 이후 기대 방향."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class BreakDirection(str, Enum):
    """구조 돌파 방향"""

    BULLISH = "BULLISH"  # 상방 돌파
    BEARISH = "BEARISH"  # 하방 돌파


# ────────────────────────────────────────────────────────────
# Dataclass 정의
# ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SwingPoint:
    """스윙 포인트 (확정된 고점 또는 저점)

    Attributes:
        timestamp: 해당 캔들의 시각
        price: 스윙 포인트의 가격 (HIGH이면 high 값, LOW이면 low 값)
        swing_type: HIGH 또는 LOW
        bar_index: DataFrame 내 위치 인덱스 (0-based)
    """

    timestamp: datetime
    price: float
    swing_type: SwingType
    bar_index: int


@dataclass(frozen=True)
class StructureBreak:
    """구조 돌파 이벤트

    Attributes:
        timestamp: 돌파가 발생한 캔들의 시각
        break_type: BOS 또는 CHOCH
        direction: 돌파 방향 (BULLISH=상방, BEARISH=하방)
        broken_level: 돌파된 스윙 가격 수준
        bar_index: DataFrame 내 위치 인덱스 (0-based)
    """

    timestamp: datetime
    break_type: BreakType
    direction: BreakDirection
    broken_level: float
    bar_index: int


@dataclass
class SwingAnalysisResult:
    """스윙 분석 통합 결과

    swings: 탐지된 스윙 포인트 리스트 (시간 오름차순)
    structure: 최종 시장 구조 방향
    structure_breaks: 탐지된 구조 돌파 이벤트 리스트 (시간 오름차순)
    warnings: 분석 중 발생한 경고 메시지 목록 (예: 데이터 부족)
    """

    swings: list[SwingPoint] = field(default_factory=list)
    structure: MarketStructure = MarketStructure.RANGE
    structure_breaks: list[StructureBreak] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ────────────────────────────────────────────────────────────
# PR-03: FVG Dataclass
# ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FairValueGap:
    """Fair Value Gap (3-캔들 불균형 갭) 탐지 결과

    3개 연속 캔들에서 캔들 i-2와 캔들 i 사이의 겹치지 않는 가격 구간입니다.

    Attributes:
        direction: 갭 방향 (BULLISH=상승 갭, BEARISH=하락 갭)
        lower: 갭 하단 가격 (Bullish: high[i-2], Bearish: high[i])
        upper: 갭 상단 가격 (Bullish: low[i], Bearish: low[i-2])
        created_at: 갭이 형성된 캔들(i번째 캔들)의 timestamp
        bar_index: 갭이 확정된 캔들(i번째 캔들)의 DataFrame 내 위치 (0-based)
        status: 갭의 현재 상태 (OPEN / TOUCHED / FILLED)
    """

    direction: FVGDirection
    lower: float
    upper: float
    created_at: datetime
    bar_index: int
    status: FVGStatus = FVGStatus.OPEN


@dataclass(frozen=True)
class OrderBlock:
    """캔들 오더블록 탐지 결과

    구조 돌파가 확정되기 직전 lookback 구간에서 발견한 마지막 반대색 캔들을
    보수적인 전체 캔들 zone으로 표현한다.

    Attributes:
        direction: 오더블록 방향 (BULLISH / BEARISH)
        lower: zone 하단 가격
        upper: zone 상단 가격
        created_at: 오더블록 후보 캔들의 timestamp
        bar_index: 오더블록 후보 캔들의 DataFrame 내 위치 (0-based)
        break_at: 오더블록을 확정한 구조 돌파 캔들의 timestamp
        break_bar_index: 구조 돌파 캔들의 DataFrame 내 위치 (0-based)
        status: 현재 상태 (FRESH / MITIGATED / INVALIDATED)
        strength: 거래량 등 보조 조건으로 보정한 강도 점수
    """

    direction: OrderBlockDirection
    lower: float
    upper: float
    created_at: datetime
    bar_index: int
    break_at: datetime
    break_bar_index: int
    status: OrderBlockStatus = OrderBlockStatus.FRESH
    strength: float = 1.0


@dataclass(frozen=True)
class LiquiditySweep:
    """스윙 레벨을 찌른 뒤 되돌린 liquidity sweep 이벤트."""

    direction: LiquiditySweepDirection
    swept_level: float
    timestamp: datetime
    bar_index: int
    swept_swing_bar_index: int


@dataclass(frozen=True)
class SignalContribution:
    """최종 신호 점수에 반영된 개별 기여 항목."""

    timeframe: str
    component: str
    direction: str
    score: float
    reason: str


@dataclass(frozen=True)
class SignalConfig:
    """Smart Money 신호 점수화 기본 설정."""

    buy_threshold: float = 0.50
    sell_threshold: float = -0.50
    min_confidence: float = 0.55
    min_confirming_timeframes: int = 2
    timeframe_weights: dict[str, float] = field(
        default_factory=lambda: {
            "daily": 0.40,
            "hourly": 0.35,
            "minute_5": 0.25,
        }
    )
    stale_pattern_penalty_per_bar: float = 0.01
    max_patterns_per_type: int = 5
    conflict_penalty: float = 0.20
    insufficient_data_penalty: float = 0.15
    invalidation_proximity_penalty: float = 0.05


@dataclass(frozen=True)
class SmartMoneyPatternConfig:
    """Smart Money 패턴 탐지 파라미터."""

    swing_left: int = 2
    swing_right: int = 2
    fvg_min_gap_pct: float = 0.001
    order_block_lookback: int = 10
    liquidity_sweep_tolerance_pct: float = 0.001
    displacement_atr_multiplier: float = 0.0
    atr_period: int = 14


@dataclass(frozen=True)
class SmartMoneySignal:
    """멀티타임프레임 조합 결과로 산출된 최종 신호."""

    signal: str
    confidence: float
    score: float
    risk_level: str
    entry_zone: tuple[float, float] | None = None
    invalidation_level: float | None = None
    take_profit_candidates: list[float] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    contributions: list[SignalContribution] = field(default_factory=list)

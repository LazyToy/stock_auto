"""시장 운영 시간 관리자

한국 및 미국 주식 시장의 운영 시간을 체크합니다.

주요 기능:
- 현재 시장이 열려있는지 확인
- 장 시작/종료 시간 반환
- 휴장일 체크 (공휴일)
- 미국 프리마켓/애프터마켓 지원
"""

import os
import logging
from datetime import datetime, time, timedelta
from typing import Optional, Tuple, Dict
from enum import Enum
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


class MarketSession(Enum):
    """시장 세션"""
    CLOSED = "closed"           # 폐장
    PRE_MARKET = "pre_market"   # 프리마켓 (미국)
    REGULAR = "regular"         # 정규장
    AFTER_HOURS = "after_hours" # 애프터마켓 (미국)


@dataclass
class MarketHours:
    """시장 운영 시간"""
    regular_open: time
    regular_close: time
    pre_market_open: Optional[time] = None
    pre_market_close: Optional[time] = None
    after_hours_open: Optional[time] = None
    after_hours_close: Optional[time] = None


class MarketTimeChecker:
    """시장 시간 체커
    
    한국 및 미국 시장의 운영 시간을 관리합니다.
    """
    
    # 한국 시장 (KST)
    KR_MARKET_HOURS = MarketHours(
        regular_open=time(9, 0),
        regular_close=time(15, 30)
    )
    
    # 미국 시장 (EST → KST 변환됨, 서머타임 미적용 기준)
    # EST 09:30-16:00 → KST 23:30-06:00 (다음날)
    # 프리마켓: EST 04:00-09:30 → KST 18:00-23:30
    # 애프터: EST 16:00-20:00 → KST 06:00-10:00 (다음날)
    US_MARKET_HOURS = MarketHours(
        regular_open=time(23, 30),   # KST 기준
        regular_close=time(6, 0),
        pre_market_open=time(18, 0),
        pre_market_close=time(23, 30),
        after_hours_open=time(6, 0),
        after_hours_close=time(10, 0)
    )
    
    # 한국 공휴일 (연도별 업데이트 필요)
    KR_HOLIDAYS_2026 = [
        "2026-01-01",  # 신정
        "2026-02-16", "2026-02-17", "2026-02-18",  # 설날
        "2026-03-01",  # 삼일절
        "2026-05-05",  # 어린이날
        "2026-05-24",  # 부처님오신날
        "2026-06-06",  # 현충일
        "2026-08-15",  # 광복절
        "2026-09-26", "2026-09-27", "2026-09-28",  # 추석
        "2026-10-03",  # 개천절
        "2026-10-09",  # 한글날
        "2026-12-25",  # 크리스마스
    ]
    
    # 미국 공휴일 (연도별 업데이트 필요)
    US_HOLIDAYS_2026 = [
        "2026-01-01",  # New Year's Day
        "2026-01-19",  # MLK Day
        "2026-02-16",  # Presidents Day
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day
        "2026-06-19",  # Juneteenth
        "2026-07-03",  # Independence Day (observed)
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving
        "2026-12-25",  # Christmas
    ]
    
    def __init__(self, market: str = "KR"):
        """초기화
        
        Args:
            market: 시장 코드 ("KR" 또는 "US")
        """
        self.market = market.upper()
        self.hours = self.KR_MARKET_HOURS if self.market == "KR" else self.US_MARKET_HOURS
        self.holidays = self.KR_HOLIDAYS_2026 if self.market == "KR" else self.US_HOLIDAYS_2026
        
        # 커스텀 휴장일 로드
        self._load_custom_holidays()
    
    def _load_custom_holidays(self):
        """커스텀 휴장일 파일 로드"""
        holidays_file = f"data/holidays_{self.market.lower()}.json"
        if os.path.exists(holidays_file):
            try:
                with open(holidays_file, 'r') as f:
                    custom = json.load(f)
                    self.holidays.extend(custom.get('holidays', []))
                    logger.debug(f"커스텀 휴장일 로드: {len(custom.get('holidays', []))}개")
            except Exception as e:
                logger.warning(f"휴장일 파일 로드 실패: {e}")
    
    def is_holiday(self, date: datetime = None) -> bool:
        """휴장일 여부 확인"""
        date = date or datetime.now()
        date_str = date.strftime("%Y-%m-%d")
        return date_str in self.holidays
    
    def is_weekend(self, date: datetime = None) -> bool:
        """주말 여부 확인"""
        date = date or datetime.now()
        return date.weekday() >= 5  # 토(5), 일(6)
    
    def get_current_session(self, now: datetime = None) -> MarketSession:
        """현재 시장 세션 반환"""
        now = now or datetime.now()
        current_time = now.time()
        
        # 주말 또는 휴장일 체크
        if self.is_weekend(now) or self.is_holiday(now):
            return MarketSession.CLOSED
        
        if self.market == "KR":
            # 한국 시장: 단순 시간 비교
            if self.hours.regular_open <= current_time <= self.hours.regular_close:
                return MarketSession.REGULAR
            return MarketSession.CLOSED
        
        else:  # 미국 시장 (KST 기준)
            # 미국 정규장 (23:30 ~ 다음날 06:00)
            if current_time >= self.hours.regular_open or current_time <= self.hours.regular_close:
                return MarketSession.REGULAR
            
            # 프리마켓 (18:00 ~ 23:30)
            if self.hours.pre_market_open <= current_time < self.hours.pre_market_close:
                return MarketSession.PRE_MARKET
            
            # 애프터마켓 (06:00 ~ 10:00)
            if self.hours.after_hours_open <= current_time <= self.hours.after_hours_close:
                return MarketSession.AFTER_HOURS
            
            return MarketSession.CLOSED
    
    def is_market_open(self, now: datetime = None, allow_extended: bool = False) -> bool:
        """시장 개장 여부
        
        Args:
            now: 확인할 시간 (기본: 현재)
            allow_extended: 프리마켓/애프터마켓 허용 여부 (미국만)
        """
        session = self.get_current_session(now)
        
        if session == MarketSession.REGULAR:
            return True
        
        if allow_extended and self.market == "US":
            return session in [MarketSession.PRE_MARKET, MarketSession.AFTER_HOURS]
        
        return False
    
    def get_next_open(self, now: datetime = None) -> datetime:
        """다음 장 시작 시간 반환"""
        now = now or datetime.now()
        
        # 오늘 장 시작 시간
        today_open = now.replace(
            hour=self.hours.regular_open.hour,
            minute=self.hours.regular_open.minute,
            second=0,
            microsecond=0
        )
        
        # 아직 장 시작 전이면 오늘
        if now < today_open and not self.is_weekend(now) and not self.is_holiday(now):
            return today_open
        
        # 내일부터 체크
        next_day = now + timedelta(days=1)
        for _ in range(7):  # 최대 7일 체크
            if not self.is_weekend(next_day) and not self.is_holiday(next_day):
                return next_day.replace(
                    hour=self.hours.regular_open.hour,
                    minute=self.hours.regular_open.minute,
                    second=0,
                    microsecond=0
                )
            next_day += timedelta(days=1)
        
        return today_open  # 폴백
    
    def get_time_to_open(self, now: datetime = None) -> Optional[timedelta]:
        """장 시작까지 남은 시간"""
        now = now or datetime.now()
        
        if self.is_market_open(now):
            return None  # 이미 열려있음
        
        next_open = self.get_next_open(now)
        return next_open - now
    
    def get_time_to_close(self, now: datetime = None) -> Optional[timedelta]:
        """장 종료까지 남은 시간"""
        now = now or datetime.now()
        
        if not self.is_market_open(now):
            return None  # 이미 닫혀있음
        
        today_close = now.replace(
            hour=self.hours.regular_close.hour,
            minute=self.hours.regular_close.minute,
            second=0,
            microsecond=0
        )
        
        # 미국 시장의 경우 다음날 종료
        if self.market == "US" and now.time() >= self.hours.regular_open:
            today_close += timedelta(days=1)
        
        return today_close - now
    
    def get_status_message(self, now: datetime = None) -> str:
        """현재 시장 상태 메시지"""
        now = now or datetime.now()
        session = self.get_current_session(now)
        
        market_name = "한국 시장" if self.market == "KR" else "미국 시장"
        
        if session == MarketSession.REGULAR:
            remaining = self.get_time_to_close(now)
            if remaining:
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes = remainder // 60
                return f"🟢 {market_name} 정규장 운영 중 (종료까지 {hours}시간 {minutes}분)"
            return f"🟢 {market_name} 정규장 운영 중"
        
        elif session == MarketSession.PRE_MARKET:
            return f"🟡 {market_name} 프리마켓 운영 중"
        
        elif session == MarketSession.AFTER_HOURS:
            return f"🟡 {market_name} 애프터마켓 운영 중"
        
        else:
            remaining = self.get_time_to_open(now)
            if remaining:
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes = remainder // 60
                return f"🔴 {market_name} 폐장 (개장까지 {hours}시간 {minutes}분)"
            return f"🔴 {market_name} 폐장"


# 전역 인스턴스
_kr_checker: Optional[MarketTimeChecker] = None
_us_checker: Optional[MarketTimeChecker] = None


def get_market_checker(market: str = "KR") -> MarketTimeChecker:
    """전역 MarketTimeChecker 인스턴스 반환"""
    global _kr_checker, _us_checker
    
    if market.upper() == "KR":
        if _kr_checker is None:
            _kr_checker = MarketTimeChecker("KR")
        return _kr_checker
    else:
        if _us_checker is None:
            _us_checker = MarketTimeChecker("US")
        return _us_checker

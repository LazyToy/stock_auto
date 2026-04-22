"""감사 로그(Audit Trail) 모듈

모든 주요 사용자 행동과 시스템 이벤트를 추적하고 기록합니다.
"""

import json
import os
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


class EventType(Enum):
    """이벤트 타입 열거형"""
    ORDER = "ORDER"  # 주문 (매수/매도)
    CONFIG_CHANGE = "CONFIG_CHANGE"  # 설정 변경
    STRATEGY_CHANGE = "STRATEGY_CHANGE"  # 전략 변경
    SYSTEM_START = "SYSTEM_START"  # 시스템 시작
    SYSTEM_STOP = "SYSTEM_STOP"  # 시스템 종료
    ERROR = "ERROR"  # 에러 발생
    LOGIN = "LOGIN"  # 로그인 (추후 인증 기능 추가 시)


@dataclass
class AuditEvent:
    """감사 이벤트 데이터 클래스"""
    event_type: EventType
    user: str
    action: str
    details: Dict[str, Any]
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        """초기화 후 처리 - 타임스탬프 자동 생성"""
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        
        # EventType enum을 문자열로 변환
        if isinstance(self.event_type, EventType):
            self.event_type = self.event_type.value


class AuditLogger:
    """감사 로거 클래스"""
    
    def __init__(self, log_file: str = "logs/active/audit.jsonl"):
        """
        초기화
        
        Args:
            log_file: 로그 파일 경로 (JSONL 형식)
        """
        self.log_file = log_file
        
        # 디렉토리 생성
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
    
    def log(self, event: AuditEvent):
        """
        이벤트 로깅
        
        Args:
            event: 감사 이벤트
        """
        try:
            # 이벤트를 JSONL 형식으로 저장 (한 줄에 하나의 JSON 객체)
            with open(self.log_file, 'a', encoding='utf-8') as f:
                event_dict = asdict(event)
                f.write(json.dumps(event_dict, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"[AuditLogger] Error logging event: {e}")
    
    def log_order(self, user: str, action: str, symbol: str, quantity: int, price: float):
        """
        주문 이벤트 로깅 편의 메서드
        
        Args:
            user: 사용자 식별자
            action: 행동 (BUY, SELL)
            symbol: 종목 코드
            quantity: 수량
            price: 가격
        """
        event = AuditEvent(
            event_type=EventType.ORDER,
            user=user,
            action=action,
            details={
                "symbol": symbol,
                "quantity": quantity,
                "price": price
            }
        )
        self.log(event)
    
    def log_config_change(self, user: str, key: str, old_value: Any, new_value: Any):
        """
        설정 변경 이벤트 로깅 편의 메서드
        
        Args:
            user: 사용자 식별자
            key: 설정 키
            old_value: 이전 값
            new_value: 새로운 값
        """
        event = AuditEvent(
            event_type=EventType.CONFIG_CHANGE,
            user=user,
            action="UPDATE",
            details={
                "key": key,
                "old_value": str(old_value),
                "new_value": str(new_value)
            }
        )
        self.log(event)
    
    def query(self, 
              user: Optional[str] = None,
              event_type: Optional[EventType] = None,
              start_date: Optional[str] = None,
              end_date: Optional[str] = None,
              limit: int = 1000) -> List[Dict[str, Any]]:
        """
        로그 조회
        
        Args:
            user: 사용자 필터
            event_type: 이벤트 타입 필터
            start_date: 시작 날짜 (ISO 형식)
            end_date: 종료 날짜 (ISO 형식)
            limit: 최대 반환 개수
            
        Returns:
            필터링된 이벤트 리스트
        """
        if not os.path.exists(self.log_file):
            return []
        
        results = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        event = json.loads(line)
                        
                        # 필터 적용
                        if user and event.get('user') != user:
                            continue
                        
                        if event_type:
                            event_type_str = event_type.value if isinstance(event_type, EventType) else event_type
                            if event.get('event_type') != event_type_str:
                                continue
                        
                        if start_date and event.get('timestamp', '') < start_date:
                            continue
                        
                        if end_date and event.get('timestamp', '') > end_date:
                            continue
                        
                        results.append(event)
                        
                        if len(results) >= limit:
                            break
                            
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[AuditLogger] Error querying logs: {e}")
        
        return results
    
    def apply_retention_policy(self, max_entries: int = 10000):
        """
        로그 보관 정책 적용 - 오래된 로그 삭제
        
        Args:
            max_entries: 최대 보관 항목 수
        """
        if not os.path.exists(self.log_file):
            return
        
        try:
            # 모든 로그 읽기
            all_lines = []
            with open(self.log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            # 최신 N개만 유지
            if len(all_lines) > max_entries:
                recent_lines = all_lines[-max_entries:]
                
                # 덮어쓰기
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.writelines(recent_lines)
                    
                print(f"[AuditLogger] Retention policy applied: {len(all_lines)} -> {len(recent_lines)}")
        except Exception as e:
            print(f"[AuditLogger] Error applying retention policy: {e}")


# 전역 로거 인스턴스
_global_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """전역 감사 로거 인스턴스 반환 (Singleton)"""
    global _global_logger
    if _global_logger is None:
        _global_logger = AuditLogger()
    return _global_logger

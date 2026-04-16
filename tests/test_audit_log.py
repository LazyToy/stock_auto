"""감사 로그(Audit Trail) 테스트

사용자의 모든 주요 행동(주문, 전략 변경, 설정 수정)을 추적하고 기록하는 기능을 테스트합니다.
"""

import unittest
from datetime import datetime
import os
import json
import tempfile
from src.utils.audit_log import AuditLogger, AuditEvent, EventType


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        """테스트용 임시 로그 파일 생성"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "audit_test.jsonl")
        self.logger = AuditLogger(log_file=self.log_file)
        
    def tearDown(self):
        """임시 파일 정리"""
        if os.path.exists(self.log_file):
            os.remove(self.log_file)
        os.rmdir(self.temp_dir)
        
    def test_log_order_event(self):
        """주문 이벤트 로깅 테스트"""
        event = AuditEvent(
            event_type=EventType.ORDER,
            user="test_user",
            action="BUY",
            details={
                "symbol": "005930",
                "quantity": 10,
                "price": 75000
            }
        )
        
        self.logger.log(event)
        
        # 파일에 기록되었는지 확인
        self.assertTrue(os.path.exists(self.log_file))
        
        # 내용 검증
        with open(self.log_file, 'r', encoding='utf-8') as f:
            line = f.readline()
            data = json.loads(line)
            
        self.assertEqual(data['event_type'], 'ORDER')
        self.assertEqual(data['user'], 'test_user')
        self.assertEqual(data['action'], 'BUY')
        self.assertEqual(data['details']['symbol'], '005930')
        
    def test_log_config_change(self):
        """설정 변경 이벤트 로깅 테스트"""
        event = AuditEvent(
            event_type=EventType.CONFIG_CHANGE,
            user="admin",
            action="UPDATE_STRATEGY",
            details={
                "old_strategy": "MA_CROSSOVER",
                "new_strategy": "RSI",
                "reason": "시장 변동성 증가"
            }
        )
        
        self.logger.log(event)
        
        # 검증
        with open(self.log_file, 'r', encoding='utf-8') as f:
            data = json.loads(f.readline())
            
        self.assertEqual(data['event_type'], 'CONFIG_CHANGE')
        self.assertEqual(data['details']['new_strategy'], 'RSI')
        
    def test_query_logs(self):
        """로그 조회 테스트"""
        # 여러 이벤트 로깅
        events = [
            AuditEvent(EventType.ORDER, "user1", "BUY", {"symbol": "AAPL"}),
            AuditEvent(EventType.ORDER, "user1", "SELL", {"symbol": "MSFT"}),
            AuditEvent(EventType.CONFIG_CHANGE, "admin", "UPDATE", {"key": "value"})
        ]
        
        for event in events:
            self.logger.log(event)
            
        # 특정 사용자의 로그만 조회
        user1_logs = self.logger.query(user="user1")
        self.assertEqual(len(user1_logs), 2)
        
        # 특정 이벤트 타입만 조회
        order_logs = self.logger.query(event_type=EventType.ORDER)
        self.assertEqual(len(order_logs), 2)
        
    def test_log_retention(self):
        """로그 보관 정책 테스트 (오래된 로그 삭제)"""
        # 100개의 이벤트 로깅
        for i in range(100):
            event = AuditEvent(
                EventType.ORDER,
                f"user_{i}",
                "TEST",
                {"index": i}
            )
            self.logger.log(event)
            
        # 보관 정책 적용 (최대 50개)
        self.logger.apply_retention_policy(max_entries=50)
        
        # 남은 로그 개수 확인
        all_logs = self.logger.query()
        self.assertEqual(len(all_logs), 50)
        

if __name__ == '__main__':
    unittest.main()

"""트레이딩 상태 관리 (State Manager)

Trailing Stop을 위한 High-Water Mark(최고점) 등의 상태를 로컬 파일에 저장하고 관리합니다.
"""

import json
import os
from typing import Dict, Any

class StateManager:
    def __init__(self, filename: str = "trading_state.json"):
        self.filename = filename
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """상태 파일 로드"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state: {e}")
                return {}
        return {}

    def save_state(self):
        """상태 파일 저장"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving state: {e}")

    def update_high_water_mark(self, symbol: str, current_price: float):
        """고점 갱신 (High-Water Mark)"""
        if 'high_water_marks' not in self.state:
            self.state['high_water_marks'] = {}
            
        hwm = self.state['high_water_marks'].get(symbol, 0)
        
        if current_price > hwm:
            self.state['high_water_marks'][symbol] = current_price
            self.save_state()
            return True # 갱신됨
        return False

    def get_high_water_mark(self, symbol: str) -> float:
        """고점 조회"""
        return self.state.get('high_water_marks', {}).get(symbol, 0.0)

    def clear_high_water_mark(self, symbol: str):
        """매도 후 고점 기록 삭제"""
        if 'high_water_marks' in self.state and symbol in self.state['high_water_marks']:
            del self.state['high_water_marks'][symbol]
            self.save_state()

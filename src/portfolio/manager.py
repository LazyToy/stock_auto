"""멀티 포트폴리오 관리자

여러 전략을 동시에 운영하고 전략별 성과를 추적합니다.

주요 기능:
- 전략별 독립적인 포트폴리오 관리
- 전략간 자금 배분
- 통합/개별 성과 리포트
"""

import os
import json
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class AllocationStrategy(Enum):
    """자금 배분 전략"""
    EQUAL = "equal"              # 균등 배분
    RISK_PARITY = "risk_parity"  # 위험 기반 배분
    CUSTOM = "custom"            # 사용자 정의


@dataclass
class PortfolioConfig:
    """포트폴리오 설정"""
    name: str
    strategy_name: str
    market: str = "KR"
    initial_capital: float = 10000000
    allocation_pct: float = 100.0  # 전체 자금 대비 배분 비율
    max_stocks: int = 5
    enabled: bool = True
    
    
@dataclass
class PortfolioPerformance:
    """포트폴리오 성과"""
    name: str
    strategy_name: str
    initial_capital: float = 0.0
    current_value: float = 0.0
    total_return_pct: float = 0.0
    daily_return_pct: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    peak_value: float = 0.0
    trade_count: int = 0
    last_updated: str = ""



@dataclass
class MultiPortfolio:
    """멀티 포트폴리오 상태"""
    portfolios: Dict[str, PortfolioConfig] = field(default_factory=dict)
    performances: Dict[str, PortfolioPerformance] = field(default_factory=dict)
    total_capital: float = 0.0
    allocation_strategy: AllocationStrategy = AllocationStrategy.EQUAL
    created_at: str = ""
    updated_at: str = ""


class MultiPortfolioManager:
    """멀티 포트폴리오 관리자
    
    여러 전략을 동시에 운영하고 성과를 추적합니다.
    """
    
    CONFIG_FILE = "data/multi_portfolio.json"
    
    def __init__(self, total_capital: float = 100000000):
        """초기화
        
        Args:
            total_capital: 총 운용 자금
        """
        self.state = MultiPortfolio(
            total_capital=total_capital,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # 저장된 상태 로드
        self._load_state()
        logger.info(f"멀티 포트폴리오 관리자 초기화: 총 자금 {total_capital:,.0f}원")
    
    def add_portfolio(self, config: PortfolioConfig) -> bool:
        """포트폴리오 추가
        
        Args:
            config: 포트폴리오 설정
            
        Returns:
            성공 여부
        """
        if config.name in self.state.portfolios:
            logger.warning(f"이미 존재하는 포트폴리오: {config.name}")
            return False
        
        self.state.portfolios[config.name] = config
        self.state.performances[config.name] = PortfolioPerformance(
            name=config.name,
            strategy_name=config.strategy_name,
            initial_capital=self.state.total_capital * (config.allocation_pct / 100),

            current_value=self.state.total_capital * (config.allocation_pct / 100),
            peak_value=self.state.total_capital * (config.allocation_pct / 100),
            last_updated=datetime.now().isoformat()
        )

        
        self._rebalance_allocations()
        self._save_state()
        
        logger.info(f"포트폴리오 추가: {config.name} ({config.strategy_name})")
        return True
    
    def remove_portfolio(self, name: str) -> bool:
        """포트폴리오 제거"""
        if name not in self.state.portfolios:
            return False
        
        del self.state.portfolios[name]
        if name in self.state.performances:
            del self.state.performances[name]
        
        self._rebalance_allocations()
        self._save_state()
        
        logger.info(f"포트폴리오 제거: {name}")
        return True
    
    def update_performance(self, name: str, current_value: float, 
                          trade_count: int = 0, win_rate: float = 0.0) -> bool:
        """포트폴리오 성과 업데이트
        
        Args:
            name: 포트폴리오 이름
            current_value: 현재 자산 가치
            trade_count: 거래 횟수
            win_rate: 승률
        """
        if name not in self.state.performances:
            return False
        
        perf = self.state.performances[name]
        
        # 수익률 계산
        if perf.initial_capital > 0:
            perf.total_return_pct = ((current_value - perf.initial_capital) / perf.initial_capital) * 100
        
        # 일일 수익률 (이전 값 대비)
        if perf.current_value > 0:
            perf.daily_return_pct = ((current_value - perf.current_value) / perf.current_value) * 100
        
        # MDD 및 Peak 업데이트
        if current_value > perf.peak_value:
            perf.peak_value = current_value
        
        drawdown = 0.0
        if perf.peak_value > 0:
            drawdown = (perf.peak_value - current_value) / perf.peak_value * 100
            
        if drawdown > perf.max_drawdown:
            perf.max_drawdown = drawdown

        perf.current_value = current_value
        perf.trade_count = trade_count
        perf.win_rate = win_rate
        perf.last_updated = datetime.now().isoformat()
        
        self._save_state()
        return True

    
    def get_portfolio(self, name: str) -> Optional[PortfolioConfig]:
        """포트폴리오 조회"""
        return self.state.portfolios.get(name)
    
    def get_performance(self, name: str) -> Optional[PortfolioPerformance]:
        """포트폴리오 성과 조회"""
        return self.state.performances.get(name)
    
    def get_all_performances(self) -> Dict[str, PortfolioPerformance]:
        """모든 포트폴리오 성과 조회"""
        return self.state.performances
    
    def get_aggregate_performance(self) -> Dict[str, Any]:
        """통합 성과 조회"""
        if not self.state.performances:
            return {}
        
        total_initial = sum(p.initial_capital for p in self.state.performances.values())
        total_current = sum(p.current_value for p in self.state.performances.values())
        
        total_return_pct = 0
        if total_initial > 0:
            total_return_pct = ((total_current - total_initial) / total_initial) * 100
        
        avg_win_rate = sum(p.win_rate for p in self.state.performances.values()) / len(self.state.performances)
        total_trades = sum(p.trade_count for p in self.state.performances.values())
        
        # 최고/최저 성과 포트폴리오
        best = max(self.state.performances.values(), key=lambda p: p.total_return_pct)
        worst = min(self.state.performances.values(), key=lambda p: p.total_return_pct)
        
        return {
            "total_initial_capital": total_initial,
            "total_current_value": total_current,
            "total_return_pct": total_return_pct,
            "avg_win_rate": avg_win_rate,
            "total_trades": total_trades,
            "portfolio_count": len(self.state.performances),
            "best_portfolio": {
                "name": best.name,
                "strategy": best.strategy_name,
                "return_pct": best.total_return_pct
            },
            "worst_portfolio": {
                "name": worst.name,
                "strategy": worst.strategy_name,
                "return_pct": worst.total_return_pct
            }
        }
    
    def get_comparison_table(self) -> List[Dict]:
        """전략 비교 테이블"""
        result = []
        for perf in self.state.performances.values():
            result.append({
                "name": perf.name,
                "strategy": perf.strategy_name,
                "initial": perf.initial_capital,
                "current": perf.current_value,
                "return_pct": perf.total_return_pct,
                "daily_pct": perf.daily_return_pct,
                "win_rate": perf.win_rate,
                "trades": perf.trade_count
            })
        
        # 수익률 순 정렬
        result.sort(key=lambda x: x["return_pct"], reverse=True)
        return result
    
    def _rebalance_allocations(self):
        """배분 비율 재조정"""
        enabled_portfolios = [p for p in self.state.portfolios.values() if p.enabled]
        
        if not enabled_portfolios:
            return
        
        if self.state.allocation_strategy == AllocationStrategy.EQUAL:
            # 균등 배분
            equal_pct = 100.0 / len(enabled_portfolios)
            for p in enabled_portfolios:
                p.allocation_pct = equal_pct

        elif self.state.allocation_strategy == AllocationStrategy.RISK_PARITY:
            # 위험 기반 배분 (Inverse Max Drawdown)
            # MDD가 낮을수록 더 많은 자금 배분
            total_inverse_risk = 0.0
            weights = {}
            epsilon = 1.0 # 0 나누기 방지 및 기본 위험 보정 (1%)

            for name in self.state.performances:
                perf = self.state.performances[name]
                # 위험 지표: MDD (없으면 0)
                risk = perf.max_drawdown
                
                # 역수 가중치 (위험이 0이면 최대 가중치 100)
                weight = 1.0 / (risk + epsilon)
                weights[name] = weight
                total_inverse_risk += weight
            
            # 정규화하여 배분
            if total_inverse_risk > 0:
                for p in enabled_portfolios:
                    w = weights.get(p.name, 0)
                    p.allocation_pct = (w / total_inverse_risk) * 100.0
            else:
                # 예외 시 균등 배분
                equal_pct = 100.0 / len(enabled_portfolios)
                for p in enabled_portfolios:
                    p.allocation_pct = equal_pct

    
    def _load_state(self):
        """상태 로드"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # PortfolioConfig 복원
                for name, config_dict in data.get('portfolios', {}).items():
                    self.state.portfolios[name] = PortfolioConfig(**config_dict)
                
                # PortfolioPerformance 복원
                for name, perf_dict in data.get('performances', {}).items():
                    self.state.performances[name] = PortfolioPerformance(**perf_dict)
                
                self.state.total_capital = data.get('total_capital', self.state.total_capital)
                self.state.allocation_strategy = AllocationStrategy(
                    data.get('allocation_strategy', 'equal')
                )
                
                logger.info(f"멀티 포트폴리오 상태 로드: {len(self.state.portfolios)}개")
                
            except Exception as e:
                logger.warning(f"상태 로드 실패: {e}")
    
    def _save_state(self):
        """상태 저장"""
        try:
            os.makedirs(os.path.dirname(self.CONFIG_FILE) if os.path.dirname(self.CONFIG_FILE) else ".", exist_ok=True)
            
            data = {
                'portfolios': {k: asdict(v) for k, v in self.state.portfolios.items()},
                'performances': {k: asdict(v) for k, v in self.state.performances.items()},
                'total_capital': self.state.total_capital,
                'allocation_strategy': self.state.allocation_strategy.value,
                'updated_at': datetime.now().isoformat()
            }
            
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")
    
    def generate_report(self) -> str:
        """성과 리포트 생성"""
        agg = self.get_aggregate_performance()
        comparison = self.get_comparison_table()
        
        if not agg:
            return "등록된 포트폴리오가 없습니다."
        
        report = f"""
📊 멀티 포트폴리오 성과 리포트
{'='*50}

💰 통합 성과
• 총 초기 자금: {agg['total_initial_capital']:,.0f}원
• 현재 평가금: {agg['total_current_value']:,.0f}원
• 총 수익률: {agg['total_return_pct']:+.2f}%
• 평균 승률: {agg['avg_win_rate']:.1f}%
• 총 거래 횟수: {agg['total_trades']}건
• 포트폴리오 수: {agg['portfolio_count']}개

🏆 최고 성과: {agg['best_portfolio']['name']} ({agg['best_portfolio']['strategy']}) +{agg['best_portfolio']['return_pct']:.2f}%
📉 최저 성과: {agg['worst_portfolio']['name']} ({agg['worst_portfolio']['strategy']}) {agg['worst_portfolio']['return_pct']:+.2f}%

{'='*50}
전략별 상세 성과
{'='*50}
"""
        
        for i, row in enumerate(comparison, 1):
            report += f"""
{i}. {row['name']} ({row['strategy']})
   수익률: {row['return_pct']:+.2f}% | 일일: {row['daily_pct']:+.2f}%
   현재 자산: {row['current']:,.0f}원 | 거래: {row['trades']}건
"""
        
        return report


# 전역 인스턴스
_manager_instance: Optional[MultiPortfolioManager] = None


def get_multi_portfolio_manager(total_capital: float = 100000000) -> MultiPortfolioManager:
    """전역 MultiPortfolioManager 인스턴스 반환"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MultiPortfolioManager(total_capital)
    return _manager_instance

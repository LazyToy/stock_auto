"""설정 로더 유틸리티

YAML 설정 파일을 로드하고 관리합니다.

사용 예시:
    from src.utils.config_loader import ConfigLoader, get_config
    
    # 전체 설정 로드
    config = get_config()
    
    # 특정 섹션 조회
    rsi_config = config.get_strategy('rsi')
    trading_config = config.get_trading()
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """설정 관련 에러"""
    pass


@dataclass
class StrategyConfig:
    """전략 설정 래퍼"""
    name: str
    params: Dict[str, Any]
    
    def get(self, key: str, default: Any = None) -> Any:
        """파라미터 조회"""
        return self.params.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        return self.params[key]


class ConfigLoader:
    """설정 로더
    
    YAML 설정 파일을 로드하고 캐싱합니다.
    """
    
    DEFAULT_CONFIG_DIR = "config"
    
    def __init__(self, config_dir: Optional[str] = None):
        """초기화
        
        Args:
            config_dir: 설정 디렉토리 경로
        """
        self.config_dir = Path(config_dir or self.DEFAULT_CONFIG_DIR)
        self._strategies_cache: Optional[Dict] = None
        self._trading_cache: Optional[Dict] = None
        
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """YAML 파일 로드"""
        filepath = self.config_dir / filename
        
        if not filepath.exists():
            logger.warning(f"설정 파일 없음: {filepath}")
            return {}
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            logger.info(f"설정 로드: {filepath}")
            return data or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML 파싱 에러 ({filepath}): {e}")
        except Exception as e:
            raise ConfigError(f"설정 로드 실패 ({filepath}): {e}")
    
    def load_strategies(self, force_reload: bool = False) -> Dict[str, Any]:
        """전략 설정 로드
        
        Args:
            force_reload: 캐시 무시하고 다시 로드
        """
        if self._strategies_cache is None or force_reload:
            self._strategies_cache = self._load_yaml("strategies.yaml")
        return self._strategies_cache
    
    def load_trading(self, force_reload: bool = False) -> Dict[str, Any]:
        """거래 설정 로드
        
        Args:
            force_reload: 캐시 무시하고 다시 로드
        """
        if self._trading_cache is None or force_reload:
            self._trading_cache = self._load_yaml("trading.yaml")
        return self._trading_cache
    
    def get_strategy(self, name: str) -> StrategyConfig:
        """특정 전략 설정 조회
        
        Args:
            name: 전략 이름 (예: 'rsi', 'macd', 'ml.random_forest')
        
        Returns:
            StrategyConfig 객체
        """
        strategies = self.load_strategies()
        
        # 점으로 구분된 경로 지원 (예: 'ml.random_forest')
        keys = name.split('.')
        config = strategies
        
        for key in keys:
            if not isinstance(config, dict):
                raise ConfigError(f"잘못된 설정 경로: {name}")
            config = config.get(key)
            if config is None:
                raise ConfigError(f"전략 설정 없음: {name}")
        
        return StrategyConfig(name=name, params=config)
    
    def get_trading(self, section: Optional[str] = None) -> Dict[str, Any]:
        """거래 설정 조회
        
        Args:
            section: 섹션 이름 (예: 'risk', 'circuit_breaker')
        """
        trading = self.load_trading()
        
        if section is None:
            return trading
        
        if section not in trading:
            raise ConfigError(f"거래 설정 섹션 없음: {section}")
        
        return trading[section]
    
    def get_risk_config(self) -> Dict[str, Any]:
        """리스크 설정 조회"""
        return self.get_trading('risk')
    
    def get_circuit_breaker_config(self) -> Dict[str, Any]:
        """Circuit Breaker 설정 조회"""
        return self.get_trading('circuit_breaker')
    
    def get_market_config(self, market: str = "korea") -> Dict[str, Any]:
        """시장 설정 조회"""
        markets = self.get_trading('markets')
        if market not in markets:
            raise ConfigError(f"시장 설정 없음: {market}")
        return markets[market]
    
    def get_symbols(self, market: str = "korea") -> list:
        """감시 종목 목록 조회"""
        symbols = self.get_trading('symbols')
        if market not in symbols:
            return []
        return symbols[market].get('watchlist', [])
    
    def get_notification_config(self) -> Dict[str, Any]:
        """알림 설정 조회"""
        return self.get_trading('notifications')
    
    def get_backtest_config(self) -> Dict[str, Any]:
        """백테스팅 설정 조회"""
        return self.get_trading('backtest')
    
    def get_ml_config(self, model: str = "random_forest") -> StrategyConfig:
        """ML 모델 설정 조회"""
        return self.get_strategy(f"ml.{model}")
    
    def get_rl_config(self, agent: str = "dqn") -> StrategyConfig:
        """RL 에이전트 설정 조회"""
        return self.get_strategy(f"reinforcement_learning.{agent}")
    
    def get_exit_config(self, strategy: str = "fixed") -> StrategyConfig:
        """Exit 전략 설정 조회"""
        return self.get_strategy(f"exit.{strategy}")
    
    def reload(self):
        """모든 설정 다시 로드"""
        self._strategies_cache = None
        self._trading_cache = None
        self.load_strategies()
        self.load_trading()
        logger.info("설정 리로드 완료")
    
    def validate(self) -> bool:
        """설정 유효성 검사"""
        try:
            # 필수 설정 확인
            strategies = self.load_strategies()
            trading = self.load_trading()
            
            # 필수 섹션 확인
            required_trading_sections = ['trading', 'risk', 'backtest']
            for section in required_trading_sections:
                if section not in trading:
                    logger.error(f"필수 설정 섹션 누락: {section}")
                    return False
            
            logger.info("설정 유효성 검사 통과")
            return True
        except Exception as e:
            logger.error(f"설정 유효성 검사 실패: {e}")
            return False


# 전역 인스턴스
_config_instance: Optional[ConfigLoader] = None


def get_config(config_dir: Optional[str] = None) -> ConfigLoader:
    """전역 ConfigLoader 인스턴스 반환
    
    싱글톤 패턴으로 ConfigLoader를 관리합니다.
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = ConfigLoader(config_dir)
    
    return _config_instance


def reload_config():
    """설정 리로드"""
    global _config_instance
    if _config_instance:
        _config_instance.reload()


# 편의 함수들
def get_strategy_config(name: str) -> StrategyConfig:
    """전략 설정 조회 편의 함수"""
    return get_config().get_strategy(name)


def get_trading_config(section: Optional[str] = None) -> Dict[str, Any]:
    """거래 설정 조회 편의 함수"""
    return get_config().get_trading(section)

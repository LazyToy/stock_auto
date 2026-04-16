"""
중앙 로깅 설정 모듈

프로젝트 전체에서 일관된 로깅 형식을 사용하도록 설정합니다.
파일 로그와 콘솔 로그를 동시에 지원하며, 로그 파일 자동 회전(Rotating) 기능을 제공합니다.
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

from src.utils.runtime_logging import ACTIVE_LOG_DIR_NAME, LOG_ROOT_DIR_NAME

# 싱글톤 패턴으로 로거 설정 상태 관리
_LOGGING_INITIALIZED = False

def setup_logging(
    name: str = "StockAuto", 
    log_dir: str = f"{LOG_ROOT_DIR_NAME}/{ACTIVE_LOG_DIR_NAME}", 
    level: int = logging.INFO,
    retention_days: int = 30
) -> logging.Logger:
    """
    중앙 로깅 설정
    
    Args:
        name: 로거 이름 (루트 로거 이름)
        log_dir: 로그 파일 저장 디렉토리
        level: 로그 레벨 (logging.INFO, logging.DEBUG 등)
        retention_days: 로그 파일 보관 기간
        
    Returns:
        logging.Logger: 설정된 로거 객체
    """
    global _LOGGING_INITIALIZED
    
    # 디렉토리 생성
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 기본 포맷
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 중복 핸들러 추가 방지
    if _LOGGING_INITIALIZED:
        return logging.getLogger(name)
        
    # 1. 콘솔 핸들러 (표준 출력)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # 2. 파일 핸들러 (TimedRotatingFileHandler) - 매일 자정 로그 회전
    today = datetime.now().strftime("%Y-%m-%d")
    filename = log_path / f"stock_auto_{today}.log"
    
    try:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=filename,
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except OSError as e:
        root_logger.warning(f"Timed log file handler disabled: {e}")
    
    # 3. 에러 전용 파일 핸들러
    error_filename = log_path / "error.log"
    try:
        error_handler = logging.handlers.RotatingFileHandler(
            filename=error_filename,
            maxBytes=10*1024*1024, # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)
    except OSError as e:
        root_logger.warning(f"Error log file handler disabled: {e}")
    
    logging.info(f"Logging initialized. Level: {logging.getLevelName(level)}, Log Dir: {log_dir}")
    _LOGGING_INITIALIZED = True
    
    return logging.getLogger(name)

def get_logger(name: str) -> logging.Logger:
    """
    모듈별 로거 획득 래퍼 함수
    """
    return logging.getLogger(name)

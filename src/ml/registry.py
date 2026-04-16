"""
ML Model Registry

모델의 버전 관리, 메타데이터 저장, 로드 기능을 제공합니다.
mlflow 등의 외부 도구 없이 경량화된 JSON 기반 레지스트리를 구현했습니다.
"""

import os
import json
import joblib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

class ModelRegistry:
    def __init__(self, base_dir: str = "models"):
        """
        모델 레지스트리 초기화
        
        Args:
            base_dir: 모델과 메타데이터가 저장될 기본 디렉토리
        """
        self.base_dir = Path(base_dir)
        self.registry_path = self.base_dir / "registry.json"
        self._ensure_directories()
        self.registry = self._load_registry()

    def _ensure_directories(self):
        """필요한 디렉토리 생성"""
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True)

    def _load_registry(self) -> Dict:
        """레지스트리 파일 로드"""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                return {"models": {}}
        return {"models": {}}

    def _save_registry(self):
        """레지스트리 파일 저장"""
        try:
            with open(self.registry_path, 'w', encoding='utf-8') as f:
                json.dump(self.registry, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")

    def register_model(self, 
                      model_name: str, 
                      model: Any, 
                      metrics: Dict[str, float], 
                      params: Dict[str, Any],
                      description: str = "") -> str:
        """
        모델을 저장하고 레지스트리에 등록
        
        Args:
            model_name: 모델 이름 (예: 'RandomForest_KR')
            model: 학습된 모델 객체 (joblib으로 저장 가능한 객체)
            metrics: 평가 지표 (accuracy, f1 등)
            params: 하이퍼파라미터
            description: 모델 설명
            
        Returns:
            version: 생성된 버전 ID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = f"v_{timestamp}"
        
        # 모델 저장 경로
        model_filename = f"{model_name}_{version}.pkl"
        model_path = self.base_dir / model_filename
        
        try:
            # 모델 파일 저장
            joblib.dump(model, model_path)
            
            # 레지스트리 업데이트
            if model_name not in self.registry["models"]:
                self.registry["models"][model_name] = []
            
            model_info = {
                "version": version,
                "path": str(model_path),
                "metrics": metrics,
                "params": params,
                "description": description,
                "created_at": datetime.now().isoformat()
            }
            
            # 리스트 앞쪽에 최신 버전 추가
            self.registry["models"][model_name].insert(0, model_info)
            self._save_registry()
            
            logger.info(f"Model registered: {model_name} (version: {version})")
            return version
            
        except Exception as e:
            logger.error(f"Failed to register model {model_name}: {e}")
            raise

    def get_model(self, model_name: str, version: str = None) -> Any:
        """
        모델 로드
        
        Args:
            model_name: 모델 이름
            version: 버전 (None이면 최신 버전)
            
        Returns:
            model: 로드된 모델 객체
        """
        if model_name not in self.registry["models"]:
            raise ValueError(f"Model not found: {model_name}")
        
        models = self.registry["models"][model_name]
        if not models:
            raise ValueError(f"No versions found for model: {model_name}")
        
        target_model_info = None
        if version:
            for m in models:
                if m["version"] == version:
                    target_model_info = m
                    break
            if not target_model_info:
                raise ValueError(f"Version {version} not found for model {model_name}")
        else:
            # 최신 버전 (0번 인덱스)
            target_model_info = models[0]
            
        try:
            model_path = target_model_info["path"]
            return joblib.load(model_path)
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            raise

    def list_models(self) -> Dict:
        """등록된 모든 모델 정보 반환"""
        return self.registry["models"]

    def get_best_model(self, model_name: str, metric: str = "accuracy") -> Any:
        """
        특정 메트릭 기준 최고 성능 모델 로드
        """
        if model_name not in self.registry["models"]:
            raise ValueError(f"Model not found: {model_name}")
            
        models = self.registry["models"][model_name]
        if not models:
            raise ValueError(f"No versions found for model: {model_name}")
            
        # 메트릭 기준으로 정렬 (내림차순 가정)
        sorted_models = sorted(models, key=lambda x: x["metrics"].get(metric, 0), reverse=True)
        best_model_info = sorted_models[0]
        
        logger.info(f"Best model selected: {model_name} version {best_model_info['version']} ({metric}={best_model_info['metrics'].get(metric)})")
        
        return self.get_model(model_name, version=best_model_info["version"])

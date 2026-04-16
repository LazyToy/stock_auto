import mlflow
import os
import joblib
from typing import Any, Dict, Optional
import logging

class MLflowManager:
    """
    MLflow를 사용하여 실험을 추적하고 모델을 관리하는 클래스.
    로컬 파일 시스템(./mlruns)을 백엔드로 사용합니다.
    """
    
    def __init__(self, experiment_name: str = "stock_auto_experiment"):
        self.logger = logging.getLogger(__name__)
        self.experiment_name = experiment_name
        
        # Set Tracking URI to local directory
        self.tracking_uri = os.path.join(os.getcwd(), "mlruns")
        mlflow.set_tracking_uri(f"file:///{self.tracking_uri}")
        
        try:
            # Create or set experiment
            if not mlflow.get_experiment_by_name(experiment_name):
                mlflow.create_experiment(experiment_name)
            mlflow.set_experiment(experiment_name)
            self.logger.info(f"MLflow initialized. Tracking URI: {self.tracking_uri}")
        except Exception as e:
            self.logger.error(f"Failed to initialize MLflow: {e}")

    def start_run(self, run_name: Optional[str] = None):
        """새로운 MLflow 실행을 시작합니다."""
        return mlflow.start_run(run_name=run_name)

    def end_run(self):
        """현재 실행을 종료합니다."""
        mlflow.end_run()

    def log_params(self, params: Dict[str, Any]):
        """파라미터를 기록합니다."""
        try:
            mlflow.log_params(params)
        except Exception as e:
            self.logger.error(f"Failed to log params: {e}")

    def log_metrics(self, metrics: Dict[str, float], step: Optional[int] = None):
        """메트릭을 기록합니다."""
        try:
            mlflow.log_metrics(metrics, step=step)
        except Exception as e:
            self.logger.error(f"Failed to log metrics: {e}")

    def log_model(self, model: Any, artifact_path: str = "model"):
        """
        모델을 기록합니다.
        Scikit-learn 모델인 경우 mlflow.sklearn 사용, 그 외에는 joblib으로 저장 후 아티팩트로 기록.
        """
        try:
            if hasattr(model, "predict"): # Simple check for sklearn-like models
                mlflow.sklearn.log_model(model, artifact_path)
            else:
                # Custom artifacts
                local_path = "temp_model.pkl"
                joblib.dump(model, local_path)
                mlflow.log_artifact(local_path, artifact_path)
                os.remove(local_path)
            self.logger.info(f"Model logged to {artifact_path}")
        except Exception as e:
            self.logger.error(f"Failed to log model: {e}")

    def load_model(self, run_id: str, artifact_path: str = "model"):
        """기록된 모델을 로드합니다."""
        try:
            model_uri = f"runs:/{run_id}/{artifact_path}"
            return mlflow.sklearn.load_model(model_uri)
        except Exception as e:
            self.logger.error(f"Failed to load model from {run_id}: {e}")
            return None

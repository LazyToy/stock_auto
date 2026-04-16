"""강화학습 전략 테스트

TDD: 강화학습 기반 트레이딩 환경 및 에이전트를 테스트합니다.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import tempfile

# 라이브러리 체크
try:
    import gymnasium as gym
    GYM_AVAILABLE = True
except ImportError:
    try:
        import gym
        GYM_AVAILABLE = True
    except ImportError:
        GYM_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from stable_baselines3 import PPO
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False


@pytest.fixture
def sample_ohlcv_data():
    """RL 학습에 충분한 샘플 OHLCV 데이터 (100일)"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    # 추세가 있는 가격 데이터 생성
    base_price = 50000
    trend = np.cumsum(np.random.randn(100) * 500)
    noise = np.random.randn(100) * 200
    
    close = base_price + trend + noise
    high = close + np.abs(np.random.randn(100) * 300)
    low = close - np.abs(np.random.randn(100) * 300)
    open_price = (high + low) / 2 + np.random.randn(100) * 100
    volume = np.random.randint(100000, 1000000, 100)
    
    return pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })


class TestRLTradeResult:
    """RLTradeResult 데이터클래스 테스트"""
    
    def test_result_creation(self):
        """RLTradeResult 생성 테스트"""
        from src.ml.rl_strategy import RLTradeResult
        
        result = RLTradeResult(
            total_reward=100.0,
            total_return=5.5,
            num_trades=10,
            win_rate=60.0,
            sharpe_ratio=1.5,
            max_drawdown=8.0,
            final_capital=10550000
        )
        
        assert result.total_reward == 100.0
        assert result.total_return == 5.5
        assert result.num_trades == 10
        assert result.win_rate == 60.0
        assert result.sharpe_ratio == 1.5
        assert result.max_drawdown == 8.0
        assert result.episode == 0


class TestTradingEnvironment:
    """트레이딩 환경 테스트"""
    
    def test_environment_creation(self, sample_ohlcv_data):
        """환경 생성 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(
            df=sample_ohlcv_data,
            initial_capital=10_000_000,
            commission_rate=0.00015,
            window_size=20
        )
        
        assert env.initial_capital == 10_000_000
        assert env.commission_rate == 0.00015
        assert env.window_size == 20
        assert env.action_space_n == 3  # 홀드, 매수, 매도
    
    def test_environment_reset(self, sample_ohlcv_data):
        """환경 초기화 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        obs, info = env.reset()
        
        # 관찰 형태 확인
        assert obs.shape == env.observation_space_shape
        assert env.capital == env.initial_capital
        assert env.position == 0.0
        assert env.total_trades == 0
    
    def test_environment_step_hold(self, sample_ohlcv_data):
        """홀드 액션 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        # 홀드 (포지션 없이)
        obs, reward, done, truncated, info = env.step(0)
        
        assert obs.shape == env.observation_space_shape
        assert env.position == 0.0
        assert info['action'] == 0
    
    def test_environment_step_buy(self, sample_ohlcv_data):
        """매수 액션 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        # 매수
        obs, reward, done, truncated, info = env.step(1)
        
        assert env.position > 0
        assert env.position_price > 0
        assert env.total_trades == 1
        assert info['trade'] == 'BUY'
    
    def test_environment_step_sell(self, sample_ohlcv_data):
        """매도 액션 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        # 매수 후 매도
        env.step(1)  # 매수
        obs, reward, done, truncated, info = env.step(2)  # 매도
        
        assert env.position == 0
        assert 'trade_return' in info
        assert info['trade'] == 'SELL'
    
    def test_environment_step_invalid_sell(self, sample_ohlcv_data):
        """포지션 없이 매도 시도 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        # 포지션 없이 매도 시도
        obs, reward, done, truncated, info = env.step(2)
        
        assert env.position == 0.0
        assert 'trade' not in info  # 거래 발생 안함
    
    def test_environment_done_condition(self, sample_ohlcv_data):
        """종료 조건 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        done = False
        steps = 0
        max_steps = len(sample_ohlcv_data) + 100
        
        while not done and steps < max_steps:
            _, _, done, _, _ = env.step(0)  # 계속 홀드
            steps += 1
        
        assert done  # 종료되어야 함
    
    def test_get_result(self, sample_ohlcv_data):
        """결과 조회 테스트"""
        from src.ml.rl_strategy import TradingEnvironment, RLTradeResult
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        # 몇 번의 거래 수행
        env.step(1)  # 매수
        for _ in range(5):
            env.step(0)  # 홀드
        env.step(2)  # 매도
        
        result = env.get_result()
        
        assert isinstance(result, RLTradeResult)
        assert result.num_trades >= 1
        assert isinstance(result.total_return, float)
        assert isinstance(result.win_rate, float)
    
    def test_observation_shape(self, sample_ohlcv_data):
        """관찰 형태 확인 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        window_size = 15
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=window_size)
        obs, _ = env.reset()
        
        # (window_size, n_features + 2) 형태 확인
        assert obs.shape[0] == window_size
        assert obs.shape[1] == env.n_features + 2  # 피처 + 포지션 + 미실현손익
    
    def test_unrealized_pnl(self, sample_ohlcv_data):
        """미실현 손익 계산 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        env.reset()
        
        # 포지션 없을 때
        assert env._get_unrealized_pnl() == 0.0
        
        # 매수 후
        env.step(1)
        # 미실현 손익이 계산되어야 함 (0이 아닐 수 있음)
        pnl = env._get_unrealized_pnl()
        assert isinstance(pnl, float)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch 미설치")
class TestDQNNetwork:
    """DQN 네트워크 테스트"""
    
    def test_network_creation(self):
        """네트워크 생성 테스트"""
        from src.ml.rl_strategy import DQNNetwork
        
        input_shape = (20, 10)
        n_actions = 3
        
        network = DQNNetwork(input_shape, n_actions)
        
        # 입력 테스트
        sample_input = torch.randn(1, 20, 10)
        output = network(sample_input)
        
        assert output.shape == (1, 3)
    
    def test_network_forward(self):
        """순전파 테스트"""
        from src.ml.rl_strategy import DQNNetwork
        
        network = DQNNetwork((20, 10), 3)
        
        # 배치 입력
        batch_input = torch.randn(32, 20, 10)
        output = network(batch_input)
        
        assert output.shape == (32, 3)
        assert not torch.isnan(output).any()


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch 미설치")
class TestDQNAgent:
    """DQN 에이전트 테스트"""
    
    @pytest.fixture
    def dqn_agent(self):
        """DQN 에이전트 픽스처"""
        from src.ml.rl_strategy import DQNAgent
        
        return DQNAgent(
            state_shape=(20, 10),
            n_actions=3,
            learning_rate=0.001,
            epsilon_start=1.0,
            epsilon_end=0.01,
            epsilon_decay=0.995,
            batch_size=16,
            memory_size=1000
        )
    
    def test_agent_creation(self, dqn_agent):
        """에이전트 생성 테스트"""
        assert dqn_agent.state_shape == (20, 10)
        assert dqn_agent.n_actions == 3
        assert dqn_agent.epsilon == 1.0
        assert len(dqn_agent.memory) == 0
    
    def test_select_action_training(self, dqn_agent):
        """학습 모드 행동 선택 테스트"""
        state = np.random.randn(20, 10).astype(np.float32)
        
        # epsilon=1.0이므로 항상 랜덤
        actions = [dqn_agent.select_action(state, training=True) for _ in range(10)]
        
        assert all(a in [0, 1, 2] for a in actions)
    
    def test_select_action_evaluation(self, dqn_agent):
        """평가 모드 행동 선택 테스트"""
        dqn_agent.epsilon = 0.0  # 탐험 없음
        state = np.random.randn(20, 10).astype(np.float32)
        
        action = dqn_agent.select_action(state, training=False)
        
        assert action in [0, 1, 2]
    
    def test_store_transition(self, dqn_agent):
        """경험 저장 테스트"""
        state = np.random.randn(20, 10).astype(np.float32)
        next_state = np.random.randn(20, 10).astype(np.float32)
        
        dqn_agent.store_transition(state, 1, 0.5, next_state, False)
        
        assert len(dqn_agent.memory) == 1
    
    def test_train_step_insufficient_memory(self, dqn_agent):
        """메모리 부족 시 학습 스킵 테스트"""
        loss = dqn_agent.train_step()
        
        assert loss == 0.0  # 배치 크기 미달
    
    def test_train_step_with_data(self, dqn_agent):
        """충분한 데이터로 학습 테스트"""
        # 메모리 채우기
        for _ in range(50):
            state = np.random.randn(20, 10).astype(np.float32)
            next_state = np.random.randn(20, 10).astype(np.float32)
            dqn_agent.store_transition(state, np.random.randint(3), 
                                       np.random.randn(), next_state, False)
        
        loss = dqn_agent.train_step()
        
        assert loss >= 0.0  # 손실 계산됨
    
    def test_save_load(self, dqn_agent):
        """모델 저장/로드 테스트"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_model.pth")
            
            # 저장
            dqn_agent.save(filepath)
            assert os.path.exists(filepath)
            
            # 로드
            dqn_agent.epsilon = 0.5  # 변경
            dqn_agent.load(filepath)
            
            # epsilon 복원 확인
            assert dqn_agent.epsilon == 1.0  # 저장 시점 값


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch 미설치")
class TestRLTrainer:
    """RL 트레이너 테스트"""
    
    def test_trainer_creation_dqn(self, sample_ohlcv_data):
        """DQN 트레이너 생성 테스트"""
        from src.ml.rl_strategy import TradingEnvironment, RLTrainer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
            trainer = RLTrainer(env=env, agent_type="DQN", save_dir=tmpdir)
            
            assert trainer.agent_type == "DQN"
            assert trainer.agent is not None
    
    def test_train_short(self, sample_ohlcv_data):
        """짧은 학습 테스트"""
        from src.ml.rl_strategy import TradingEnvironment, RLTrainer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
            trainer = RLTrainer(env=env, agent_type="DQN", save_dir=tmpdir)
            
            results = trainer.train(n_episodes=2)
            
            assert len(results) == 2
            assert all(hasattr(r, 'total_return') for r in results)
    
    def test_evaluate(self, sample_ohlcv_data):
        """평가 테스트"""
        from src.ml.rl_strategy import TradingEnvironment, RLTrainer, RLTradeResult
        
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
            trainer = RLTrainer(env=env, agent_type="DQN", save_dir=tmpdir)
            
            # 약간의 학습
            trainer.train(n_episodes=1)
            
            # 평가
            result = trainer.evaluate(n_episodes=2)
            
            assert isinstance(result, RLTradeResult)
            assert isinstance(result.total_return, float)
    
    def test_save_load_model(self, sample_ohlcv_data):
        """모델 저장/로드 테스트"""
        from src.ml.rl_strategy import TradingEnvironment, RLTrainer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
            trainer = RLTrainer(env=env, agent_type="DQN", save_dir=tmpdir)
            
            # 학습
            trainer.train(n_episodes=1)
            
            # 저장
            trainer.save_model("test_rl")
            assert os.path.exists(os.path.join(tmpdir, "test_rl.pth"))
            
            # 로드
            trainer.load_model("test_rl")
    
    def test_invalid_agent_type(self, sample_ohlcv_data):
        """잘못된 에이전트 타입 테스트"""
        from src.ml.rl_strategy import TradingEnvironment, RLTrainer
        
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
            
            with pytest.raises(ValueError):
                RLTrainer(env=env, agent_type="INVALID", save_dir=tmpdir)


class TestFeaturePreparation:
    """피처 준비 테스트"""
    
    def test_feature_columns(self, sample_ohlcv_data):
        """피처 컬럼 생성 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        
        expected_features = [
            'return', 'ma_5_ratio', 'ma_10_ratio', 'ma_20_ratio',
            'rsi_normalized', 'bb_position', 'volume_ratio', 'atr_ratio'
        ]
        
        assert set(env.feature_columns) == set(expected_features)
    
    def test_features_no_nan(self, sample_ohlcv_data):
        """피처에 NaN 없음 테스트"""
        from src.ml.rl_strategy import TradingEnvironment
        
        env = TradingEnvironment(df=sample_ohlcv_data, window_size=10)
        
        assert not np.isnan(env.features).any()

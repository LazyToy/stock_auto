"""강화학습 기반 매매 전략

DQN, PPO 등 강화학습 알고리즘을 활용한 자동 매매 에이전트.

주요 기능:
- 트레이딩 환경 (Gym 호환)
- DQN 에이전트
- PPO 에이전트 (Stable-Baselines3)
- 학습 및 평가
"""

import numpy as np
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
from collections import deque
import random
import os
import json

logger = logging.getLogger(__name__)

# Gym 체크
try:
    import gymnasium as gym
    from gymnasium import spaces
    GYM_AVAILABLE = True
except ImportError:
    try:
        import gym
        from gym import spaces
        GYM_AVAILABLE = True
    except ImportError:
        GYM_AVAILABLE = False

# PyTorch 체크
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Stable-Baselines3 체크
try:
    from stable_baselines3 import PPO, A2C, DQN as SB3_DQN
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import EvalCallback
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False


@dataclass
class RLTradeResult:
    """강화학습 거래 결과"""
    total_reward: float
    total_return: float
    num_trades: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    final_capital: float
    episode: int = 0


class TradingEnvironment:
    """트레이딩 환경 (Gym 호환)
    
    상태: 기술적 지표 + 포지션 정보
    행동: 0(홀드), 1(매수), 2(매도)
    보상: 수익률 기반
    """
    
    def __init__(
        self,
        df: pd.DataFrame,
        initial_capital: float = 10_000_000,
        commission_rate: float = 0.00015,
        window_size: int = 20,
        max_position: float = 1.0
    ):
        """초기화
        
        Args:
            df: OHLCV 데이터
            initial_capital: 초기 자본
            commission_rate: 수수료율
            window_size: 관찰 윈도우
            max_position: 최대 포지션 비율
        """
        self.df = df.reset_index(drop=True)
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.window_size = window_size
        self.max_position = max_position
        
        # 피처 생성
        self._prepare_features()
        
        # 상태/행동 공간
        self.n_features = len(self.feature_columns)
        self.observation_space_shape = (self.window_size, self.n_features + 2)  # +2: 포지션, 수익률
        self.action_space_n = 3  # 홀드, 매수, 매도
        
        # Gym 호환
        if GYM_AVAILABLE:
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, 
                shape=self.observation_space_shape,
                dtype=np.float32
            )
            self.action_space = spaces.Discrete(self.action_space_n)
        
        self.reset()
    
    def _prepare_features(self):
        """기술적 지표 피처 생성"""
        df = self.df.copy()
        
        # 수익률
        df['return'] = df['close'].pct_change()
        
        # 이동평균 비율
        for period in [5, 10, 20]:
            ma = df['close'].rolling(window=period).mean()
            df[f'ma_{period}_ratio'] = df['close'] / ma - 1
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi_normalized'] = (df['rsi'] - 50) / 50  # -1 ~ 1 정규화
        
        # 볼린저밴드 위치
        bb_mid = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_position'] = (df['close'] - bb_mid) / (2 * bb_std + 1e-10)
        
        # 거래량 비율
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(window=10).mean() - 1
        
        # ATR 비율
        high_low = df['high'] - df['low']
        df['atr_ratio'] = high_low / df['close']
        
        # NaN 처리
        df = df.fillna(0)
        
        self.feature_columns = [
            'return', 'ma_5_ratio', 'ma_10_ratio', 'ma_20_ratio',
            'rsi_normalized', 'bb_position', 'volume_ratio', 'atr_ratio'
        ]
        
        self.features = df[self.feature_columns].values.astype(np.float32)
        self.prices = df['close'].values
    
    def reset(self, seed=None) -> Tuple[np.ndarray, dict]:
        """환경 초기화"""
        if seed is not None:
            np.random.seed(seed)
        
        self.current_step = self.window_size
        self.capital = self.initial_capital
        self.position = 0.0  # 0: 현금, 1: 풀 포지션
        self.position_price = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.returns = []
        self.peak_capital = self.initial_capital
        
        return self._get_observation(), {}
    
    def _get_observation(self) -> np.ndarray:
        """현재 상태 관찰"""
        start_idx = self.current_step - self.window_size
        end_idx = self.current_step
        
        # 피처 윈도우
        feature_window = self.features[start_idx:end_idx]
        
        # 포지션 정보 추가
        position_info = np.full((self.window_size, 2), 
                                [self.position, self._get_unrealized_pnl()],
                                dtype=np.float32)
        
        obs = np.concatenate([feature_window, position_info], axis=1)
        return obs.astype(np.float32)
    
    def _get_unrealized_pnl(self) -> float:
        """미실현 손익률"""
        if self.position == 0 or self.position_price == 0:
            return 0.0
        current_price = self.prices[self.current_step]
        return (current_price - self.position_price) / self.position_price
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """한 스텝 실행
        
        Args:
            action: 0(홀드), 1(매수), 2(매도)
            
        Returns:
            (관찰, 보상, 종료, truncated, 정보)
        """
        current_price = self.prices[self.current_step]
        reward = 0.0
        info = {'action': action, 'price': current_price}
        
        # 행동 실행
        if action == 1 and self.position == 0:
            # 매수
            self.position = self.max_position
            self.position_price = current_price * (1 + self.commission_rate)
            self.total_trades += 1
            info['trade'] = 'BUY'
            
        elif action == 2 and self.position > 0:
            # 매도
            exit_price = current_price * (1 - self.commission_rate)
            trade_return = (exit_price - self.position_price) / self.position_price
            
            self.returns.append(trade_return)
            reward = trade_return * 100  # 보상 스케일링
            
            if trade_return > 0:
                self.winning_trades += 1
            
            self.capital *= (1 + trade_return * self.position)
            self.position = 0
            self.position_price = 0
            
            info['trade'] = 'SELL'
            info['trade_return'] = trade_return
        
        else:
            # 홀드 - 포지션 보유 중이면 작은 보상
            if self.position > 0:
                unrealized = self._get_unrealized_pnl()
                reward = unrealized * 0.1  # 미실현 손익 반영
        
        # 다음 스텝
        self.current_step += 1
        
        # 종료 조건
        done = self.current_step >= len(self.prices) - 1
        
        # 최대 낙폭 추적
        if self.capital > self.peak_capital:
            self.peak_capital = self.capital
        
        return self._get_observation(), reward, done, False, info
    
    def get_result(self) -> RLTradeResult:
        """최종 결과 반환"""
        # 미청산 포지션 정리
        if self.position > 0:
            current_price = self.prices[self.current_step]
            exit_price = current_price * (1 - self.commission_rate)
            trade_return = (exit_price - self.position_price) / self.position_price
            self.returns.append(trade_return)
            self.capital *= (1 + trade_return * self.position)
            if trade_return > 0:
                self.winning_trades += 1
            self.total_trades += 1
        
        # 통계 계산
        total_return = (self.capital - self.initial_capital) / self.initial_capital
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        if len(self.returns) > 1 and np.std(self.returns) > 0:
            # 실제 데이터 기간 기반 연율화 팩터 사용
            # (거래 수 / 데이터 기간(년)) * 252 거래일로 연율화
            years_in_data = max(len(self.prices) / 252, 1e-6)
            annualize_factor = np.sqrt(len(self.returns) / years_in_data)
            sharpe_ratio = np.mean(self.returns) / np.std(self.returns) * annualize_factor
        else:
            sharpe_ratio = 0
        
        max_drawdown = (self.peak_capital - min(self.capital, self.peak_capital)) / self.peak_capital
        
        return RLTradeResult(
            total_reward=sum(self.returns) * 100,
            total_return=total_return * 100,
            num_trades=self.total_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown * 100,
            final_capital=self.capital
        )


if TORCH_AVAILABLE:
    class DQNNetwork(nn.Module):
        """DQN 신경망"""
        
        def __init__(self, input_shape: Tuple[int, int], n_actions: int):
            super().__init__()
            
            input_size = input_shape[0] * input_shape[1]
            
            self.fc = nn.Sequential(
                nn.Flatten(),
                nn.Linear(input_size, 256),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(256, 128),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(128, 64),
                nn.ReLU(),
                nn.Linear(64, n_actions)
            )
        
        def forward(self, x):
            return self.fc(x)
    
    
    class DQNAgent:
        """DQN 에이전트
        
        Deep Q-Network 기반 트레이딩 에이전트.
        """
        
        def __init__(
            self,
            state_shape: Tuple[int, int],
            n_actions: int,
            learning_rate: float = 0.001,
            gamma: float = 0.99,
            epsilon_start: float = 1.0,
            epsilon_end: float = 0.01,
            epsilon_decay: float = 0.995,
            memory_size: int = 10000,
            batch_size: int = 64,
            target_update: int = 10
        ):
            """초기화
            
            Args:
                state_shape: 상태 차원
                n_actions: 행동 수
                learning_rate: 학습률
                gamma: 할인율
                epsilon_*: 탐험 관련
                memory_size: 리플레이 버퍼 크기
                batch_size: 배치 크기
                target_update: 타겟 네트워크 업데이트 주기
            """
            self.state_shape = state_shape
            self.n_actions = n_actions
            self.gamma = gamma
            self.epsilon = epsilon_start
            self.epsilon_end = epsilon_end
            self.epsilon_decay = epsilon_decay
            self.batch_size = batch_size
            self.target_update = target_update
            
            # 네트워크
            self.policy_net = DQNNetwork(state_shape, n_actions)
            self.target_net = DQNNetwork(state_shape, n_actions)
            self.target_net.load_state_dict(self.policy_net.state_dict())
            
            self.optimizer = optim.Adam(self.policy_net.parameters(), lr=learning_rate)
            
            # 리플레이 버퍼
            self.memory = deque(maxlen=memory_size)
            
            self.steps = 0
        
        def select_action(self, state: np.ndarray, training: bool = True) -> int:
            """행동 선택 (epsilon-greedy)"""
            if training and random.random() < self.epsilon:
                return random.randrange(self.n_actions)
            
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0)
                q_values = self.policy_net(state_tensor)
                return q_values.argmax().item()
        
        def store_transition(
            self,
            state: np.ndarray,
            action: int,
            reward: float,
            next_state: np.ndarray,
            done: bool
        ):
            """경험 저장"""
            self.memory.append((state, action, reward, next_state, done))
        
        def train_step(self) -> float:
            """학습 스텝"""
            if len(self.memory) < self.batch_size:
                return 0.0
            
            # 배치 샘플링
            batch = random.sample(self.memory, self.batch_size)
            states, actions, rewards, next_states, dones = zip(*batch)
            
            states = torch.FloatTensor(np.array(states))
            actions = torch.LongTensor(actions)
            rewards = torch.FloatTensor(rewards)
            next_states = torch.FloatTensor(np.array(next_states))
            dones = torch.FloatTensor(dones)
            
            # 현재 Q값
            current_q = self.policy_net(states).gather(1, actions.unsqueeze(1))
            
            # 타겟 Q값
            with torch.no_grad():
                next_q = self.target_net(next_states).max(1)[0]
                target_q = rewards + (1 - dones) * self.gamma * next_q
            
            # 손실 계산
            loss = F.smooth_l1_loss(current_q.squeeze(), target_q)
            
            # 역전파
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
            self.optimizer.step()
            
            # epsilon 감소
            self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
            
            # 타겟 네트워크 업데이트
            self.steps += 1
            if self.steps % self.target_update == 0:
                self.target_net.load_state_dict(self.policy_net.state_dict())
            
            return loss.item()
        
        def save(self, filepath: str):
            """모델 저장"""
            torch.save({
                'policy_net': self.policy_net.state_dict(),
                'target_net': self.target_net.state_dict(),
                'optimizer': self.optimizer.state_dict(),
                'epsilon': self.epsilon
            }, filepath)
        
        def load(self, filepath: str):
            """모델 로드"""
            checkpoint = torch.load(filepath)
            self.policy_net.load_state_dict(checkpoint['policy_net'])
            self.target_net.load_state_dict(checkpoint['target_net'])
            self.optimizer.load_state_dict(checkpoint['optimizer'])
            self.epsilon = checkpoint['epsilon']


class RLTrainer:
    """강화학습 트레이너"""
    
    def __init__(
        self,
        env: TradingEnvironment,
        agent_type: str = "DQN",  # "DQN", "PPO", "A2C"
        save_dir: str = "models/rl"
    ):
        """초기화
        
        Args:
            env: 트레이딩 환경
            agent_type: 에이전트 유형
            save_dir: 모델 저장 경로
        """
        self.env = env
        self.agent_type = agent_type
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)
        
        # 에이전트 생성
        if agent_type == "DQN" and TORCH_AVAILABLE:
            self.agent = DQNAgent(
                state_shape=env.observation_space_shape,
                n_actions=env.action_space_n
            )
        elif agent_type in ["PPO", "A2C"] and SB3_AVAILABLE:
            vec_env = DummyVecEnv([lambda: env])
            if agent_type == "PPO":
                self.agent = PPO("MlpPolicy", vec_env, verbose=1)
            else:
                self.agent = A2C("MlpPolicy", vec_env, verbose=1)
        else:
            raise ValueError(f"에이전트 {agent_type}를 사용할 수 없습니다.")
    
    def train(self, n_episodes: int = 100) -> List[RLTradeResult]:
        """학습 실행"""
        results = []
        
        for episode in range(n_episodes):
            state, _ = self.env.reset()
            total_reward = 0
            done = False
            
            while not done:
                # 행동 선택
                if self.agent_type == "DQN":
                    action = self.agent.select_action(state, training=True)
                else:
                    action, _ = self.agent.predict(state)
                
                # 환경 스텝
                next_state, reward, done, truncated, info = self.env.step(action)
                total_reward += reward
                
                # DQN 학습
                if self.agent_type == "DQN":
                    self.agent.store_transition(state, action, reward, next_state, done)
                    self.agent.train_step()
                
                state = next_state
            
            # 에피소드 결과
            result = self.env.get_result()
            result.episode = episode + 1
            results.append(result)
            
            if (episode + 1) % 10 == 0:
                avg_return = np.mean([r.total_return for r in results[-10:]])
                logger.info(f"Episode {episode+1}: 평균 수익률 {avg_return:.2f}%, epsilon {self.agent.epsilon:.3f}")
        
        # SB3 에이전트는 별도 학습
        if self.agent_type in ["PPO", "A2C"] and SB3_AVAILABLE:
            self.agent.learn(total_timesteps=n_episodes * len(self.env.prices))
        
        return results
    
    def evaluate(self, n_episodes: int = 10) -> RLTradeResult:
        """평가"""
        results = []
        
        for _ in range(n_episodes):
            state, _ = self.env.reset()
            done = False
            
            while not done:
                if self.agent_type == "DQN":
                    action = self.agent.select_action(state, training=False)
                else:
                    action, _ = self.agent.predict(state, deterministic=True)
                
                state, reward, done, truncated, info = self.env.step(action)
            
            results.append(self.env.get_result())
        
        # 평균 결과
        avg_result = RLTradeResult(
            total_reward=np.mean([r.total_reward for r in results]),
            total_return=np.mean([r.total_return for r in results]),
            num_trades=int(np.mean([r.num_trades for r in results])),
            win_rate=np.mean([r.win_rate for r in results]),
            sharpe_ratio=np.mean([r.sharpe_ratio for r in results]),
            max_drawdown=np.mean([r.max_drawdown for r in results]),
            final_capital=np.mean([r.final_capital for r in results])
        )
        
        return avg_result
    
    def save_model(self, name: str = "rl_model"):
        """모델 저장"""
        filepath = os.path.join(self.save_dir, f"{name}.pth")
        if self.agent_type == "DQN":
            self.agent.save(filepath)
        else:
            self.agent.save(filepath)
        logger.info(f"모델 저장: {filepath}")
    
    def load_model(self, name: str = "rl_model"):
        """모델 로드"""
        filepath = os.path.join(self.save_dir, f"{name}.pth")
        if self.agent_type == "DQN":
            self.agent.load(filepath)
        else:
            self.agent = self.agent.__class__.load(filepath)
        logger.info(f"모델 로드: {filepath}")

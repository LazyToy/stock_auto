"""2025년 투자 시뮬레이션 - 기존 전략 vs AI 전략 비교

한국/미국 주식 각 100만원으로 2025년 성과 비교:
1. 기존 전략 (Risk-Adjusted Momentum)
2. ML 전략 (RandomForest)
3. 앙상블 전략 (기존 + ML 결합)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ML 라이브러리 체크
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️ scikit-learn 미설치 - ML 전략 비활성화")


def add_technical_features(df):
    """기술적 지표 추가"""
    df = df.copy()
    
    # 이동평균
    for period in [5, 10, 20, 50]:
        df[f'ma_{period}'] = df['close'].rolling(window=period).mean()
        df[f'ma_{period}_ratio'] = df['close'] / df[f'ma_{period}']
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # 볼린저밴드
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)
    
    # 수익률
    for period in [1, 5, 10, 20]:
        df[f'return_{period}d'] = df['close'].pct_change(period)
    
    # 거래량 비율
    df['volume_ma10'] = df['volume'].rolling(window=10).mean()
    df['volume_ratio'] = df['volume'] / (df['volume_ma10'] + 1)
    
    return df


def create_ml_labels(df, forward_days=5, threshold=0.02):
    """ML 레이블 생성 (미래 수익률 기반)"""
    df = df.copy()
    df['future_return'] = df['close'].shift(-forward_days) / df['close'] - 1
    df['label'] = 0
    df.loc[df['future_return'] > threshold, 'label'] = 1
    df.loc[df['future_return'] < -threshold, 'label'] = -1
    return df


def calculate_momentum_score(price_series, date, lookback=126):
    """모멘텀/변동성 점수 계산"""
    try:
        history = price_series.loc[:date].tail(130)
        if len(history) < 100:
            return -np.inf
        
        current_price = history.iloc[-1]
        past_price = history.iloc[-lookback]
        
        momentum = (current_price - past_price) / past_price
        daily_ret = history.pct_change().dropna()
        volatility = daily_ret.std() * np.sqrt(252)
        
        if volatility == 0:
            return 0
        
        return momentum / volatility
    except:
        return -np.inf


class TraditionalStrategy:
    """기존 모멘텀/변동성 전략"""
    
    def __init__(self, top_n=3):
        self.top_n = top_n
        self.name = "Traditional (Momentum/Vol)"
    
    def select_stocks(self, price_df, universe, date):
        """주식 선정"""
        scores = []
        for ticker in universe:
            if ticker not in price_df.columns:
                continue
            score = calculate_momentum_score(price_df[ticker], date)
            scores.append((ticker, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in scores[:self.top_n]]


class MLStrategy:
    """ML 기반 전략"""
    
    def __init__(self, top_n=3, model_type='rf'):
        self.top_n = top_n
        self.model_type = model_type
        self.models = {}  # {ticker: model}
        self.scalers = {}  # {ticker: scaler}
        self.name = f"ML ({model_type.upper()})"
        
        self.feature_cols = [
            'ma_5_ratio', 'ma_10_ratio', 'ma_20_ratio',
            'rsi', 'macd_hist', 'bb_position',
            'return_1d', 'return_5d', 'volume_ratio'
        ]
    
    def train(self, price_df, universe, train_end_date):
        """모든 종목에 대해 모델 학습"""
        if not ML_AVAILABLE:
            return
        
        for ticker in universe:
            if ticker not in price_df.columns:
                continue
            
            # 단일 종목 데이터프레임 생성
            df = pd.DataFrame({
                'close': price_df[ticker],
                'volume': price_df.get(f'{ticker}_vol', price_df[ticker] * 0 + 1e6)
            }).dropna()
            
            if len(df) < 200:
                continue
            
            # 피처 생성
            df = add_technical_features(df)
            df = create_ml_labels(df)
            df = df.dropna()
            
            # 학습 데이터 (train_end_date 이전)
            train_df = df.loc[:train_end_date]
            if len(train_df) < 100:
                continue
            
            X = train_df[self.feature_cols].values
            y = train_df['label'].values
            
            # 스케일링
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 모델 학습
            if self.model_type == 'rf':
                model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
            else:
                model = GradientBoostingClassifier(n_estimators=50, max_depth=3, random_state=42)
            
            model.fit(X_scaled, y)
            
            self.models[ticker] = model
            self.scalers[ticker] = scaler
    
    def select_stocks(self, price_df, universe, date):
        """ML 예측 기반 주식 선정"""
        if not ML_AVAILABLE or not self.models:
            return []
        
        predictions = []
        
        for ticker in universe:
            if ticker not in self.models:
                continue
            
            # 현재 피처 생성
            df = pd.DataFrame({
                'close': price_df[ticker],
                'volume': price_df.get(f'{ticker}_vol', price_df[ticker] * 0 + 1e6)
            })
            
            df = add_technical_features(df)
            df = df.dropna()
            
            if date not in df.index:
                continue
            
            # 예측
            try:
                features = df.loc[date, self.feature_cols].values.reshape(1, -1)
                features_scaled = self.scalers[ticker].transform(features)
                
                pred = self.models[ticker].predict(features_scaled)[0]
                proba = self.models[ticker].predict_proba(features_scaled)[0]
                confidence = max(proba)
                
                # 매수 신호 (1) 이고 신뢰도가 높은 순
                if pred == 1:
                    predictions.append((ticker, confidence))
            except:
                continue
        
        # 신뢰도 순 정렬
        predictions.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in predictions[:self.top_n]]


class EnsembleStrategy:
    """기존 + ML 앙상블 전략"""
    
    def __init__(self, top_n=3):
        self.traditional = TraditionalStrategy(top_n=top_n * 2)
        self.ml = MLStrategy(top_n=top_n * 2)
        self.top_n = top_n
        self.name = "Ensemble (Trad + ML)"
    
    def train(self, price_df, universe, train_end_date):
        self.ml.train(price_df, universe, train_end_date)
    
    def select_stocks(self, price_df, universe, date):
        """두 전략의 합집합에서 공통 종목 우선 선정"""
        trad_picks = set(self.traditional.select_stocks(price_df, universe, date))
        ml_picks = set(self.ml.select_stocks(price_df, universe, date))
        
        # 교집합 우선
        common = list(trad_picks & ml_picks)
        
        # 부족하면 나머지 추가
        remaining = list((trad_picks | ml_picks) - set(common))
        
        result = common + remaining
        return result[:self.top_n]


def run_backtest(market, capital, universe, strategy, start_date=None, end_date=None):
    """백테스트 실행"""
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    # 데이터 다운로드 (학습용 + 테스트용)
    data_start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")  # 학습용 데이터 시작 (2년 전)
    
    print(f"[{market}] {strategy.name} - 데이터 다운로드 중...")
    
    data = {}
    for ticker in universe:
        df = yf.download(ticker, start=data_start, end=end_date, progress=False, multi_level_index=False)
        if df.empty:
            continue
        
        if 'Adj Close' in df.columns:
            data[ticker] = df['Adj Close']
        elif 'Close' in df.columns:
            data[ticker] = df['Close']
    
    price_df = pd.DataFrame(data)
    price_df = price_df.ffill()
    
    # ML 전략 학습 (start_date 이전 데이터로)
    if hasattr(strategy, 'train'):
        train_end = pd.Timestamp(start_date) - timedelta(days=1)
        strategy.train(price_df, universe, train_end)
    
    # 월별 리밸런싱
    rebalance_dates = pd.date_range(start=start_date, end=end_date, freq='BMS')
    
    current_cash = capital
    holdings = {}
    portfolio_values = [capital]
    trades = 0
    
    for date in rebalance_dates:
        # 가장 가까운 거래일 찾기
        if date not in price_df.index:
            idx = price_df.index.searchsorted(date)
            if idx >= len(price_df):
                current_date = price_df.index[-1]
            else:
                current_date = price_df.index[idx]
        else:
            current_date = date
        
        # 현재 가치 평가
        total_value = current_cash
        for ticker, qty in holdings.items():
            if ticker in price_df.columns:
                price = price_df.loc[current_date, ticker]
                total_value += price * qty
        
        # 주식 선정
        selected = strategy.select_stocks(price_df, universe, current_date)
        
        if not selected:
            selected = [universe[0]]  # 폴백
        
        # 전량 매도 후 재매수
        current_cash = total_value
        holdings = {}
        trades += 1
        
        target_amount = current_cash / len(selected)
        for ticker in selected:
            if ticker not in price_df.columns:
                continue
            price = price_df.loc[current_date, ticker]
            qty = int(target_amount // price)
            if qty > 0:
                holdings[ticker] = qty
                current_cash -= qty * price
        
        portfolio_values.append(total_value)
    
    # 최종 평가
    final_date = price_df.index[-1]
    final_value = current_cash
    for ticker, qty in holdings.items():
        if ticker in price_df.columns:
            price = price_df.loc[final_date, ticker]
            final_value += price * qty
    
    total_return = (final_value - capital) / capital * 100
    
    return {
        'strategy': strategy.name,
        'market': market,
        'initial': capital,
        'final': final_value,
        'return_pct': total_return,
        'trades': trades
    }


def main():
    print("=" * 60)
    print("🚀 2025년 투자 시뮬레이션 - 기존 전략 vs AI 전략 비교")
    print("=" * 60)
    
    # 유니버스
    kr_universe = [
        "005930.KS", "000660.KS", "035420.KS", "035720.KS", "005380.KS",
        "051910.KS", "006400.KS", "086520.KQ", "247540.KQ", "005490.KS"
    ]
    
    us_universe = [
        "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META",
        "AMD", "PLTR", "LLY"
    ]
    
    # 전략
    strategies = [
        TraditionalStrategy(top_n=3),
        MLStrategy(top_n=3, model_type='rf') if ML_AVAILABLE else None,
        EnsembleStrategy(top_n=3) if ML_AVAILABLE else None
    ]
    strategies = [s for s in strategies if s is not None]
    
    results = []
    
    # 한국 시장
    print("\n🇰🇷 한국 시장 (초기 자본: 1,000,000원)")
    print("-" * 40)
    for strategy in strategies:
        result = run_backtest("KR", 1_000_000, kr_universe, strategy)
        results.append(result)
        print(f"  {result['strategy']}: {result['return_pct']:+.2f}% → {result['final']:,.0f}원")
    
    # 미국 시장
    print("\n🇺🇸 미국 시장 (초기 자본: $715 ≈ 100만원)")
    print("-" * 40)
    for strategy in strategies:
        # 새 전략 인스턴스 생성
        if isinstance(strategy, TraditionalStrategy):
            s = TraditionalStrategy(top_n=3)
        elif isinstance(strategy, MLStrategy):
            s = MLStrategy(top_n=3)
        else:
            s = EnsembleStrategy(top_n=3)
        
        result = run_backtest("US", 715, us_universe, s)
        results.append(result)
        print(f"  {result['strategy']}: {result['return_pct']:+.2f}% → ${result['final']:,.2f}")
    
    # 종합 결과
    print("\n" + "=" * 60)
    print("📊 종합 결과 요약")
    print("=" * 60)
    
    exchange_rate = 1400  # USD/KRW
    
    for strategy_name in set(r['strategy'] for r in results):
        kr_result = next((r for r in results if r['strategy'] == strategy_name and r['market'] == 'KR'), None)
        us_result = next((r for r in results if r['strategy'] == strategy_name and r['market'] == 'US'), None)
        
        if kr_result and us_result:
            total_initial = 1_000_000 + (715 * exchange_rate)
            kr_final = kr_result['final']
            us_final_krw = us_result['final'] * exchange_rate
            total_final = kr_final + us_final_krw
            total_return = (total_final - total_initial) / total_initial * 100
            
            print(f"\n📌 {strategy_name}")
            print(f"   KR: {kr_result['return_pct']:+.2f}% ({kr_result['final']:,.0f}원)")
            print(f"   US: {us_result['return_pct']:+.2f}% (${us_result['final']:,.2f} = {us_final_krw:,.0f}원)")
            print(f"   💰 총합: {total_return:+.2f}% ({total_final:,.0f}원)")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

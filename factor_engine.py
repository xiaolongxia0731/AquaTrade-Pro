#!/usr/bin/env python3
"""
AquaTrade Pro - 多因子策略引擎
支持动量、趋势、波动率、成交量等因子
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime
import time


@dataclass
class FactorResult:
    """因子计算结果"""
    symbol: str
    factor_name: str
    score: float  # 0-100
    raw_value: float
    rank: int
    weight: float


class BaseFactor(ABC):
    """因子基类"""
    
    def __init__(self, name: str, weight: float = 1.0, **kwargs):
        self.name = name
        self.weight = weight
        self.params = kwargs
        
    @abstractmethod
    def calculate(self, kline_data: pd.DataFrame) -> float:
        """
        计算因子值
        
        Args:
            kline_data: DataFrame with columns [open, high, low, close, volume]
        
        Returns:
            float: 因子得分 (0-100)
        """
        pass
    
    def normalize(self, value: float, min_val: float, max_val: float) -> float:
        """标准化到 0-100"""
        if max_val == min_val:
            return 50.0
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(100.0, normalized * 100))


class MomentumFactor(BaseFactor):
    """
    动量因子
    
    计算逻辑：
    - 近期涨幅排名
    - 涨幅越高得分越高
    """
    
    def __init__(self, period: int = 20, **kwargs):
        super().__init__("momentum", **kwargs)
        self.period = period
        
    def calculate(self, kline_data: pd.DataFrame) -> float:
        if len(kline_data) < self.period:
            return 50.0
        
        close = kline_data['close'].values
        
        # 计算涨幅
        momentum = (close[-1] - close[-self.period]) / close[-self.period] * 100
        
        # 标准化到 0-100 (假设涨幅范围 -20% ~ +20%)
        score = self.normalize(momentum, -20, 20)
        
        return score


class TrendFactor(BaseFactor):
    """
    趋势因子
    
    计算逻辑：
    - 短期均线在长期均线上方 → 多头趋势
    - 均线斜率越大 → 趋势越强
    """
    
    def __init__(self, short_period: int = 5, long_period: int = 20, **kwargs):
        super().__init__("trend", **kwargs)
        self.short_period = short_period
        self.long_period = long_period
        
    def calculate(self, kline_data: pd.DataFrame) -> float:
        if len(kline_data) < self.long_period:
            return 50.0
        
        close = kline_data['close'].values
        
        # 计算均线
        ma_short = np.mean(close[-self.short_period:])
        ma_long = np.mean(close[-self.long_period:])
        
        # 均线差值百分比
        diff_pct = (ma_short - ma_long) / ma_long * 100
        
        # 标准化 (假设范围 -5% ~ +5%)
        score = self.normalize(diff_pct, -5, 5)
        
        return score


class VolatilityFactor(BaseFactor):
    """
    波动率因子 (ATR)
    
    计算逻辑：
    - ATR 越低 → 波动越小 → 得分越高（适合趋势交易）
    - 或反过来，高波动适合突破策略
    """
    
    def __init__(self, period: int = 14, inverse: bool = True, **kwargs):
        super().__init__("volatility", **kwargs)
        self.period = period
        self.inverse = inverse  # True: 低波动高分, False: 高波动高分
        
    def calculate(self, kline_data: pd.DataFrame) -> float:
        if len(kline_data) < self.period + 1:
            return 50.0
        
        high = kline_data['high'].values
        low = kline_data['low'].values
        close = kline_data['close'].values
        
        # 计算 TR (True Range)
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        # 计算 ATR
        atr = np.mean(tr[-self.period:])
        
        # ATR 百分比
        atr_pct = atr / close[-1] * 100
        
        # 标准化 (假设范围 0% ~ 5%)
        if self.inverse:
            # 低波动高分
            score = 100 - self.normalize(atr_pct, 0, 5)
        else:
            # 高波动高分
            score = self.normalize(atr_pct, 0, 5)
        
        return score


class VolumeFactor(BaseFactor):
    """
    成交量因子
    
    计算逻辑：
    - 成交量放大 → 资金关注度高
    - 量价配合（放量上涨）
    """
    
    def __init__(self, period: int = 20, **kwargs):
        super().__init__("volume", **kwargs)
        self.period = period
        
    def calculate(self, kline_data: pd.DataFrame) -> float:
        if len(kline_data) < self.period:
            return 50.0
        
        volume = kline_data['volume'].values
        close = kline_data['close'].values
        
        # 近期平均成交量
        avg_volume = np.mean(volume[-self.period:])
        
        # 今日成交量比率
        volume_ratio = volume[-1] / avg_volume if avg_volume > 0 else 1.0
        
        # 价格变化方向
        price_change = (close[-1] - close[-2]) / close[-2] if len(close) > 1 else 0
        
        # 量价配合得分
        if price_change > 0 and volume_ratio > 1.0:
            # 放量上涨 - 最佳
            score = min(100, volume_ratio * 50)
        elif price_change < 0 and volume_ratio > 1.0:
            # 放量下跌 - 最差
            score = max(0, 100 - volume_ratio * 50)
        else:
            # 缩量 - 中性
            score = 50.0
        
        return score


class MultiFactorEngine:
    """
    多因子引擎
    
    功能：
    1. 计算多个因子的得分
    2. 加权合成综合得分
    3. 品种排序和筛选
    """
    
    FACTOR_MAP = {
        'momentum': MomentumFactor,
        'trend': TrendFactor,
        'volatility': VolatilityFactor,
        'volume': VolumeFactor,
    }
    
    def __init__(self, config_manager=None):
        self.config = config_manager
        self.factors: Dict[str, BaseFactor] = {}
        self.cache: Dict[str, Dict] = {}  # 缓存计算结果
        self.cache_ttl = 60  # 缓存60秒
        self._init_factors()
        
    def _init_factors(self):
        """初始化因子（从配置读取）"""
        if self.config:
            factor_configs = self.config.get('factors', {})
            for name, cfg in factor_configs.items():
                if cfg.get('enabled', False) and name in self.FACTOR_MAP:
                    factor_class = self.FACTOR_MAP[name]
                    weight = cfg.get('weight', 0.25)
                    
                    # 提取参数
                    kwargs = {k: v for k, v in cfg.items() 
                             if k not in ['enabled', 'weight', 'description']}
                    kwargs['weight'] = weight
                    
                    self.factors[name] = factor_class(**kwargs)
    
    def update_factor_weight(self, name: str, weight: float):
        """更新因子权重"""
        if name in self.factors:
            self.factors[name].weight = weight
    
    def calculate_single_factor(self, symbol: str, factor_name: str, 
                               kline_data: pd.DataFrame) -> Optional[FactorResult]:
        """计算单个因子得分"""
        if factor_name not in self.factors:
            return None
        
        factor = self.factors[factor_name]
        score = factor.calculate(kline_data)
        
        return FactorResult(
            symbol=symbol,
            factor_name=factor_name,
            score=score,
            raw_value=0.0,  # 可以扩展记录原始值
            rank=0,
            weight=factor.weight
        )
    
    def calculate_all_factors(self, symbol: str, 
                             kline_data: pd.DataFrame) -> Dict[str, FactorResult]:
        """计算所有启用的因子"""
        results = {}
        
        for name, factor in self.factors.items():
            score = factor.calculate(kline_data)
            results[name] = FactorResult(
                symbol=symbol,
                factor_name=name,
                score=score,
                raw_value=0.0,
                rank=0,
                weight=factor.weight
            )
        
        return results
    
    def calculate_composite_score(self, symbol: str, 
                                  kline_data: pd.DataFrame) -> Tuple[float, Dict[str, float]]:
        """
        计算综合得分
        
        Returns:
            (综合得分, 各因子得分字典)
        """
        factor_results = self.calculate_all_factors(symbol, kline_data)
        
        if not factor_results:
            return 50.0, {}
        
        # 加权计算
        total_weight = sum(r.weight for r in factor_results.values())
        if total_weight == 0:
            return 50.0, {}
        
        composite_score = 0
        details = {}
        
        for name, result in factor_results.items():
            weighted_score = result.score * result.weight / total_weight
            composite_score += weighted_score
            details[name] = result.score
        
        return composite_score, details
    
    def rank_symbols(self, symbols_data: Dict[str, pd.DataFrame]) -> List[Dict]:
        """
        对所有品种排序
        
        Args:
            symbols_data: {symbol: kline_dataframe}
        
        Returns:
            排序后的列表，每个元素包含 symbol, score, details
        """
        results = []
        
        for symbol, kline_data in symbols_data.items():
            try:
                score, details = self.calculate_composite_score(symbol, kline_data)
                results.append({
                    'symbol': symbol,
                    'score': score,
                    'details': details,
                    'timestamp': time.time()
                })
            except Exception as e:
                print(f"[MultiFactorEngine] 计算 {symbol} 失败: {e}")
                continue
        
        # 按得分排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # 添加排名
        for i, r in enumerate(results):
            r['rank'] = i + 1
        
        return results
    
    def get_top_symbols(self, symbols_data: Dict[str, pd.DataFrame], 
                       n: int = 5, min_score: float = 0) -> List[Dict]:
        """获取排名前N的品种"""
        ranked = self.rank_symbols(symbols_data)
        
        # 过滤最低得分
        filtered = [r for r in ranked if r['score'] >= min_score]
        
        return filtered[:n]
    
    def get_factor_explanation(self, factor_name: str) -> str:
        """获取因子说明"""
        explanations = {
            'momentum': '动量因子：近期涨幅越高得分越高，追涨策略',
            'trend': '趋势因子：均线多头排列得分高，趋势跟踪策略',
            'volatility': '波动率因子：低波动环境得分高，趋势交易更稳定',
            'volume': '成交量因子：放量上涨得分高，资金关注度高',
        }
        return explanations.get(factor_name, '未知因子')


# 测试代码
if __name__ == '__main__':
    # 创建测试数据
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # 模拟螺纹钢行情（上涨趋势）
    close = 3500 + np.cumsum(np.random.randn(100) * 10 + 2)
    high = close + np.abs(np.random.randn(100)) * 20
    low = close - np.abs(np.random.randn(100)) * 20
    open_price = close + np.random.randn(100) * 10
    volume = np.random.randint(100000, 500000, 100)
    
    df = pd.DataFrame({
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    }, index=dates)
    
    # 测试因子引擎
    engine = MultiFactorEngine()
    
    # 添加测试因子
    engine.factors = {
        'momentum': MomentumFactor(period=20, weight=0.4),
        'trend': TrendFactor(short_period=5, long_period=20, weight=0.4),
        'volatility': VolatilityFactor(period=14, weight=0.2),
    }
    
    # 计算得分
    score, details = engine.calculate_composite_score('rb2505', df)
    
    print(f"螺纹钢 rb2505 综合得分: {score:.2f}")
    print(f"各因子得分: {details}")
    
    # 测试排序
    symbols_data = {
        'rb2505': df,
        'cu2505': df * 1.1,  # 铜涨幅更高
        'au2506': df * 0.95,  # 黄金涨幅较低
    }
    
    ranked = engine.rank_symbols(symbols_data)
    print("\n品种排名:")
    for r in ranked:
        print(f"{r['rank']}. {r['symbol']}: {r['score']:.2f}")

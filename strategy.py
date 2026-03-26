"""
AquaTrade - 策略模块
实现双均线策略（支持扩展到多策略）
"""

import numpy as np
from collections import deque
from typing import Dict, List, Optional, Tuple
from enum import Enum
import config
from logger import logger


class Signal(Enum):
    """交易信号"""
    BUY = "BUY"      # 开多/平空
    SELL = "SELL"    # 开空/平多
    HOLD = "HOLD"    # 持仓不动
    CLOSE = "CLOSE"  # 平仓


class DualMAStrategy:
    """双均线策略
    
    策略逻辑：
    - 短均线上穿长均线（金叉）→ 做多信号
    - 短均线下穿长均线（死叉）→ 做空信号
    - 已经持有多头时，死叉信号 → 平多
    - 已经持有空头时，金叉信号 → 平空
    """
    
    def __init__(self, symbol: str, short_period: int = None, long_period: int = None):
        self.symbol = symbol
        self.short_period = short_period or config.MA_SHORT_PERIOD
        self.long_period = long_period or config.MA_LONG_PERIOD
        
        # 价格缓存
        self.prices: deque = deque(maxlen=self.long_period + 10)
        
        # 当前持仓状态
        self.position = 0  # >0 多头, <0 空头, 0 空仓
        self.avg_price = 0.0
        
        # 上一次信号
        self.last_signal = Signal.HOLD
        self.last_ma_short = 0.0
        self.last_ma_long = 0.0
        
        logger.info(f"双均线策略初始化: {symbol}, 短周期={self.short_period}, 长周期={self.long_period}")
        
    def on_tick(self, price: float) -> Signal:
        """接收Tick数据，返回交易信号"""
        self.prices.append(price)
        
        # 数据不足时返回HOLD
        if len(self.prices) < self.long_period:
            return Signal.HOLD
            
        # 计算均线
        prices_array = np.array(list(self.prices))
        ma_short = np.mean(prices_array[-self.short_period:])
        ma_long = np.mean(prices_array[-self.long_period:])
        
        # 保存当前均线值
        self.last_ma_short = ma_short
        self.last_ma_long = ma_long
        
        # 判断金叉/死叉
        prev_ma_short = np.mean(prices_array[-self.short_period-1:-1])
        prev_ma_long = np.mean(prices_array[-self.long_period-1:-1])
        
        golden_cross = prev_ma_short <= prev_ma_long and ma_short > ma_long
        dead_cross = prev_ma_short >= prev_ma_long and ma_short < ma_long
        
        signal = Signal.HOLD
        
        if golden_cross:
            if self.position <= 0:  # 空仓或空头 → 开多/平空
                signal = Signal.BUY
            else:
                signal = Signal.HOLD  # 已有多头，继续持仓
                
        elif dead_cross:
            if self.position >= 0:  # 空仓或多头 → 开空/平多
                signal = Signal.SELL
            else:
                signal = Signal.HOLD  # 已有空头，继续持仓
                
        # 记录信号
        if signal != Signal.HOLD:
            logger.strategy_signal(self.symbol, signal.value, price, ma_short, ma_long)
            self.last_signal = signal
            
        return signal
        
    def on_position_change(self, new_position: int, avg_price: float = 0.0):
        """更新持仓状态（由交易模块调用）"""
        old_pos = self.position
        self.position = new_position
        self.avg_price = avg_price
        
        if old_pos != new_position:
            logger.info(f"策略持仓更新: {self.symbol} {old_pos} -> {new_position} @ {avg_price}")
            
    def get_target_action(self, signal: Signal) -> Tuple[str, int]:
        """根据信号生成交易动作
        
        Returns:
            (动作, 数量)
            动作: 'buy_open', 'sell_open', 'buy_close', 'sell_close', 'hold'
        """
        if signal == Signal.HOLD:
            return 'hold', 0
            
        if signal == Signal.BUY:
            if self.position < 0:
                # 有空头，先平空
                return 'buy_close', abs(self.position)
            else:
                # 空仓，开多
                return 'buy_open', 1
                
        if signal == Signal.SELL:
            if self.position > 0:
                # 有多头，先平多
                return 'sell_close', abs(self.position)
            else:
                # 空仓，开空
                return 'sell_open', 1
                
        return 'hold', 0

    def check_take_profit(self, current_price: float) -> Optional[Signal]:
        """检查是否需要止盈"""
        if self.position == 0 or config.TAKE_PROFIT_TICKS == 0:
            return None

        tick_size = 1
        take_profit_ticks = config.TAKE_PROFIT_TICKS

        if self.position > 0:  # 多头
            profit = current_price - self.avg_price
            if profit >= take_profit_ticks * tick_size:
                logger.warning(f"多头止盈触发: 成本{self.avg_price}, 现价{current_price}, 盈利{profit}")
                return Signal.SELL  # 平多止盈

        elif self.position < 0:  # 空头
            profit = self.avg_price - current_price
            if profit >= take_profit_ticks * tick_size:
                logger.warning(f"空头止盈触发: 成本{self.avg_price}, 现价{current_price}, 盈利{profit}")
                return Signal.BUY  # 平空止盈

        return None

    def check_stop_loss(self, current_price: float) -> Optional[Signal]:
        """检查是否需要止损"""
        if self.position == 0 or config.STOP_LOSS_TICKS == 0:
            return None
            
        # 这里简化处理，实际应该用tick size计算
        # 假设 1 tick = 1 元
        tick_size = 1
        stop_loss_ticks = config.STOP_LOSS_TICKS
        
        if self.position > 0:  # 多头
            loss = self.avg_price - current_price
            if loss >= stop_loss_ticks * tick_size:
                logger.warning(f"多头止损触发: 成本{self.avg_price}, 现价{current_price}, 亏损{loss}")
                return Signal.SELL  # 平多
                
        elif self.position < 0:  # 空头
            loss = current_price - self.avg_price
            if loss >= stop_loss_ticks * tick_size:
                logger.warning(f"空头止损触发: 成本{self.avg_price}, 现价{current_price}, 亏损{loss}")
                return Signal.BUY  # 平空
                
        return None
        
    def get_status(self) -> dict:
        """获取策略状态"""
        return {
            'symbol': self.symbol,
            'position': self.position,
            'avg_price': self.avg_price,
            'ma_short': round(self.last_ma_short, 2),
            'ma_long': round(self.last_ma_long, 2),
            'last_signal': self.last_signal.value,
            'data_points': len(self.prices)
        }


class StrategyManager:
    """策略管理器 - 管理多个策略实例"""
    
    def __init__(self):
        self.strategies: Dict[str, DualMAStrategy] = {}
        
    def add_strategy(self, symbol: str, strategy_type: str = "dual_ma"):
        """添加策略"""
        if strategy_type == "dual_ma":
            self.strategies[symbol] = DualMAStrategy(symbol)
        else:
            raise ValueError(f"不支持的策略类型: {strategy_type}")
            
        logger.info(f"添加策略: {symbol} ({strategy_type})")
        
    def on_tick(self, symbol: str, price: float) -> Optional[Tuple[Signal, str, int]]:
        """处理tick数据，返回交易决策
        
        Returns:
            (信号, 动作, 数量) 或 None
        """
        if symbol not in self.strategies:
            return None
            
        strategy = self.strategies[symbol]
        
        # 先检查止盈（盈利时优先锁定利润）
        profit_signal = strategy.check_take_profit(price)
        if profit_signal:
            action, volume = strategy.get_target_action(profit_signal)
            return profit_signal, action, volume
        
        # 再检查止损
        stop_signal = strategy.check_stop_loss(price)
        if stop_signal:
            action, volume = strategy.get_target_action(stop_signal)
            return stop_signal, action, volume
            
        # 再检查策略信号
        signal = strategy.on_tick(price)
        if signal != Signal.HOLD:
            action, volume = strategy.get_target_action(signal)
            return signal, action, volume
            
        return None
        
    def update_position(self, symbol: str, position: int, avg_price: float = 0.0):
        """更新策略持仓状态"""
        if symbol in self.strategies:
            self.strategies[symbol].on_position_change(position, avg_price)
            
    def get_all_status(self) -> List[dict]:
        """获取所有策略状态"""
        return [s.get_status() for s in self.strategies.values()]
        
    def get_strategy(self, symbol: str) -> Optional[DualMAStrategy]:
        """获取指定策略"""
        return self.strategies.get(symbol)

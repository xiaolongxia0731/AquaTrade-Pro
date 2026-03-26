"""
AquaTrade - 风控管理模块
提供完整的前置风控、持仓风控、异常熔断功能
"""

import time
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Tuple, Optional
import config
from logger import logger


class RiskManager:
    """风控管理器 - 所有交易决策必须经过风控检查"""
    
    def __init__(self):
        # 持仓信息 {symbol: {'long': 0, 'short': 0}}
        self.positions: Dict[str, Dict[str, int]] = {}
        
        # 账户权益
        self.account_balance = 0.0
        self.initial_balance = 0.0
        self.daily_high = 0.0
        
        # 报单频率控制
        self.order_history: deque = deque()
        self.order_history_maxlen = 100
        
        # 错误计数
        self.error_count = 0
        self.last_error_time = None
        
        # 暂停状态
        self.is_paused = False
        self.pause_reason = ""
        
        # 熔断状态
        self.is_circuit_breaker = False
        
        # 最新行情缓存 {symbol: {'bid': 0, 'ask': 0, 'last': 0}}
        self.last_quotes: Dict[str, Dict] = {}
        
        # 活跃订单缓存 {order_id: {'symbol': '', 'volume': 0, 'price': 0, 'time': timestamp}}
        self.active_orders: Dict[str, Dict] = {}
        
        logger.info("风控管理器初始化完成")
        logger.info(f"风控参数: 最大持仓={config.MAX_POSITION}, 最大回撤={config.MAX_DRAWDOWN*100}%, "
                   f"最大报单频率={config.MAX_ORDERS_PER_MIN}/分钟")
        
    def set_account_balance(self, balance: float):
        """设置账户权益"""
        self.account_balance = balance
        if self.initial_balance == 0:
            self.initial_balance = balance
            self.daily_high = balance
        else:
            self.daily_high = max(self.daily_high, balance)
            
    def update_position(self, symbol: str, long_pos: int = 0, short_pos: int = 0):
        """更新持仓信息"""
        self.positions[symbol] = {'long': long_pos, 'short': short_pos}
        logger.position_update(symbol, long_pos, short_pos, self.account_balance)
        
    def update_quote(self, symbol: str, bid: float, ask: float, last: float):
        """更新行情"""
        self.last_quotes[symbol] = {
            'bid': bid,
            'ask': ask,
            'last': last,
            'time': time.time()
        }
        
    def check_pre_trade(self, symbol: str, direction: str, volume: int, price: float) -> Tuple[bool, str]:
        """交易前风控检查
        
        Args:
            symbol: 合约代码
            direction: 方向 ('buy_open', 'sell_open', 'buy_close', 'sell_close')
            volume: 手数
            price: 价格
            
        Returns:
            (是否通过, 拒绝原因)
        """
        # 1. 检查暂停状态
        if self.is_paused:
            return False, f"交易已暂停: {self.pause_reason}"
            
        if self.is_circuit_breaker:
            return False, "熔断状态，禁止交易"
            
        # 2. 检查报单频率
        if not self._check_order_rate():
            self._trigger_risk("报单频率限制", f"超过{config.MAX_ORDERS_PER_MIN}次/分钟")
            return False, "报单频率过高，请稍后"
            
        # 3. 检查价格偏离
        if not self._check_price_deviation(symbol, price):
            deviation = config.PRICE_DEVIATION_LIMIT * 100
            return False, f"价格偏离过大，超过最新价±{deviation}%限制"
            
        # 4. 检查持仓限制（开仓时）
        if 'open' in direction:
            current_pos = self.positions.get(symbol, {'long': 0, 'short': 0})
            if 'buy' in direction:
                new_pos = current_pos['long'] + volume
            else:
                new_pos = current_pos['short'] + volume
                
            if new_pos > config.MAX_POSITION:
                self._trigger_risk("持仓限制", f"{symbol} 持仓{new_pos}超过最大限制{config.MAX_POSITION}")
                return False, f"持仓限制：最大允许{config.MAX_POSITION}手"
                
        # 5. 检查回撤限制
        if not self._check_drawdown():
            drawdown = config.MAX_DRAWDOWN * 100
            self._trigger_risk("回撤限制", f"单日回撤超过{drawdown}%")
            return False, f"回撤限制：单日最大回撤{drawdown}%"
            
        # 6. 检查连续错误
        if self.error_count >= config.MAX_CONSECUTIVE_ERRORS:
            self._trigger_risk("连续错误", f"连续{self.error_count}次错误")
            self.emergency_pause("连续错误次数超限")
            return False, "连续错误次数超限，已暂停交易"
            
        # 记录报单时间
        self._record_order()
        
        return True, "通过"
        
    def check_post_trade(self, symbol: str, trade_info: dict) -> bool:
        """成交后检查"""
        # 更新持仓
        # 这里简化处理，实际需要根据成交回报更新
        return True
        
    def _check_order_rate(self) -> bool:
        """检查报单频率"""
        now = time.time()
        one_min_ago = now - 60
        
        # 清理过期记录
        while self.order_history and self.order_history[0] < one_min_ago:
            self.order_history.popleft()
            
        return len(self.order_history) < config.MAX_ORDERS_PER_MIN
        
    def _record_order(self):
        """记录报单时间"""
        self.order_history.append(time.time())
        
    def _check_price_deviation(self, symbol: str, price: float) -> bool:
        """检查价格偏离"""
        if symbol not in self.last_quotes:
            return True  # 无行情时不限制
            
        last = self.last_quotes[symbol].get('last', 0)
        if last == 0:
            return True
            
        deviation = abs(price - last) / last
        return deviation <= config.PRICE_DEVIATION_LIMIT
        
    def _check_drawdown(self) -> bool:
        """检查回撤限制"""
        if self.daily_high == 0 or self.account_balance == 0:
            return True
            
        drawdown = (self.daily_high - self.account_balance) / self.initial_balance
        return drawdown <= config.MAX_DRAWDOWN
        
    def _trigger_risk(self, risk_type: str, details: str):
        """触发风控记录"""
        logger.risk_trigger(risk_type, details)
        
    def report_error(self, error_msg: str):
        """报告错误，累计计数"""
        self.error_count += 1
        self.last_error_time = time.time()
        logger.error(f"交易错误 #{self.error_count}: {error_msg}")
        
        if self.error_count >= config.MAX_CONSECUTIVE_ERRORS:
            self.emergency_pause(f"连续{self.error_count}次错误")
            
    def clear_error(self):
        """清除错误计数（成功交易后）"""
        if self.error_count > 0:
            self.error_count = 0
            logger.info("错误计数已清零")
            
    def emergency_pause(self, reason: str):
        """紧急暂停"""
        self.is_paused = True
        self.pause_reason = reason
        logger.emergency("交易暂停", reason)
        
    def pause(self, reason: str = "手动暂停"):
        """暂停交易"""
        self.is_paused = True
        self.pause_reason = reason
        logger.info(f"交易已暂停: {reason}")
        
    def resume(self):
        """恢复交易"""
        if self.is_circuit_breaker:
            logger.warning("熔断状态，无法恢复，需要人工确认")
            return False
            
        self.is_paused = False
        self.pause_reason = ""
        self.clear_error()
        logger.info("交易已恢复")
        return True
        
    def circuit_breaker(self, reason: str):
        """熔断 - 需要人工干预才能恢复"""
        self.is_circuit_breaker = True
        self.emergency_pause(f"熔断: {reason}")
        logger.emergency("熔断触发", reason)
        
    def reset_circuit_breaker(self):
        """人工重置熔断（需要确认）"""
        self.is_circuit_breaker = False
        self.is_paused = False
        self.pause_reason = ""
        logger.info("熔断已重置，交易恢复")
        
    def get_status(self) -> dict:
        """获取风控状态"""
        return {
            'paused': self.is_paused,
            'circuit_breaker': self.is_circuit_breaker,
            'pause_reason': self.pause_reason,
            'error_count': self.error_count,
            'account_balance': self.account_balance,
            'daily_high': self.daily_high,
            'positions': self.positions,
            'orders_per_min': len(self.order_history)
        }

"""
AquaTrade - 日志模块
提供完整的交易日志、风控日志、错误日志记录
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler


class TradeLogger:
    """交易日志管理器"""
    
    def __init__(self, name="AquaTrade", log_dir="logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if self.logger.handlers:
            return
            
        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_fmt = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_fmt)
        self.logger.addHandler(console_handler)
        
        # 交易日志 - 按日期轮转
        today = datetime.now().strftime('%Y-%m-%d')
        trade_file = self.log_dir / f"trade_{today}.log"
        trade_handler = logging.FileHandler(trade_file, encoding='utf-8')
        trade_handler.setLevel(logging.INFO)
        trade_fmt = logging.Formatter(
            '%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        trade_handler.setFormatter(trade_fmt)
        self.logger.addHandler(trade_handler)
        
        # 风控日志 - 单独文件
        risk_file = self.log_dir / f"risk_{today}.log"
        self.risk_handler = logging.FileHandler(risk_file, encoding='utf-8')
        self.risk_handler.setLevel(logging.WARNING)
        risk_fmt = logging.Formatter(
            '%(asctime)s [RISK] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.risk_handler.setFormatter(risk_fmt)
        self.logger.addHandler(self.risk_handler)
        
        # 错误日志
        error_file = self.log_dir / f"error_{today}.log"
        error_handler = logging.FileHandler(error_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_fmt = logging.Formatter(
            '%(asctime)s [ERROR] - %(message)s\n%(exc_info)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_fmt)
        self.logger.addHandler(error_handler)
        
    def info(self, msg):
        """普通信息"""
        self.logger.info(msg)
        
    def debug(self, msg):
        """调试信息"""
        self.logger.debug(msg)
        
    def warning(self, msg):
        """警告信息"""
        self.logger.warning(msg)
        
    def error(self, msg, exc_info=False):
        """错误信息"""
        self.logger.error(msg, exc_info=exc_info)
        
    def trade(self, symbol, action, volume, price, order_id=None):
        """记录交易报单
        
        Args:
            symbol: 合约代码
            action: 动作（开多/开空/平多/平空）
            volume: 手数
            price: 价格
            order_id: 订单ID
        """
        msg = f"[TRADE] {action} | {symbol} | {volume}手 | 价格:{price}"
        if order_id:
            msg += f" | 订单:{order_id}"
        self.logger.info(msg)
        
    def fill(self, symbol, direction, volume, price, trade_id, order_id):
        """记录成交回报
        
        Args:
            symbol: 合约代码
            direction: 方向（买/卖）
            volume: 成交手数
            price: 成交价格
            trade_id: 成交编号
            order_id: 订单编号
        """
        msg = f"[FILL] {symbol} | {direction} | {volume}手 | 价:{price} | 成交:{trade_id} | 订单:{order_id}"
        self.logger.info(msg)
        
    def risk_trigger(self, risk_type, details):
        """记录风控触发
        
        Args:
            risk_type: 风控类型（仓位限制/回撤限制/价格偏离等）
            details: 详细信息
        """
        msg = f"[RISK TRIGGER] {risk_type} | {details}"
        self.logger.warning(msg)
        
    def position_update(self, symbol, long_pos, short_pos, available):
        """记录仓位更新
        
        Args:
            symbol: 合约代码
            long_pos: 多头持仓
            short_pos: 空头持仓
            available: 可用资金
        """
        msg = f"[POSITION] {symbol} | 多:{long_pos} | 空:{short_pos} | 可用:{available:.2f}"
        self.logger.info(msg)
        
    def strategy_signal(self, symbol, signal, price, ma_short, ma_long):
        """记录策略信号
        
        Args:
            symbol: 合约代码
            signal: 信号类型（BUY/SELL/HOLD）
            price: 当前价格
            ma_short: 短均线值
            ma_long: 长均线值
        """
        msg = f"[SIGNAL] {symbol} | {signal} | 价:{price} | MA5:{ma_short:.2f} | MA20:{ma_long:.2f}"
        self.logger.info(msg)
        
    def connection_status(self, status, details=""):
        """记录连接状态
        
        Args:
            status: 状态（已连接/断开/重连中）
            details: 详细信息
        """
        msg = f"[CONN] {status}"
        if details:
            msg += f" | {details}"
        self.logger.info(msg)
        
    def emergency(self, action, reason):
        """记录应急处置
        
        Args:
            action: 处置动作（平仓/暂停/熔断）
            reason: 原因
        """
        msg = f"[EMERGENCY] {action} | 原因:{reason}"
        self.logger.error(msg)


# 全局日志实例
logger = TradeLogger()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AquaTrade Pro - 股票交易模块
支持 QMT/Ptrade 等主流股票量化接口
"""

import time
import threading
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional
from datetime import datetime


class BaseTrader(ABC):
    """交易接口基类"""
    
    @abstractmethod
    def connect(self) -> bool:
        """连接交易服务器"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    def send_order(self, symbol: str, action: str, volume: int, price: float = 0) -> Optional[str]:
        """
        发送订单
        action: 'buy_open', 'sell_close', 'sell_open', 'buy_close'
        """
        pass
    
    @abstractmethod
    def query_position(self) -> Dict:
        """查询持仓"""
        pass
    
    @abstractmethod
    def query_account(self) -> Dict:
        """查询账户信息"""
        pass


class QMTTrader(BaseTrader):
    """
    QMT (迅投) 股票交易接口
    支持多家券商：华泰、中信、国泰君安等
    """
    
    def __init__(self, risk_manager=None, on_order_callback: Callable = None):
        self.risk_manager = risk_manager
        self.on_order_callback = on_order_callback
        self.connected = False
        self.xt_trader = None
        
        # 账号配置
        self.account_id = ""
        self.account_type = "STOCK"  # STOCK 或 CREDIT (两融)
        
    def connect(self) -> bool:
        """连接 QMT"""
        try:
            # 导入 QMT API
            # 注意：需要在 QMT 客户端的 Python 环境中运行
            from xtquant import xttrader
            from xtquant.xttype import StockAccount
            
            print("[QMT] 正在连接...")
            
            # 创建交易对象
            self.xt_trader = xttrader.XtQuantTrader(
                path="D:\\QMT\\userdata",  # QMT 安装路径
                session_id=123456  # 会话ID，随机即可
            )
            
            # 启动交易线程
            self.xt_trader.start()
            
            # 连接客户端
            connect_result = self.xt_trader.connect()
            if connect_result == 0:
                print("[QMT] 连接成功")
                self.connected = True
                
                # 订阅账号
                account = StockAccount(self.account_id, self.account_type)
                self.xt_trader.subscribe(account)
                
                return True
            else:
                print(f"[QMT] 连接失败，错误码: {connect_result}")
                return False
                
        except ImportError:
            print("[QMT] 错误: 未找到 xtquant 库")
            print("[QMT] 请在 QMT 客户端的 Python 环境中运行")
            return False
        except Exception as e:
            print(f"[QMT] 连接异常: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.xt_trader:
            self.xt_trader.stop()
            self.connected = False
            print("[QMT] 已断开")
    
    def send_order(self, symbol: str, action: str, volume: int, price: float = 0) -> Optional[str]:
        """
        发送股票订单
        
        action 映射:
        - 'buy_open' / 'buy' -> 买入
        - 'sell_close' / 'sell' -> 卖出
        """
        if not self.connected:
            print("[QMT] 未连接")
            return None
        
        try:
            from xtquant.xttype import StockAccount
            
            account = StockAccount(self.account_id, self.account_type)
            
            # 转换 action
            if action in ['buy_open', 'buy']:
                order_type = 23  # 买入
            elif action in ['sell_close', 'sell']:
                order_type = 24  # 卖出
            else:
                print(f"[QMT] 不支持的 action: {action}")
                return None
            
            # 下单
            # price_type: 5=限价, 11=市价
            price_type = 5 if price > 0 else 11
            
            order_id = self.xt_trader.order_stock(
                account=account,
                stock_code=symbol,  # 如 '000001.SZ'
                order_type=order_type,
                order_volume=volume,
                price_type=price_type,
                price=price
            )
            
            print(f"[QMT] 下单成功: {symbol} {action} {volume}股 @ {price}, 订单ID: {order_id}")
            return str(order_id)
            
        except Exception as e:
            print(f"[QMT] 下单失败: {e}")
            return None
    
    def query_position(self) -> Dict:
        """查询股票持仓"""
        if not self.connected:
            return {}
        
        try:
            from xtquant.xttype import StockAccount
            account = StockAccount(self.account_id, self.account_type)
            
            positions = self.xt_trader.query_stock_positions(account)
            result = {}
            for pos in positions:
                result[pos.stock_code] = {
                    'volume': pos.volume,  # 总持仓
                    'can_use_volume': pos.can_use_volume,  # 可用持仓
                    'open_price': pos.open_price,  # 成本价
                    'market_value': pos.market_value,  # 市值
                }
            return result
            
        except Exception as e:
            print(f"[QMT] 查询持仓失败: {e}")
            return {}
    
    def query_account(self) -> Dict:
        """查询账户资金"""
        if not self.connected:
            return {}
        
        try:
            from xtquant.xttype import StockAccount
            account = StockAccount(self.account_id, self.account_type)
            
            asset = self.xt_trader.query_stock_asset(account)
            return {
                'total_asset': asset.total_asset,  # 总资产
                'cash': asset.cash,  # 可用资金
                'market_value': asset.market_value,  # 持仓市值
            }
            
        except Exception as e:
            print(f"[QMT] 查询账户失败: {e}")
            return {}


class PTradeTrader(BaseTrader):
    """
    PTrade (恒生) 交易接口
    支持：华泰证券等
    """
    
    def __init__(self, risk_manager=None, on_order_callback: Callable = None):
        self.risk_manager = risk_manager
        self.on_order_callback = on_order_callback
        self.connected = False
        
    def connect(self) -> bool:
        """连接 PTrade"""
        try:
            # PTrade 是在券商提供的云端环境运行
            # 本地只是回测/研究，实盘在云端的 PTrade 环境里
            from hsstock import trade
            
            print("[PTrade] 正在连接...")
            # 实际连接代码根据券商提供的 API 文档
            
            self.connected = True
            print("[PTrade] 连接成功")
            return True
            
        except ImportError:
            print("[PTrade] 错误: 未找到 hsstock 库")
            print("[PTrade] 请在 PTrade 环境中运行")
            return False
    
    def disconnect(self):
        """断开连接"""
        self.connected = False
        print("[PTrade] 已断开")
    
    def send_order(self, symbol: str, action: str, volume: int, price: float = 0) -> Optional[str]:
        """下单"""
        # 根据 PTrade API 实现
        print(f"[PTrade] 下单: {symbol} {action} {volume}")
        return None
    
    def query_position(self) -> Dict:
        """查询持仓"""
        return {}
    
    def query_account(self) -> Dict:
        """查询账户"""
        return {}


class MockStockTrader(BaseTrader):
    """股票模拟交易器（测试用）"""
    
    def __init__(self, risk_manager=None, on_order_callback: Callable = None):
        self.risk_manager = risk_manager
        self.on_order_callback = on_order_callback
        self.connected = False
        self.positions = {}
        self.cash = 100000.0  # 初始资金10万
        self.market_value = 0.0
        
    def connect(self) -> bool:
        """模拟连接"""
        print("[股票模拟] 连接成功")
        print(f"[股票模拟] 初始资金: {self.cash:.2f}")
        self.connected = True
        return True
    
    def disconnect(self):
        """断开"""
        self.connected = False
        print("[股票模拟] 已断开")
    
    def send_order(self, symbol: str, action: str, volume: int, price: float = 0) -> Optional[str]:
        """模拟下单"""
        if not self.connected:
            return None
        
        order_id = f"MOCK_{int(time.time() * 1000)}"
        
        if action in ['buy', 'buy_open']:
            # 买入
            cost = price * volume
            if cost > self.cash:
                print(f"[股票模拟] 资金不足: 需要{cost:.2f}, 可用{self.cash:.2f}")
                return None
            
            self.cash -= cost
            if symbol in self.positions:
                # 加仓
                old_pos = self.positions[symbol]
                total_volume = old_pos['volume'] + volume
                total_cost = old_pos['cost'] + cost
                self.positions[symbol] = {
                    'volume': total_volume,
                    'cost': total_cost,
                    'price': total_cost / total_volume
                }
            else:
                # 新建仓
                self.positions[symbol] = {
                    'volume': volume,
                    'cost': cost,
                    'price': price
                }
            
            print(f"[股票模拟] 买入: {symbol} {volume}股 @ {price:.2f}, 花费{cost:.2f}")
            
        elif action in ['sell', 'sell_close']:
            # 卖出
            if symbol not in self.positions:
                print(f"[股票模拟] 没有持仓: {symbol}")
                return None
            
            pos = self.positions[symbol]
            if volume > pos['volume']:
                print(f"[股票模拟] 持仓不足: 可卖{pos['volume']}, 想卖{volume}")
                return None
            
            revenue = price * volume
            self.cash += revenue
            
            # 计算盈亏
            cost = pos['price'] * volume
            pnl = revenue - cost
            
            pos['volume'] -= volume
            pos['cost'] -= cost
            
            if pos['volume'] == 0:
                del self.positions[symbol]
            
            print(f"[股票模拟] 卖出: {symbol} {volume}股 @ {price:.2f}, 收入{revenue:.2f}, 盈亏{pnl:+.2f}")
        
        return order_id
    
    def query_position(self) -> Dict:
        """查询持仓"""
        return self.positions.copy()
    
    def query_account(self) -> Dict:
        """查询账户"""
        total_value = self.cash + sum(
            pos['volume'] * pos['price'] 
            for pos in self.positions.values()
        )
        return {
            'total_asset': total_value,
            'cash': self.cash,
            'market_value': total_value - self.cash,
            'positions': len(self.positions)
        }


# 交易器工厂
def create_trader(trader_type: str, **kwargs) -> BaseTrader:
    """
    创建交易器实例
    
    trader_type: 'ctp', 'qmt', 'ptrade', 'mock_stock', 'mock_futures'
    """
    traders = {
        'ctp': None,  # 从 trader.py 导入 CTPTrader
        'qmt': QMTTrader,
        'ptrade': PTradeTrader,
        'mock_stock': MockStockTrader,
        'mock_futures': None,  # 从 trader.py 导入 MockCTPTrader
    }
    
    trader_class = traders.get(trader_type)
    if trader_class is None:
        raise ValueError(f"未知的交易器类型: {trader_type}")
    
    return trader_class(**kwargs)

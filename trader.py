"""
AquaTrade - CTP交易核心
封装CTP接口，提供统一的交易接口
"""

import time
import threading
from typing import Callable, Dict, List, Optional
from datetime import datetime

import config
from logger import logger
from risk_manager import RiskManager


class MockCTPTrader:
    """模拟CTP交易器（用于无CTP环境测试）"""
    
    def __init__(self, risk_manager: RiskManager, on_order_callback: Callable = None):
        self.risk_manager = risk_manager
        self.on_order_callback = on_order_callback
        self.connected = False
        self.logged_in = False
        self.order_id_counter = 0
        self.positions: Dict[str, dict] = {}
        
    def connect(self) -> bool:
        """模拟连接"""
        logger.info("[模拟] 连接CTP...")
        time.sleep(0.5)
        self.connected = True
        logger.info("[模拟] 行情连接成功")
        
        time.sleep(0.5)
        self.logged_in = True
        logger.info("[模拟] 交易登录成功")
        
        # 初始化模拟持仓
        self.risk_manager.set_account_balance(100000.0)
        logger.info("[模拟] 账户权益: 100000.00")
        
        return True
        
    def disconnect(self):
        """断开连接"""
        self.connected = False
        self.logged_in = False
        logger.info("[模拟] 已断开连接")
        
    def subscribe(self, symbols: List[str]):
        """订阅行情"""
        logger.info(f"[模拟] 订阅行情: {symbols}")
        
    def send_order(self, symbol: str, direction: str, volume: int, price: float) -> str:
        """模拟报单"""
        # 风控检查
        passed, reason = self.risk_manager.check_pre_trade(symbol, direction, volume, price)
        if not passed:
            logger.warning(f"[模拟] 风控拦截: {reason}")
            return None
            
        self.order_id_counter += 1
        order_id = f"MOCK{self.order_id_counter:06d}"
        
        logger.trade(symbol, direction, volume, price, order_id)
        
        # 模拟成交（立即成交）
        if self.on_order_callback:
            trade_info = {
                'order_id': order_id,
                'symbol': symbol,
                'direction': direction,
                'volume': volume,
                'price': price,
                'trade_id': f"T{self.order_id_counter:06d}"
            }
            # 异步回调
            threading.Timer(0.1, lambda: self.on_order_callback(trade_info)).start()
            
        return order_id
        
    def cancel_order(self, order_id: str):
        """模拟撤单"""
        logger.info(f"[模拟] 撤单: {order_id}")
        
    def query_position(self, symbol: str = None) -> dict:
        """查询持仓"""
        return self.positions.get(symbol, {'long': 0, 'short': 0})
        
    def query_account(self) -> dict:
        """查询账户"""
        return {
            'balance': 100000.0,
            'available': 80000.0,
            'margin': 20000.0
        }


class CTPTrader:
    """CTP交易器（真实交易）
    
    实际使用时需要安装 vnpy_ctp：
    pip install vnpy_ctp
    """
    
    def __init__(self, risk_manager: RiskManager, on_order_callback: Callable = None):
        self.risk_manager = risk_manager
        self.on_order_callback = on_order_callback
        
        self.connected = False
        self.logged_in = False
        
        # CTP API实例（延迟初始化）
        self.md_api = None
        self.td_api = None
        
        # 数据缓存
        self.tick_callbacks: List[Callable] = []
        self.positions: Dict[str, dict] = {}
        self.orders: Dict[str, dict] = {}
        
        # 是否使用模拟模式
        self.use_mock = False
        
        self._try_import_vnpy()
        
    def _try_import_vnpy(self):
        """尝试导入vnpy"""
        try:
            from vnpy_ctp import CtpMdApi, CtpTdApi
            self.CtpMdApi = CtpMdApi
            self.CtpTdApi = CtpTdApi
            self.vnpy_available = True
            logger.info("vnpy_ctp 加载成功")
        except Exception as e:
            logger.warning(f"vnpy_ctp 加载失败: {e}")
            self.vnpy_available = False
            self.use_mock = True
            
    def set_mock_mode(self, enabled: bool = True):
        """设置模拟模式"""
        self.use_mock = enabled
        if enabled:
            logger.info("已切换到模拟交易模式")
        else:
            if not self.vnpy_available:
                logger.error("vnpy_ctp 未安装，无法切换到实盘模式")
                self.use_mock = True
            else:
                logger.info("已切换到实盘交易模式")
                
    def connect(self) -> bool:
        """连接CTP"""
        if self.use_mock or not self.vnpy_available:
            # 使用模拟器
            self.mock_trader = MockCTPTrader(self.risk_manager, self.on_order_callback)
            return self.mock_trader.connect()
            
        try:
            from vnpy.event import EventEngine
            
            # 初始化事件引擎
            self.event_engine = EventEngine()
            self.event_engine.start()
            
            # 初始化行情API
            self.md_api = self.CtpMdApi(self.event_engine)
            self.md_api.connect({
                '用户名': config.CTP_USER_ID,
                '密码': config.CTP_PASSWORD,
                '经纪商代码': config.CTP_BROKER_ID,
                '行情服务器': config.CTP_MD_ADDRESS,
                '授权编码': config.CTP_AUTH_CODE,
                '产品名称': config.CTP_APP_ID
            })
            
            # 初始化交易API
            self.td_api = self.CtpTdApi(self.event_engine)
            self.td_api.connect({
                '用户名': config.CTP_USER_ID,
                '密码': config.CTP_PASSWORD,
                '经纪商代码': config.CTP_BROKER_ID,
                '交易服务器': config.CTP_TD_ADDRESS,
                '授权编码': config.CTP_AUTH_CODE,
                '产品名称': config.CTP_APP_ID
            })
            
            # 注册回调
            self.event_engine.register('eTick', self._on_vnpy_tick)
            self.event_engine.register('eTrade', self._on_vnpy_trade)
            self.event_engine.register('eOrder', self._on_vnpy_order)
            self.event_engine.register('ePosition', self._on_vnpy_position)
            self.event_engine.register('eAccount', self._on_vnpy_account)
            
            self.connected = True
            logger.connection_status("已连接", "CTP连接成功")
            return True
            
        except Exception as e:
            logger.error(f"CTP连接失败: {e}", exc_info=True)
            logger.info("切换到模拟模式")
            self.use_mock = True
            self.mock_trader = MockCTPTrader(self.risk_manager, self.on_order_callback)
            return self.mock_trader.connect()
            
    def disconnect(self):
        """断开连接"""
        if self.use_mock and hasattr(self, 'mock_trader'):
            self.mock_trader.disconnect()
            return
            
        if self.md_api:
            self.md_api.close()
        if self.td_api:
            self.td_api.close()
        if hasattr(self, 'event_engine'):
            self.event_engine.stop()
            
        self.connected = False
        logger.connection_status("已断开")
        
    def subscribe(self, symbols: List[str]):
        """订阅行情"""
        if self.use_mock:
            self.mock_trader.subscribe(symbols)
            return
            
        if self.md_api:
            for symbol in symbols:
                self.md_api.subscribe(symbol)
                
    def send_order(self, symbol: str, direction: str, volume: int, price: float) -> str:
        """报单
        
        Args:
            symbol: 合约代码
            direction: buy_open, sell_open, buy_close, sell_close
            volume: 手数
            price: 价格
            
        Returns:
            订单ID
        """
        if self.use_mock:
            return self.mock_trader.send_order(symbol, direction, volume, price)
            
        # 风控检查
        passed, reason = self.risk_manager.check_pre_trade(symbol, direction, volume, price)
        if not passed:
            logger.warning(f"风控拦截: {reason}")
            return None
            
        if not self.td_api:
            logger.error("交易API未初始化")
            return None
            
        # 转换方向为CTP格式
        vnpy_direction, offset = self._convert_direction(direction)
        
        try:
            vt_orderid = self.td_api.send_order({
                'symbol': symbol,
                'direction': vnpy_direction,
                'offset': offset,
                'volume': volume,
                'price': price,
                'price_type': '限价' if price > 0 else '市价'
            })
            
            logger.trade(symbol, direction, volume, price, vt_orderid)
            return vt_orderid
            
        except Exception as e:
            logger.error(f"报单失败: {e}")
            self.risk_manager.report_error(f"报单失败: {e}")
            return None
            
    def cancel_order(self, order_id: str):
        """撤单"""
        if self.use_mock:
            self.mock_trader.cancel_order(order_id)
            return
            
        if self.td_api:
            self.td_api.cancel_order(order_id)
            
    def _convert_direction(self, direction: str) -> tuple:
        """转换方向"""
        # vnpy方向: Direction.LONG/SHORT
        # vnpy开平: Offset.OPEN/CLOSE/CLOSETODAY/CLOSEYESTERDAY
        
        if direction == 'buy_open':
            return '多', '开'
        elif direction == 'sell_open':
            return '空', '开'
        elif direction == 'buy_close':
            return '多', '平'
        elif direction == 'sell_close':
            return '空', '平'
        else:
            return '多', '开'
            
    def _on_vnpy_tick(self, event):
        """行情回调"""
        tick = event.data
        symbol = tick.symbol
        
        # 更新风控行情缓存
        self.risk_manager.update_quote(symbol, tick.bid_price_1, tick.ask_price_1, tick.last_price)
        
        # 回调给策略
        for callback in self.tick_callbacks:
            callback(symbol, tick.last_price)
            
    def _on_vnpy_trade(self, event):
        """成交回调"""
        trade = event.data
        logger.fill(
            trade.symbol,
            trade.direction,
            trade.volume,
            trade.price,
            trade.tradeid,
            trade.orderid
        )
        
        if self.on_order_callback:
            self.on_order_callback({
                'trade_id': trade.tradeid,
                'order_id': trade.orderid,
                'symbol': trade.symbol,
                'direction': trade.direction,
                'volume': trade.volume,
                'price': trade.price
            })
            
    def _on_vnpy_order(self, event):
        """报单回调"""
        order = event.data
        self.orders[order.orderid] = order
        
    def _on_vnpy_position(self, event):
        """持仓回调"""
        position = event.data
        self.positions[position.symbol] = {
            'long': position.long_pos,
            'short': position.short_pos,
            'yd_long': position.long_yd,
            'yd_short': position.short_yd
        }
        
    def _on_vnpy_account(self, event):
        """账户回调"""
        account = event.data
        self.risk_manager.set_account_balance(account.balance)
        
    def register_tick_callback(self, callback: Callable):
        """注册tick回调"""
        self.tick_callbacks.append(callback)
        
    def get_position(self, symbol: str) -> dict:
        """获取持仓"""
        if self.use_mock:
            return self.mock_trader.query_position(symbol)
        return self.positions.get(symbol, {'long': 0, 'short': 0})
        
    def close_all_positions(self):
        """一键平仓"""
        logger.emergency("一键平仓", "开始执行")
        
        for symbol, pos in self.positions.items():
            if pos.get('long', 0) > 0:
                self.send_order(symbol, 'sell_close', pos['long'], 0)
            if pos.get('short', 0) > 0:
                self.send_order(symbol, 'buy_close', pos['short'], 0)
                
        logger.emergency("一键平仓", "平仓指令已发送")

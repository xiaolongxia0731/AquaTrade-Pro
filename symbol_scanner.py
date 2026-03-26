#!/usr/bin/env python3
"""
AquaTrade Pro - 品种扫描器
自动扫描全市场，按多因子打分排序
"""

import pandas as pd
import threading
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass

from factor_engine import MultiFactorEngine
from data_provider import DataProvider


@dataclass
class ScanResult:
    """扫描结果"""
    symbol: str
    score: float
    rank: int
    momentum_score: float
    trend_score: float
    volatility_score: float
    volume_score: float
    last_price: float
    change_pct: float
    timestamp: datetime


class SymbolScanner:
    """
    品种扫描器
    
    功能：
    1. 定时扫描全市场品种
    2. 多因子打分排序
    3. 自动更新交易池
    4. 推送扫描结果
    """
    
    # 默认品种池（期货主力合约）
    DEFAULT_SYMBOLS = [
        # 黑色系
        "rb2505", "hc2505", "i2505", "j2505", "jm2505", "fg2505",
        # 有色金属
        "cu2505", "al2505", "zn2505", "ni2505", "sn2505", "ss2505",
        # 贵金属
        "au2506", "ag2506",
        # 能化
        "sc2505", "fu2505", "lu2505", "bu2505", "ta2505", "ma2505", 
        "pp2505", "l2505", "v2505", "eg2505", "eb2505",
        # 农产品
        "m2505", "y2505", "p2505", "oi2505", "cf2505", "sr2505", 
        "ru2505", "c2505", "cs2505", "a2505"
    ]
    
    def __init__(self, config_manager=None, factor_engine=None, data_provider=None):
        self.config = config_manager
        self.factor_engine = factor_engine or MultiFactorEngine(config_manager)
        self.data_provider = data_provider or DataProvider()
        
        # 从配置读取参数
        self.symbols = self._get_symbols_from_config()
        self.auto_scan = self.config.get('scanner.auto_scan', True) if self.config else True
        self.scan_interval = self.config.get('scanner.scan_interval', 300) if self.config else 300
        self.top_n = self.config.get('scanner.top_n', 5) if self.config else 5
        self.min_score = self.config.get('scanner.min_score', 60) if self.config else 60
        
        # 扫描结果
        self.last_results: List[ScanResult] = []
        self.last_scan_time: Optional[datetime] = None
        
        # 回调函数
        self.on_scan_complete: Optional[Callable] = None
        self.on_top_symbols_change: Optional[Callable] = None
        
        # 定时扫描线程
        self._scan_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # 缓存的行情数据
        self._price_cache: Dict[str, Dict] = {}
        
    def _get_symbols_from_config(self) -> List[str]:
        """从配置读取品种列表"""
        if self.config:
            return self.config.get('scanner.symbols_pool', self.DEFAULT_SYMBOLS)
        return self.DEFAULT_SYMBOLS
    
    def set_data_provider(self, provider: Callable):
        """
        设置数据提供器
        
        Args:
            provider: 函数，接收 symbol 和 period，返回 kline DataFrame
        """
        self._data_provider = provider
    
    def update_price(self, symbol: str, price: float, change_pct: float = 0):
        """更新实时价格（从行情回调接收）"""
        self._price_cache[symbol] = {
            'price': price,
            'change_pct': change_pct,
            'timestamp': time.time()
        }
    
    def scan(self, force: bool = False) -> List[ScanResult]:
        """
        执行一次扫描
        
        Args:
            force: 是否强制扫描（忽略缓存）
        
        Returns:
            排序后的品种列表
        """
        print(f"[SymbolScanner] 开始扫描 {len(self.symbols)} 个品种...")
        start_time = time.time()
        
        symbols_data = {}
        
        # 获取所有品种的历史数据
        for symbol in self.symbols:
            try:
                kline = self.data_provider.get_kline(symbol, period='1d', count=60)
                if kline is not None and len(kline) >= 20:
                    symbols_data[symbol] = kline
                    print(f"[SymbolScanner] {symbol}: {len(kline)} 条数据")
            except Exception as e:
                print(f"[SymbolScanner] 获取 {symbol} 数据失败: {e}")
                continue
        
        if not symbols_data:
            print("[SymbolScanner] 没有获取到有效数据")
            return []
        
        # 使用因子引擎计算得分
        ranked = self.factor_engine.rank_symbols(symbols_data)
        
        # 转换为 ScanResult
        results = []
        for item in ranked:
            symbol = item['symbol']
            details = item['details']
            
            # 获取实时价格
            price_info = self._price_cache.get(symbol, {})
            last_price = price_info.get('price', 0)
            change_pct = price_info.get('change_pct', 0)
            
            result = ScanResult(
                symbol=symbol,
                score=item['score'],
                rank=item['rank'],
                momentum_score=details.get('momentum', 50),
                trend_score=details.get('trend', 50),
                volatility_score=details.get('volatility', 50),
                volume_score=details.get('volume', 50),
                last_price=last_price,
                change_pct=change_pct,
                timestamp=datetime.now()
            )
            results.append(result)
        
        # 过滤最低得分
        results = [r for r in results if r.score >= self.min_score]
        
        # 只保留前N名
        self.last_results = results[:self.top_n]
        self.last_scan_time = datetime.now()
        
        elapsed = time.time() - start_time
        print(f"[SymbolScanner] 扫描完成，耗时 {elapsed:.2f}s，发现 {len(results)} 个符合条件的品种")
        
        # 触发回调
        if self.on_scan_complete:
            self.on_scan_complete(self.last_results)
        
        # 检查品种变化
        self._check_top_symbols_change()
        
        return self.last_results
    
    def _check_top_symbols_change(self):
        """检查排行榜品种是否变化"""
        # 这里可以实现品种变化时的通知逻辑
        if self.on_top_symbols_change and self.last_results:
            top_symbols = [r.symbol for r in self.last_results]
            self.on_top_symbols_change(top_symbols)
    
    def start_auto_scan(self):
        """启动自动扫描"""
        if self._scan_thread and self._scan_thread.is_alive():
            print("[SymbolScanner] 自动扫描已在运行")
            return
        
        self._stop_event.clear()
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()
        print(f"[SymbolScanner] 自动扫描已启动，间隔 {self.scan_interval}s")
    
    def stop_auto_scan(self):
        """停止自动扫描"""
        self._stop_event.set()
        if self._scan_thread:
            self._scan_thread.join(timeout=5)
        print("[SymbolScanner] 自动扫描已停止")
    
    def _scan_loop(self):
        """扫描循环"""
        while not self._stop_event.is_set():
            try:
                self.scan()
            except Exception as e:
                print(f"[SymbolScanner] 扫描异常: {e}")
            
            # 等待下一次扫描
            self._stop_event.wait(self.scan_interval)
    
    def get_top_symbols(self) -> List[ScanResult]:
        """获取上一次扫描的Top品种"""
        return self.last_results
    
    def get_symbol_score(self, symbol: str) -> Optional[float]:
        """获取指定品种的得分"""
        for r in self.last_results:
            if r.symbol == symbol:
                return r.score
        return None
    
    def update_config(self, **kwargs):
        """更新扫描配置"""
        if 'scan_interval' in kwargs:
            self.scan_interval = kwargs['scan_interval']
        if 'top_n' in kwargs:
            self.top_n = kwargs['top_n']
        if 'min_score' in kwargs:
            self.min_score = kwargs['min_score']
        if 'auto_scan' in kwargs:
            self.auto_scan = kwargs['auto_scan']
            if self.auto_scan:
                self.start_auto_scan()
            else:
                self.stop_auto_scan()
    
    def get_scan_summary(self) -> Dict:
        """获取扫描摘要"""
        return {
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'total_symbols': len(self.symbols),
            'qualified_count': len(self.last_results),
            'top_score': self.last_results[0].score if self.last_results else 0,
            'top_symbol': self.last_results[0].symbol if self.last_results else None,
            'auto_scan': self.auto_scan,
            'scan_interval': self.scan_interval
        }


class TradingPoolManager:
    """
    交易池管理器
    
    功能：
    1. 根据扫描结果动态调整交易品种
    2. 处理品种切换（平仓旧品种，开仓新品种）
    3. 持仓品种跟踪
    """
    
    def __init__(self, scanner: SymbolScanner, trader=None):
        self.scanner = scanner
        self.trader = trader
        
        self.current_pool: List[str] = []  # 当前交易池
        self.positions: Dict[str, Dict] = {}  # 持仓信息
        
        # 注册品种变化回调
        self.scanner.on_top_symbols_change = self._on_pool_change
        
    def _on_pool_change(self, new_symbols: List[str]):
        """交易池变化时的处理"""
        print(f"[TradingPoolManager] 交易池更新: {self.current_pool} -> {new_symbols}")
        
        # 找出需要平仓的品种（不在新交易池中）
        to_close = set(self.current_pool) - set(new_symbols)
        
        # 找出需要开仓的品种（新加入交易池的）
        to_open = set(new_symbols) - set(self.current_pool)
        
        # 执行调仓
        if to_close:
            self._close_positions(list(to_close))
        
        if to_open:
            self._open_positions(list(to_open))
        
        self.current_pool = new_symbols
    
    def _close_positions(self, symbols: List[str]):
        """平仓指定品种"""
        print(f"[TradingPoolManager] 平仓: {symbols}")
        # 调用交易接口平仓
        # if self.trader:
        #     for symbol in symbols:
        #         self.trader.close_all_positions(symbol)
    
    def _open_positions(self, symbols: List[str]):
        """开仓新品种"""
        print(f"[TradingPoolManager] 开仓: {symbols}")
        # 这里可以集成策略信号系统
    
    def get_current_pool(self) -> List[str]:
        """获取当前交易池"""
        return self.current_pool.copy()
    
    def is_in_pool(self, symbol: str) -> bool:
        """检查品种是否在交易池中"""
        return symbol in self.current_pool


# 测试代码
if __name__ == '__main__':
    import numpy as np
    
    # 模拟数据提供器
    def mock_data_provider(symbol, period='1d', count=60):
        np.random.seed(hash(symbol) % 2**32)
        
        # 模拟不同品种有不同的走势
        base_price = {'rb': 3500, 'cu': 70000, 'au': 500, 'sc': 500}.get(symbol[:2], 5000)
        trend = {'rb': 2, 'cu': -1, 'au': 0, 'sc': 1}.get(symbol[:2], 0)
        
        dates = pd.date_range(end=datetime.now(), periods=count, freq='D')
        close = base_price + np.cumsum(np.random.randn(count) * 10 + trend)
        
        df = pd.DataFrame({
            'open': close + np.random.randn(count) * 5,
            'high': close + np.abs(np.random.randn(count)) * 15,
            'low': close - np.abs(np.random.randn(count)) * 15,
            'close': close,
            'volume': np.random.randint(100000, 500000, count)
        }, index=dates)
        
        return df
    
    # 创建扫描器
    scanner = SymbolScanner()
    scanner.set_data_provider(mock_data_provider)
    
    # 扫描
    results = scanner.scan()
    
    print("\n扫描结果:")
    for r in results[:10]:
        print(f"{r.rank}. {r.symbol}: {r.score:.2f} "
              f"(动量{r.momentum_score:.1f}, 趋势{r.trend_score:.1f})")

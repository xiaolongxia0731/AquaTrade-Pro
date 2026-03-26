#!/usr/bin/env python3
"""
AquaTrade Pro - 数据提供器
支持多渠道：AKShare、CTP实时、本地缓存
"""

import pandas as pd
import numpy as np
import sqlite3
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
import akshare as ak


@dataclass
class KLineData:
    """K线数据"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    symbol: str


class LocalDataCache:
    """
    本地数据缓存（SQLite）
    
    功能：
    1. 存储历史K线数据
    2. 智能更新（只下载缺失部分）
    3. 多品种管理
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent / "data" / "market_data.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
        
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kline (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            
            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_time 
                ON kline(symbol, timestamp)
            """)
            
            conn.commit()
    
    def get_kline(self, symbol: str, start_date: str = None, 
                  end_date: str = None, limit: int = None) -> Optional[pd.DataFrame]:
        """从本地缓存获取K线"""
        query = "SELECT * FROM kline WHERE symbol = ?"
        params = [symbol]
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        
        query += " ORDER BY timestamp"
        
        if limit:
            query += f" LIMIT {limit}"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                return df
        except Exception as e:
            print(f"[LocalCache] 读取失败: {e}")
            return None
    
    def save_kline(self, symbol: str, df: pd.DataFrame):
        """保存K线到本地缓存"""
        if df.empty:
            return
        
        # 准备数据
        df_copy = df.copy()
        if df_copy.index.name == 'timestamp' or isinstance(df_copy.index, pd.DatetimeIndex):
            df_copy.reset_index(inplace=True)
        
        df_copy['symbol'] = symbol
        
        # 确保列名正确
        column_map = {
            'open': 'open', 'Open': 'open',
            'high': 'high', 'High': 'high',
            'low': 'low', 'Low': 'low',
            'close': 'close', 'Close': 'close',
            'volume': 'volume', 'Volume': 'volume',
            'timestamp': 'timestamp'
        }
        df_copy.rename(columns=column_map, inplace=True)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 使用 REPLACE 插入（如果存在则更新）
                for _, row in df_copy.iterrows():
                    conn.execute("""
                        INSERT OR REPLACE INTO kline 
                        (symbol, timestamp, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        symbol,
                        str(row['timestamp']),
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        int(row['volume'])
                    ))
                conn.commit()
        except Exception as e:
            print(f"[LocalCache] 保存失败: {e}")
    
    def get_last_update(self, symbol: str) -> Optional[str]:
        """获取品种最后更新时间"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT MAX(timestamp) FROM kline WHERE symbol = ?",
                    (symbol,)
                )
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except:
            return None
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT symbol, COUNT(*), MIN(timestamp), MAX(timestamp)
                    FROM kline
                    GROUP BY symbol
                """)
                stats = {}
                for row in cursor.fetchall():
                    stats[row[0]] = {
                        'count': row[1],
                        'start': row[2],
                        'end': row[3]
                    }
                return stats
        except:
            return {}


class AKShareProvider:
    """
    AKShare 数据接口
    
    免费、免注册的 Python 财经数据接口库
    支持期货、股票、基金等多种数据
    """
    
    # 期货代码映射（SimNow/CTP -> AKShare）
    FUTURE_MAP = {
        'rb': 'RB',      # 螺纹钢
        'hc': 'HC',      # 热卷
        'i': 'I',        # 铁矿石
        'j': 'J',        # 焦炭
        'jm': 'JM',      # 焦煤
        'fg': 'FG',      # 玻璃
        'cu': 'CU',      # 铜
        'al': 'AL',      # 铝
        'zn': 'ZN',      # 锌
        'ni': 'NI',      # 镍
        'sn': 'SN',      # 锡
        'au': 'AU',      # 黄金
        'ag': 'AG',      # 白银
        'sc': 'SC',      # 原油
        'fu': 'FU',      # 燃油
        'ta': 'TA',      # PTA
        'ma': 'MA',      # 甲醇
        'pp': 'PP',      # 聚丙烯
        'l': 'L',        # 塑料
        'v': 'V',        # PVC
        'm': 'M',        # 豆粕
        'y': 'Y',        # 豆油
        'p': 'P',        # 棕榈油
        'oi': 'OI',      # 菜油
        'cf': 'CF',      # 棉花
        'sr': 'SR',      # 白糖
        'ru': 'RU',      # 橡胶
        'c': 'C',        # 玉米
        'a': 'A',        # 豆一
    }
    
    @classmethod
    def symbol_to_akshare(cls, symbol: str) -> str:
        """
        转换 SimNow 合约代码到 AKShare 格式
        rb2505 -> RB2505
        """
        # 提取品种代码和年月
        # 处理 4位年份如 rb2505 或 2位 rb2505
        for prefix, ak_code in cls.FUTURE_MAP.items():
            if symbol.lower().startswith(prefix):
                # 提取后面的数字部分
                year_month = symbol[len(prefix):]
                # 如果是4位年份(2505)，转换为2位(05)
                if len(year_month) == 4:
                    year_month = year_month[2:]
                return f"{ak_code}{year_month}"
        return symbol.upper()
    
    @classmethod
    def get_futures_daily(cls, symbol: str, start_date: str = None, 
                          end_date: str = None) -> Optional[pd.DataFrame]:
        """
        获取期货日线数据
        
        Args:
            symbol: SimNow 合约代码如 'rb2505'
            start_date: 开始日期 '20240101'
            end_date: 结束日期 '20241231'
        
        Returns:
            DataFrame with columns: [open, high, low, close, volume]
        """
        try:
            ak_symbol = cls.symbol_to_akshare(symbol)
            
            # 设置默认日期
            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            if start_date is None:
                start = datetime.strptime(end_date, '%Y%m%d') - timedelta(days=365)
                start_date = start.strftime('%Y%m%d')
            
            print(f"[AKShare] 获取 {symbol} -> {ak_symbol} 日线数据 {start_date} ~ {end_date}")
            
            # 使用 AKShare 获取数据
            df = ak.futures_zh_daily_sina(symbol=ak_symbol)
            
            if df is None or df.empty:
                print(f"[AKShare] 未获取到 {symbol} 数据")
                return None
            
            # 标准化列名
            df.columns = [col.lower() for col in df.columns]
            
            # 转换日期
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.rename(columns={'date': 'timestamp'}, inplace=True)
            
            # 设置索引
            if 'timestamp' in df.columns:
                df.set_index('timestamp', inplace=True)
            
            # 筛选日期范围
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            # 确保必要的列存在
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                if col not in df.columns:
                    print(f"[AKShare] 警告: 缺少列 {col}")
            
            # 转换为数值类型
            for col in ['open', 'high', 'low', 'close']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            if 'volume' in df.columns:
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
            
            print(f"[AKShare] 获取成功: {len(df)} 条记录")
            return df[required_cols] if all(c in df.columns for c in required_cols) else df
            
        except Exception as e:
            print(f"[AKShare] 获取 {symbol} 失败: {e}")
            return None
    
    @classmethod
    def get_futures_realtime(cls, symbol: str) -> Optional[Dict]:
        """获取期货实时行情"""
        try:
            ak_symbol = cls.symbol_to_akshare(symbol)
            df = ak.futures_zh_realtime(symbol=ak_symbol)
            
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    'symbol': symbol,
                    'last_price': float(row.get('最新价', 0)),
                    'open': float(row.get('开盘价', 0)),
                    'high': float(row.get('最高价', 0)),
                    'low': float(row.get('最低价', 0)),
                    'volume': int(row.get('成交量', 0)),
                    'bid': float(row.get('买入', 0)),
                    'ask': float(row.get('卖出', 0)),
                    'timestamp': datetime.now()
                }
        except Exception as e:
            print(f"[AKShare] 获取实时行情失败: {e}")
        
        return None


class DataProvider:
    """
    统一数据提供器
    
    整合多个数据源，提供统一的K线获取接口
    优先级：本地缓存 -> AKShare -> CTP实时
    """
    
    def __init__(self, cache: LocalDataCache = None):
        self.cache = cache or LocalDataCache()
        self.akshare = AKShareProvider()
        
        # CTP实时数据回调
        self.ctp_tick_callback: Optional[Callable] = None
        self.ctp_kline_buffer: Dict[str, List] = {}
        
        # 实时价格缓存
        self.last_prices: Dict[str, Dict] = {}
        
    def get_kline(self, symbol: str, period: str = '1d', count: int = 60,
                  use_cache: bool = True, update_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        获取K线数据（统一接口）
        
        Args:
            symbol: 合约代码如 'rb2505'
            period: 周期 '1d'/'1h'/'5m'（目前只支持日线）
            count: 获取条数
            use_cache: 是否使用本地缓存
            update_cache: 是否更新本地缓存
        
        Returns:
            DataFrame or None
        """
        # 1. 尝试从本地缓存获取
        if use_cache:
            # 计算需要的日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=count * 2)  # 多取一些，以防节假日
            
            df_cached = self.cache.get_kline(
                symbol,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if df_cached is not None and len(df_cached) >= count:
                print(f"[DataProvider] 从缓存获取 {symbol}: {len(df_cached)} 条")
                return df_cached.tail(count)
            
            # 缓存数据不足，需要从网络获取
            last_update = self.cache.get_last_update(symbol)
            print(f"[DataProvider] 缓存数据不足，最后更新: {last_update}")
        
        # 2. 从 AKShare 获取
        df_new = self.akshare.get_futures_daily(symbol)
        
        if df_new is not None and not df_new.empty:
            # 保存到缓存
            if update_cache:
                self.cache.save_kline(symbol, df_new)
                print(f"[DataProvider] 已缓存 {symbol}: {len(df_new)} 条")
            
            # 返回需要的条数
            return df_new.tail(count) if len(df_new) > count else df_new
        
        # 3. 如果网络获取失败，返回缓存的部分数据
        if use_cache and df_cached is not None:
            print(f"[DataProvider] 网络获取失败，使用缓存数据: {len(df_cached)} 条")
            return df_cached
        
        return None
    
    def on_ctp_tick(self, symbol: str, tick: Dict):
        """
        接收CTP实时tick数据
        
        用于：
        1. 更新最新价格
        2. 合成实时K线
        """
        self.last_prices[symbol] = {
            'price': tick.get('last_price', 0),
            'bid': tick.get('bid_price_1', 0),
            'ask': tick.get('ask_price_1', 0),
            'volume': tick.get('volume', 0),
            'timestamp': tick.get('timestamp', datetime.now())
        }
        
        # 如果有回调，通知订阅者
        if self.ctp_tick_callback:
            self.ctp_tick_callback(symbol, tick)
    
    def get_last_price(self, symbol: str) -> Optional[Dict]:
        """获取最新价格"""
        return self.last_prices.get(symbol)
    
    def subscribe_ctp(self, symbols: List[str], callback: Callable):
        """订阅CTP实时数据"""
        self.ctp_tick_callback = callback
        # 实际订阅逻辑由外部CTP连接管理器处理
        print(f"[DataProvider] 订阅 {len(symbols)} 个品种的CTP实时数据")
    
    def update_all_symbols(self, symbols: List[str], force: bool = False):
        """
        批量更新所有品种数据
        
        Args:
            symbols: 品种列表
            force: 是否强制更新（忽略缓存）
        """
        print(f"[DataProvider] 开始更新 {len(symbols)} 个品种...")
        
        success_count = 0
        for symbol in symbols:
            try:
                if not force:
                    # 检查是否需要更新（超过1天未更新）
                    last_update = self.cache.get_last_update(symbol)
                    if last_update:
                        last_dt = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
                        if (datetime.now() - last_dt).days < 1:
                            print(f"[DataProvider] {symbol} 数据较新，跳过")
                            continue
                
                df = self.akshare.get_futures_daily(symbol)
                if df is not None and not df.empty:
                    self.cache.save_kline(symbol, df)
                    success_count += 1
                    
                time.sleep(0.5)  # 避免请求过快
                
            except Exception as e:
                print(f"[DataProvider] 更新 {symbol} 失败: {e}")
        
        print(f"[DataProvider] 更新完成: {success_count}/{len(symbols)} 成功")
        return success_count
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        return self.cache.get_cache_stats()


# 测试代码
if __name__ == '__main__':
    print("=" * 50)
    print("数据提供器测试")
    print("=" * 50)
    
    # 创建数据提供器
    provider = DataProvider()
    
    # 测试品种
    test_symbols = ['rb2505', 'cu2505', 'au2506']
    
    # 测试1：获取单品种数据
    print("\n1. 获取单品种数据")
    for symbol in test_symbols:
        df = provider.get_kline(symbol, count=30)
        if df is not None:
            print(f"✅ {symbol}: {len(df)} 条记录")
            print(f"   日期范围: {df.index[0]} ~ {df.index[-1]}")
        else:
            print(f"❌ {symbol}: 获取失败")
    
    # 测试2：批量更新
    print("\n2. 批量更新数据")
    provider.update_all_symbols(test_symbols)
    
    # 测试3：查看缓存统计
    print("\n3. 缓存统计")
    stats = provider.get_cache_info()
    for symbol, info in stats.items():
        print(f"📦 {symbol}: {info['count']} 条 ({info['start']} ~ {info['end']})")
    
    print("\n✅ 测试完成")

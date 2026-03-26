#!/usr/bin/env python3
"""
AquaTrade Pro - 实时配置管理器
支持热更新配置，无需重启
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Callable, List
from dataclasses import dataclass, asdict
from enum import Enum


class ConfigChangeEvent:
    """配置变更事件"""
    def __init__(self, key: str, old_value: Any, new_value: Any, timestamp: float = None):
        self.key = key
        self.old_value = old_value
        self.new_value = new_value
        self.timestamp = timestamp or time.time()


class ConfigManager:
    """
    实时配置管理器
    
    功能：
    1. 热更新配置（无需重启）
    2. 配置变更监听
    3. 自动持久化
    4. 配置版本控制
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.config_file = Path(__file__).parent / "config.json"
        self.config: Dict[str, Any] = {}
        self.listeners: Dict[str, List[Callable]] = {}
        self.global_listeners: List[Callable] = []
        self.history: List[Dict] = []  # 配置变更历史
        self.max_history = 100
        
        self._load_config()
        self._initialized = True
        
    def _load_config(self):
        """从文件加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"[ConfigManager] 加载配置失败: {e}")
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()
            self._save_config()
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            # === 多因子配置 ===
            "factors": {
                "momentum": {
                    "enabled": True,
                    "weight": 0.4,
                    "period": 20,
                    "description": "动量因子 - 近期涨幅排名"
                },
                "trend": {
                    "enabled": True,
                    "weight": 0.4,
                    "period_short": 5,
                    "period_long": 20,
                    "description": "趋势因子 - 均线多头排列"
                },
                "volatility": {
                    "enabled": False,
                    "weight": 0.2,
                    "period": 14,
                    "description": "波动率因子 - ATR波动率"
                },
                "volume": {
                    "enabled": False,
                    "weight": 0.0,
                    "period": 20,
                    "description": "成交量因子 - 放量突破"
                }
            },
            
            # === 品种扫描配置 ===
            "scanner": {
                "auto_scan": True,
                "scan_interval": 300,  # 秒
                "top_n": 5,  # 选前N个品种
                "min_score": 60,  # 最低得分
                "symbols_pool": [
                    "rb2505", "hc2505", "i2505", "j2505", "jm2505",
                    "cu2505", "al2505", "zn2505", "ni2505", "sn2505",
                    "au2506", "ag2506",
                    "sc2505", "fu2505",
                    "ta2505", "ma2505", "pp2505", "l2505", "v2505",
                    "m2505", "y2505", "p2505", "oi2505", "cf2505",
                    "sr2505", "ru2505"
                ]
            },
            
            # === 交易配置 ===
            "trading": {
                "max_positions": 3,  # 最大持仓品种数
                "position_size": 0.3,  # 每个品种仓位比例
                "rebalance_interval": 86400,  # 调仓间隔（秒）
                "auto_trade_top": True  # 自动交易排行榜品种
            },
            
            # === 原有CTP配置 ===
            "CTP_BROKER_ID": "9999",
            "CTP_USER_ID": "",
            "CTP_PASSWORD": "",
            "CTP_MD_ADDRESS": "180.168.146.187:10131",
            "CTP_TD_ADDRESS": "180.168.146.187:10130",
            "CTP_AUTH_CODE": "",
            "CTP_APP_ID": "simnow_client_test",
        }
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] 保存配置失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持嵌套路径，如 'factors.momentum.weight'）"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any, notify: bool = True) -> bool:
        """
        设置配置值（热更新）
        
        Args:
            key: 配置键（支持嵌套路径）
            value: 新值
            notify: 是否通知监听器
        
        Returns:
            bool: 是否成功
        """
        keys = key.split('.')
        config = self.config
        
        # 导航到目标位置
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        old_value = config.get(keys[-1])
        
        # 如果值没变，不触发更新
        if old_value == value:
            return True
        
        # 更新值
        config[keys[-1]] = value
        
        # 保存到文件
        self._save_config()
        
        # 记录历史
        self._add_history(key, old_value, value)
        
        # 通知监听器
        if notify:
            event = ConfigChangeEvent(key, old_value, value)
            self._notify_listeners(key, event)
        
        return True
    
    def update_factors(self, factor_name: str, settings: Dict) -> bool:
        """
        更新因子配置
        
        Args:
            factor_name: 因子名称（momentum/trend/volatility/volume）
            settings: 因子设置字典
        """
        key = f"factors.{factor_name}"
        return self.set(key, settings)
    
    def update_factor_weight(self, factor_name: str, weight: float) -> bool:
        """更新因子权重"""
        key = f"factors.{factor_name}.weight"
        return self.set(key, max(0.0, min(1.0, weight)))
    
    def update_factor_enabled(self, factor_name: str, enabled: bool) -> bool:
        """启用/禁用因子"""
        key = f"factors.{factor_name}.enabled"
        return self.set(key, enabled)
    
    def get_active_factors(self) -> Dict[str, Dict]:
        """获取所有启用的因子"""
        factors = self.get('factors', {})
        return {k: v for k, v in factors.items() if v.get('enabled', False)}
    
    def add_listener(self, key: str, callback: Callable):
        """
        添加配置变更监听器
        
        Args:
            key: 监听的配置键（如 'factors.momentum.weight'）
            callback: 回调函数，接收 ConfigChangeEvent 参数
        """
        if key not in self.listeners:
            self.listeners[key] = []
        self.listeners[key].append(callback)
    
    def add_global_listener(self, callback: Callable):
        """添加全局监听器（监听所有变更）"""
        self.global_listeners.append(callback)
    
    def remove_listener(self, key: str, callback: Callable):
        """移除监听器"""
        if key in self.listeners and callback in self.listeners[key]:
            self.listeners[key].remove(callback)
    
    def _notify_listeners(self, changed_key: str, event: ConfigChangeEvent):
        """通知监听器"""
        # 通知精确匹配的监听器
        if changed_key in self.listeners:
            for callback in self.listeners[changed_key]:
                try:
                    callback(event)
                except Exception as e:
                    print(f"[ConfigManager] 监听器回调失败: {e}")
        
        # 通知父级监听器（如监听 'factors.momentum' 的也会收到 'factors.momentum.weight' 的变更）
        parts = changed_key.split('.')
        for i in range(1, len(parts)):
            parent_key = '.'.join(parts[:-i])
            if parent_key in self.listeners:
                for callback in self.listeners[parent_key]:
                    try:
                        callback(event)
                    except Exception as e:
                        print(f"[ConfigManager] 父级监听器回调失败: {e}")
        
        # 通知全局监听器
        for callback in self.global_listeners:
            try:
                callback(event)
            except Exception as e:
                print(f"[ConfigManager] 全局监听器回调失败: {e}")
    
    def _add_history(self, key: str, old_value: Any, new_value: Any):
        """添加变更历史"""
        self.history.append({
            'timestamp': time.time(),
            'key': key,
            'old_value': old_value,
            'new_value': new_value
        })
        
        # 限制历史记录数量
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def get_history(self, limit: int = 50) -> List[Dict]:
        """获取配置变更历史"""
        return self.history[-limit:]
    
    def export_config(self, filepath: str) -> bool:
        """导出配置到文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] 导出配置失败: {e}")
            return False
    
    def import_config(self, filepath: str) -> bool:
        """从文件导入配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                new_config = json.load(f)
            
            # 合并配置
            old_config = self.config.copy()
            self.config.update(new_config)
            self._save_config()
            
            # 通知所有变更
            self._notify_all_changes(old_config, self.config)
            
            return True
        except Exception as e:
            print(f"[ConfigManager] 导入配置失败: {e}")
            return False
    
    def _notify_all_changes(self, old_config: Dict, new_config: Dict, prefix: str = ''):
        """递归通知所有配置变更"""
        for key in new_config:
            full_key = f"{prefix}.{key}" if prefix else key
            
            if key not in old_config:
                # 新增配置
                event = ConfigChangeEvent(full_key, None, new_config[key])
                self._notify_listeners(full_key, event)
            elif isinstance(new_config[key], dict) and isinstance(old_config.get(key), dict):
                # 递归处理嵌套字典
                self._notify_all_changes(old_config[key], new_config[key], full_key)
            elif old_config.get(key) != new_config[key]:
                # 值变更
                event = ConfigChangeEvent(full_key, old_config.get(key), new_config[key])
                self._notify_listeners(full_key, event)
    
    def reset_to_default(self):
        """重置为默认配置"""
        old_config = self.config.copy()
        self.config = self._get_default_config()
        self._save_config()
        self._notify_all_changes(old_config, self.config)


# 全局配置管理器实例
config_mgr = ConfigManager()


# 便捷函数
def get_config(key: str, default: Any = None) -> Any:
    """获取配置值"""
    return config_mgr.get(key, default)


def set_config(key: str, value: Any, notify: bool = True) -> bool:
    """设置配置值"""
    return config_mgr.set(key, value, notify)


# 测试代码
if __name__ == '__main__':
    # 测试配置管理器
    mgr = ConfigManager()
    
    # 注册监听器
    def on_momentum_weight_change(event):
        print(f"动量因子权重变更: {event.old_value} -> {event.new_value}")
    
    mgr.add_listener('factors.momentum.weight', on_momentum_weight_change)
    
    # 修改配置
    mgr.set('factors.momentum.weight', 0.5)
    
    # 获取配置
    print(f"当前动量权重: {mgr.get('factors.momentum.weight')}")
    print(f"所有启用的因子: {mgr.get_active_factors()}")

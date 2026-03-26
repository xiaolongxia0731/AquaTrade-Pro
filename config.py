# AquaTrade 配置文件

import os
import json
from pathlib import Path

# 配置文件路径
CONFIG_FILE = Path(__file__).parent / "config.json"

# 默认配置
DEFAULT_CONFIG = {
    # CTP 配置
    "CTP_BROKER_ID": "9999",
    "CTP_USER_ID": "your_user_id",
    "CTP_PASSWORD": "your_password",
    "CTP_MD_ADDRESS": "180.168.146.187:10131",
    "CTP_TD_ADDRESS": "180.168.146.187:10130",
    "CTP_AUTH_CODE": "",
    "CTP_APP_ID": "simnow_client_test",
    
    # 交易配置
    "TRADING_SYMBOLS": ["rb2505"],
    "CONTRACT_MULTIPLIER": {"rb": 10, "cu": 5, "al": 5, "au": 1000},
    "MARGIN_RATIO": 0.15,
    
    # 策略配置
    "MA_SHORT_PERIOD": 5,
    "MA_LONG_PERIOD": 20,
    "BAR_INTERVAL": "1m",
    
    # 风控配置
    "MAX_POSITION": 2,
    "MAX_DRAWDOWN": 0.02,
    "STOP_LOSS_TICKS": 10,
    "TAKE_PROFIT_TICKS": 0,
    "DAILY_PROFIT_TARGET": 0,  # 每日盈利目标（元），0=关闭
    "DAILY_LOSS_LIMIT": 0,     # 每日亏损上限（元），0=关闭
    "MAX_ORDERS_PER_MIN": 5,
    "MAX_CONSECUTIVE_ERRORS": 3,
    "PRICE_DEVIATION_LIMIT": 0.01,
    
    # 系统配置
    "LOG_LEVEL": "INFO",
    "LOG_RETAIN_DAYS": 30,
    "RECONNECT_INTERVAL": 5,
    "ORDER_TIMEOUT": 10,
    "PAPER_TRADING": False,
    "TRADING_MODE": "futures",  # futures, stock, mock
    
    # 通知配置
    "FEISHU_WEBHOOK": "",
    "DINGTALK_WEBHOOK": "",
    "ALERT_INTERVAL": 300,
}


def load_config():
    """从 JSON 文件加载配置"""
    config = DEFAULT_CONFIG.copy()
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                config.update(user_config)
            print(f"[Config] 已加载配置文件: {CONFIG_FILE}")
        except Exception as e:
            print(f"[Config] 加载配置文件失败: {e}")
    else:
        print(f"[Config] 配置文件不存在，使用默认配置: {CONFIG_FILE}")
    
    return config


def save_config(config_dict):
    """保存配置到 JSON 文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config] 保存配置文件失败: {e}")
        return False


# 加载配置
_user_config = load_config()

# 导出配置变量（兼容原有代码）
CTP_BROKER_ID = _user_config.get("CTP_BROKER_ID", os.getenv("CTP_BROKER_ID", "9999"))
CTP_USER_ID = _user_config.get("CTP_USER_ID", os.getenv("CTP_USER_ID", "your_user_id"))
CTP_PASSWORD = _user_config.get("CTP_PASSWORD", os.getenv("CTP_PASSWORD", "your_password"))
CTP_MD_ADDRESS = _user_config.get("CTP_MD_ADDRESS", os.getenv("CTP_MD_ADDRESS", "180.168.146.187:10131"))
CTP_TD_ADDRESS = _user_config.get("CTP_TD_ADDRESS", os.getenv("CTP_TD_ADDRESS", "180.168.146.187:10130"))
CTP_AUTH_CODE = _user_config.get("CTP_AUTH_CODE", os.getenv("CTP_AUTH_CODE", ""))
CTP_APP_ID = _user_config.get("CTP_APP_ID", os.getenv("CTP_APP_ID", "simnow_client_test"))

TRADING_SYMBOLS = _user_config.get("TRADING_SYMBOLS", ["rb2505"])
CONTRACT_MULTIPLIER = _user_config.get("CONTRACT_MULTIPLIER", {"rb": 10, "cu": 5, "al": 5, "au": 1000})
MARGIN_RATIO = _user_config.get("MARGIN_RATIO", 0.15)

MA_SHORT_PERIOD = _user_config.get("MA_SHORT_PERIOD", 5)
MA_LONG_PERIOD = _user_config.get("MA_LONG_PERIOD", 20)
BAR_INTERVAL = _user_config.get("BAR_INTERVAL", "1m")

MAX_POSITION = _user_config.get("MAX_POSITION", 2)
MAX_DRAWDOWN = _user_config.get("MAX_DRAWDOWN", 0.02)
STOP_LOSS_TICKS = _user_config.get("STOP_LOSS_TICKS", 10)
TAKE_PROFIT_TICKS = _user_config.get("TAKE_PROFIT_TICKS", 0)
DAILY_PROFIT_TARGET = _user_config.get("DAILY_PROFIT_TARGET", 0)
DAILY_LOSS_LIMIT = _user_config.get("DAILY_LOSS_LIMIT", 0)
MAX_ORDERS_PER_MIN = _user_config.get("MAX_ORDERS_PER_MIN", 5)
MAX_CONSECUTIVE_ERRORS = _user_config.get("MAX_CONSECUTIVE_ERRORS", 3)
PRICE_DEVIATION_LIMIT = _user_config.get("PRICE_DEVIATION_LIMIT", 0.01)

LOG_LEVEL = _user_config.get("LOG_LEVEL", "INFO")
LOG_RETAIN_DAYS = _user_config.get("LOG_RETAIN_DAYS", 30)
RECONNECT_INTERVAL = _user_config.get("RECONNECT_INTERVAL", 5)
ORDER_TIMEOUT = _user_config.get("ORDER_TIMEOUT", 10)
PAPER_TRADING = _user_config.get("PAPER_TRADING", False)
TRADING_MODE = _user_config.get("TRADING_MODE", "futures")  # futures, stock, mock

FEISHU_WEBHOOK = _user_config.get("FEISHU_WEBHOOK", os.getenv("FEISHU_WEBHOOK", ""))
DINGTALK_WEBHOOK = _user_config.get("DINGTALK_WEBHOOK", os.getenv("DINGTALK_WEBHOOK", ""))
ALERT_INTERVAL = _user_config.get("ALERT_INTERVAL", 300)


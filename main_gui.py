#!/usr/bin/env python3
"""
AquaTrade Pro - GUI 主程序
期货程序化交易系统 - 图形界面版
"""

import sys
import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, Optional

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit,
        QGroupBox, QGridLayout, QMessageBox, QDialog, QLineEdit,
        QComboBox, QSpinBox, QDoubleSpinBox, QTabWidget, QSplitter,
        QHeaderView, QSystemTrayIcon, QMenu, QAction, QStatusBar
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
    from PyQt5.QtGui import QIcon, QFont, QColor
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False
    print("PyQt5 not found, using tkinter...")

# 如果没有 PyQt5，使用 tkinter 作为备选
if not HAS_PYQT:
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, scrolledtext
        from tkinter.simpledialog import askstring
        HAS_TK = True
    except ImportError:
        HAS_TK = False

# 导入核心模块
import config
from logger import logger
from risk_manager import RiskManager
from strategy import StrategyManager

# 导入多因子系统
from config_manager import ConfigManager, config_mgr
from factor_engine import MultiFactorEngine
from symbol_scanner import SymbolScanner
from factor_panels import FactorConfigPanel, SymbolRankingPanel

# 导入新模块
try:
    from chart_widget import KLineChart
    from stock_trader import create_trader
    from ai_assistant import AIAssistant, AIAssistantPanel
    HAS_NEW_MODULES = True
except ImportError as e:
    HAS_NEW_MODULES = False
    print(f"[警告] 部分新模块导入失败: {e}")

# 导入更新模块
try:
    from updater import Updater, UpdateChecker
    HAS_UPDATER = True
except ImportError:
    HAS_UPDATER = False

# 版本号
APP_VERSION = "2.0.0"


class SignalEmitter(QObject):
    """用于线程间通信的信号发射器"""
    tick_signal = pyqtSignal(str, float)
    trade_signal = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(dict)


class ConfigDialog(QDialog):
    """配置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AquaTrade Pro - 系统配置")
        self.setMinimumSize(500, 600)
        self.setup_ui()
        self.load_config()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 创建标签页
        tabs = QTabWidget()
        
        # === CTP 配置页 ===
        ctp_tab = QWidget()
        ctp_layout = QGridLayout(ctp_tab)
        
        ctp_layout.addWidget(QLabel("期货公司代码:"), 0, 0)
        self.ctp_broker = QLineEdit()
        ctp_layout.addWidget(self.ctp_broker, 0, 1)
        
        ctp_layout.addWidget(QLabel("交易账号:"), 1, 0)
        self.ctp_user = QLineEdit()
        ctp_layout.addWidget(self.ctp_user, 1, 1)
        
        ctp_layout.addWidget(QLabel("密码:"), 2, 0)
        self.ctp_pass = QLineEdit()
        self.ctp_pass.setEchoMode(QLineEdit.Password)
        ctp_layout.addWidget(self.ctp_pass, 2, 1)
        
        ctp_layout.addWidget(QLabel("行情服务器:"), 3, 0)
        self.ctp_md = QLineEdit()
        ctp_layout.addWidget(self.ctp_md, 3, 1)
        
        ctp_layout.addWidget(QLabel("交易服务器:"), 4, 0)
        self.ctp_td = QLineEdit()
        ctp_layout.addWidget(self.ctp_td, 4, 1)
        
        ctp_layout.addWidget(QLabel("授权码:"), 5, 0)
        self.ctp_auth = QLineEdit()
        ctp_layout.addWidget(self.ctp_auth, 5, 1)
        
        ctp_layout.addWidget(QLabel("AppID:"), 6, 0)
        self.ctp_appid = QLineEdit()
        ctp_layout.addWidget(self.ctp_appid, 6, 1)
        
        # 模拟盘/实盘选择
        ctp_layout.addWidget(QLabel("环境:"), 7, 0)
        self.env_combo = QComboBox()
        self.env_combo.addItems(["SimNow 模拟盘", "实盘交易"])
        ctp_layout.addWidget(self.env_combo, 7, 1)
        
        tabs.addTab(ctp_tab, "CTP 配置")
        
        # === 交易模式页 ===
        mode_tab = QWidget()
        mode_layout = QGridLayout(mode_tab)
        
        mode_layout.addWidget(QLabel("交易模式:"), 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["期货 (CTP)", "股票 (QMT/Ptrade)", "模拟模式"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo, 0, 1)
        
        mode_layout.addWidget(QLabel("AI助手:"), 1, 0)
        self.ai_checkbox = QComboBox()
        self.ai_checkbox.addItems(["关闭", "手动模式", "自动模式"])
        mode_layout.addWidget(self.ai_checkbox, 1, 1)
        
        tabs.addTab(mode_tab, "交易模式")
        
        # === 交易配置页 ===
        trade_tab = QWidget()
        trade_layout = QGridLayout(trade_tab)
        
        trade_layout.addWidget(QLabel("交易品种:"), 0, 0)
        self.symbols = QLineEdit()
        self.symbols.setPlaceholderText("rb2505, cu2505 (逗号分隔)")
        trade_layout.addWidget(self.symbols, 0, 1)
        
        tabs.addTab(trade_tab, "交易品种")
        
        # === 策略配置页 ===
        strategy_tab = QWidget()
        strategy_layout = QGridLayout(strategy_tab)
        
        strategy_layout.addWidget(QLabel("短周期均线:"), 0, 0)
        self.ma_short = QSpinBox()
        self.ma_short.setRange(1, 60)
        self.ma_short.setValue(5)
        strategy_layout.addWidget(self.ma_short, 0, 1)
        
        strategy_layout.addWidget(QLabel("长周期均线:"), 1, 0)
        self.ma_long = QSpinBox()
        self.ma_long.setRange(5, 120)
        self.ma_long.setValue(20)
        strategy_layout.addWidget(self.ma_long, 1, 1)
        
        tabs.addTab(strategy_tab, "策略参数")
        
        # === 风控配置页 ===
        risk_tab = QWidget()
        risk_layout = QGridLayout(risk_tab)
        
        risk_layout.addWidget(QLabel("最大持仓手数:"), 0, 0)
        self.max_pos = QSpinBox()
        self.max_pos.setRange(1, 100)
        self.max_pos.setValue(2)
        risk_layout.addWidget(self.max_pos, 0, 1)
        
        risk_layout.addWidget(QLabel("单日最大回撤(%)"), 1, 0)
        self.max_dd = QDoubleSpinBox()
        self.max_dd.setRange(0.1, 50.0)
        self.max_dd.setValue(2.0)
        self.max_dd.setDecimals(1)
        risk_layout.addWidget(self.max_dd, 1, 1)
        
        risk_layout.addWidget(QLabel("止损跳数:"), 2, 0)
        self.stop_loss = QSpinBox()
        self.stop_loss.setRange(1, 100)
        self.stop_loss.setValue(10)
        risk_layout.addWidget(self.stop_loss, 2, 1)
        
        risk_layout.addWidget(QLabel("每分钟最大报单:"), 3, 0)
        self.max_orders = QSpinBox()
        self.max_orders.setRange(1, 100)
        self.max_orders.setValue(5)
        risk_layout.addWidget(self.max_orders, 3, 1)
        
        risk_layout.addWidget(QLabel("每日盈利目标(元):"), 4, 0)
        self.daily_profit_target = QSpinBox()
        self.daily_profit_target.setRange(0, 1000000)
        self.daily_profit_target.setValue(0)
        self.daily_profit_target.setSingleStep(100)
        self.daily_profit_target.setSpecialValueText("关闭")
        risk_layout.addWidget(self.daily_profit_target, 4, 1)
        
        risk_layout.addWidget(QLabel("每日亏损上限(元):"), 5, 0)
        self.daily_loss_limit = QSpinBox()
        self.daily_loss_limit.setRange(0, 1000000)
        self.daily_loss_limit.setValue(0)
        self.daily_loss_limit.setSingleStep(100)
        self.daily_loss_limit.setSpecialValueText("关闭")
        risk_layout.addWidget(self.daily_loss_limit, 5, 1)
        
        tabs.addTab(risk_tab, "风控参数")
        
        # === AI 配置页 ===
        ai_tab = QWidget()
        ai_layout = QGridLayout(ai_tab)
        
        ai_layout.addWidget(QLabel("AI 监控:"), 0, 0)
        self.ai_enabled = QComboBox()
        self.ai_enabled.addItems(["关闭", "开启"])
        ai_layout.addWidget(self.ai_enabled, 0, 1)
        
        ai_layout.addWidget(QLabel("自动执行:"), 1, 0)
        self.ai_auto = QComboBox()
        self.ai_auto.addItems(["手动确认", "自动执行"])
        ai_layout.addWidget(self.ai_auto, 1, 1)
        
        ai_layout.addWidget(QLabel("网关地址:"), 2, 0)
        self.ai_gateway = QLineEdit("http://localhost:10489")
        ai_layout.addWidget(self.ai_gateway, 2, 1)
        
        tabs.addTab(ai_tab, "AI助手")
        
        layout.addWidget(tabs)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("保存配置")
        self.btn_save.clicked.connect(self.save_config)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
    def load_config(self):
        """加载当前配置"""
        self.ctp_broker.setText(config.CTP_BROKER_ID)
        self.ctp_user.setText(config.CTP_USER_ID)
        self.ctp_pass.setText(config.CTP_PASSWORD)
        self.ctp_md.setText(config.CTP_MD_ADDRESS)
        self.ctp_td.setText(config.CTP_TD_ADDRESS)
        self.ctp_auth.setText(config.CTP_AUTH_CODE)
        self.ctp_appid.setText(config.CTP_APP_ID)
        self.symbols.setText(", ".join(config.TRADING_SYMBOLS))
        self.ma_short.setValue(config.MA_SHORT_PERIOD)
        self.ma_long.setValue(config.MA_LONG_PERIOD)
        self.max_pos.setValue(config.MAX_POSITION)
        self.max_dd.setValue(config.MAX_DRAWDOWN * 100)
        self.stop_loss.setValue(config.STOP_LOSS_TICKS)
        self.max_orders.setValue(config.MAX_ORDERS_PER_MIN)
        self.daily_profit_target.setValue(getattr(config, 'DAILY_PROFIT_TARGET', 0))
        self.daily_loss_limit.setValue(getattr(config, 'DAILY_LOSS_LIMIT', 0))
        
        # 加载交易模式
        mode_map = {"futures": 0, "stock": 1, "mock": 2}
        current_mode = getattr(config, 'TRADING_MODE', 'futures')
        self.mode_combo.setCurrentIndex(mode_map.get(current_mode, 0))
        
        # 判断环境
        if "simnow" in config.CTP_MD_ADDRESS.lower() or "9999" in config.CTP_BROKER_ID:
            self.env_combo.setCurrentIndex(0)
        else:
            self.env_combo.setCurrentIndex(1)
    
    def _on_mode_changed(self, index):
        """交易模式切换"""
        modes = ["futures", "stock", "mock"]
        print(f"[配置] 切换到模式: {modes[index]}")
        self.stop_loss.setValue(config.STOP_LOSS_TICKS)
        self.max_orders.setValue(config.MAX_ORDERS_PER_MIN)
        
        # 判断环境
        if "simnow" in config.CTP_MD_ADDRESS.lower() or "9999" in config.CTP_BROKER_ID:
            self.env_combo.setCurrentIndex(0)
        else:
            self.env_combo.setCurrentIndex(1)
            
    def save_config(self):
        """保存配置到文件"""
        # 获取交易模式
        modes = ["futures", "stock", "mock"]
        current_mode = modes[self.mode_combo.currentIndex()]
        
        # 先读取现有配置（保留多因子等其他配置）
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        cfg = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            except:
                cfg = {}
        
        # 更新配置字段
        cfg.update({
            "CTP_BROKER_ID": self.ctp_broker.text(),
            "CTP_USER_ID": self.ctp_user.text(),
            "CTP_PASSWORD": self.ctp_pass.text(),
            "CTP_MD_ADDRESS": self.ctp_md.text(),
            "CTP_TD_ADDRESS": self.ctp_td.text(),
            "CTP_AUTH_CODE": self.ctp_auth.text(),
            "CTP_APP_ID": self.ctp_appid.text(),
            "TRADING_SYMBOLS": [s.strip() for s in self.symbols.text().split(",") if s.strip()],
            "MA_SHORT_PERIOD": self.ma_short.value(),
            "MA_LONG_PERIOD": self.ma_long.value(),
            "MAX_POSITION": self.max_pos.value(),
            "MAX_DRAWDOWN": self.max_dd.value() / 100,
            "STOP_LOSS_TICKS": self.stop_loss.value(),
            "MAX_ORDERS_PER_MIN": self.max_orders.value(),
            "DAILY_PROFIT_TARGET": self.daily_profit_target.value(),
            "DAILY_LOSS_LIMIT": self.daily_loss_limit.value(),
            "TRADING_MODE": current_mode,
        })
        
        # 保存到 JSON 文件
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "成功", "配置已保存，重启软件后生效")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {e}")


class AquaTradeMainWindow(QMainWindow):
    """AquaTrade Pro 主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AquaTrade Pro - 程序化交易系统 v{APP_VERSION}")
        self.setMinimumSize(1400, 900)
        
        # 初始化核心组件
        self.risk_manager = RiskManager()
        self.strategy_manager = StrategyManager()
        self.trading_active = False
        self.trading_mode = "futures"
        
        # 模拟持仓（用于演示）
        self.mock_positions = {}  # {symbol: {'volume': 0, 'avg_price': 0}}
        self.mock_equity = 100000.0  # 模拟账户权益
        self.mock_available = 80000.0  # 模拟可用资金
        self.mock_margin = 20000.0  # 模拟保证金
        self.daily_pnl = 0.0  # 当日累计盈亏
        self.initial_equity = 100000.0  # 初始权益（用于计算当日盈亏）
        
        # 初始化 AI 助手
        if HAS_NEW_MODULES:
            self.ai_assistant = AIAssistant(enabled=False, auto_mode=False)
            self.ai_assistant.execute_callback = self._execute_ai_advice
        else:
            self.ai_assistant = None
        
        # 初始化多因子系统
        from data_provider import DataProvider
        self.data_provider = DataProvider()
        self.factor_engine = MultiFactorEngine(config_mgr)
        self.symbol_scanner = SymbolScanner(config_mgr, self.factor_engine, self.data_provider)
        self.config_manager = config_mgr
        
        # 信号发射器
        self.signals = SignalEmitter()
        self.signals.tick_signal.connect(self.on_tick_update)
        self.signals.trade_signal.connect(self.on_trade_update)
        self.signals.log_signal.connect(self.on_log_message)
        self.signals.status_signal.connect(self.on_status_update)
        
        self.setup_ui()
        self.setup_timer()
        self.check_first_run()
        
    def setup_ui(self):
        """设置用户界面"""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        # 左侧区域
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # === 账户信息 ===
        account_box = QGroupBox("账户信息")
        account_layout = QGridLayout(account_box)
        
        self.lbl_equity = QLabel("权益: --")
        self.lbl_available = QLabel("可用: --")
        self.lbl_margin = QLabel("保证金: --")
        self.lbl_pnl = QLabel("当日盈亏: --")
        
        account_layout.addWidget(self.lbl_equity, 0, 0)
        account_layout.addWidget(self.lbl_available, 0, 1)
        account_layout.addWidget(self.lbl_margin, 1, 0)
        account_layout.addWidget(self.lbl_pnl, 1, 1)
        
        left_layout.addWidget(account_box)
        
        # === 风控状态 ===
        risk_box = QGroupBox("风控状态")
        risk_layout = QGridLayout(risk_box)
        
        self.lbl_risk_status = QLabel("状态: 正常")
        self.lbl_risk_status.setStyleSheet("color: green; font-weight: bold;")
        self.lbl_error_count = QLabel("错误计数: 0")
        self.lbl_order_rate = QLabel("报单频率: 0/5")
        
        risk_layout.addWidget(self.lbl_risk_status, 0, 0)
        risk_layout.addWidget(self.lbl_error_count, 0, 1)
        risk_layout.addWidget(self.lbl_order_rate, 1, 0)
        
        left_layout.addWidget(risk_box)
        
        # === 持仓信息 ===
        position_box = QGroupBox("持仓信息")
        position_layout = QVBoxLayout(position_box)
        
        self.position_table = QTableWidget()
        self.position_table.setColumnCount(5)
        self.position_table.setHorizontalHeaderLabels(["品种", "方向", "数量", "均价", "盈亏"])
        self.position_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        position_layout.addWidget(self.position_table)
        
        left_layout.addWidget(position_box)
        
        # === 操作按钮 ===
        btn_box = QGroupBox("操作")
        btn_layout = QGridLayout(btn_box)
        
        # 模式切换
        self.mode_label = QLabel("模式: 期货")
        btn_layout.addWidget(self.mode_label, 0, 0, 1, 2)
        
        self.btn_start = QPushButton("▶ 开始交易")
        self.btn_start.setStyleSheet("background-color: #52c41a; color: white; font-size: 14px; padding: 10px;")
        self.btn_start.clicked.connect(self.toggle_trading)
        
        self.btn_close = QPushButton("⚠ 一键平仓")
        self.btn_close.setStyleSheet("background-color: #ff4d4f; color: white;")
        self.btn_close.clicked.connect(self.close_all_positions)
        
        self.btn_config = QPushButton("⚙ 系统设置")
        self.btn_config.clicked.connect(self.open_config)
        
        btn_layout.addWidget(self.btn_start, 0, 0, 1, 2)
        btn_layout.addWidget(self.btn_close, 1, 0)
        btn_layout.addWidget(self.btn_config, 1, 1)
        
        # 检查更新按钮
        if HAS_UPDATER:
            self.btn_update = QPushButton("🔄 检查更新")
            self.btn_update.setStyleSheet("background-color: #1890ff; color: white;")
            self.btn_update.clicked.connect(self.check_update_manual)
            btn_layout.addWidget(self.btn_update, 2, 0, 1, 2)
            
        # 版本标签
        self.lbl_version = QLabel(f"版本: v{APP_VERSION}")
        self.lbl_version.setStyleSheet("color: #999; font-size: 10px;")
        btn_layout.addWidget(self.lbl_version, 3, 0, 1, 2, Qt.AlignCenter)
        
        left_layout.addWidget(btn_box)
        
        main_layout.addWidget(left_panel, 1)
        
        # 右侧区域
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # === 行情面板 ===
        quote_box = QGroupBox("实时行情")
        quote_layout = QVBoxLayout(quote_box)
        
        # 创建标签页
        quote_tabs = QTabWidget()
        
        # K线图表页
        kline_tab = QWidget()
        kline_layout = QVBoxLayout(kline_tab)
        if HAS_NEW_MODULES:
            self.kline_chart = KLineChart()
            kline_layout.addWidget(self.kline_chart)
        else:
            self.quote_table = QTableWidget()
            self.quote_table.setColumnCount(4)
            self.quote_table.setHorizontalHeaderLabels(["品种", "最新价", "涨跌", "时间"])
            self.quote_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            kline_layout.addWidget(self.quote_table)
        quote_tabs.addTab(kline_tab, "📈 K线图")
        
        # 多因子配置页
        factor_tab = FactorConfigPanel(self.config_manager)
        factor_tab.factor_changed.connect(self._on_factor_changed)
        quote_tabs.addTab(factor_tab, "⚙️ 多因子配置")
        
        # 品种排行榜页
        ranking_tab = SymbolRankingPanel(self.symbol_scanner)
        ranking_tab.symbol_selected.connect(self._on_symbol_selected)
        quote_tabs.addTab(ranking_tab, "🏆 品种排行")
        
        quote_layout.addWidget(quote_tabs)
        right_layout.addWidget(quote_box)
        
        # === 交易日志 ===
        log_box = QGroupBox("交易日志")
        log_layout = QVBoxLayout(log_box)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # 兼容旧版 PyQt5
        try:
            self.log_text.setMaximumBlockCount(500)
        except AttributeError:
            pass  # 旧版本不支持，忽略
        log_layout.addWidget(self.log_text)
        
        right_layout.addWidget(log_box)
        
        main_layout.addWidget(right_panel, 2)
        
        # 状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪 - 请配置 CTP 账号后开始交易")
        
    def setup_timer(self):
        """设置定时器"""
        # 状态更新定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # 每秒更新
        
    def check_first_run(self):
        """检查是否首次运行"""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        if not os.path.exists(config_path):
            reply = QMessageBox.question(
                self, 
                "首次运行", 
                "检测到首次运行，是否现在配置 CTP 账号？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.open_config()
            else:
                self.log_message("请配置 CTP 账号后再开始交易")
                
    def open_config(self):
        """打开配置对话框"""
        dialog = ConfigDialog(self)
        dialog.exec_()
        
    def toggle_trading(self):
        """切换交易状态"""
        if not self.trading_active:
            # 开始交易
            self.start_trading()
        else:
            # 暂停交易
            self.pause_trading()
            
    def start_trading(self):
        """开始交易"""
        # 检查配置
        if config.CTP_USER_ID == 'your_user_id' or not config.CTP_USER_ID:
            QMessageBox.warning(self, "警告", "请先配置 CTP 账号")
            self.open_config()
            return
        
        self.trading_active = True
        self.btn_start.setText("⏸ 暂停交易")
        self.btn_start.setStyleSheet("background-color: #faad14; color: white; font-size: 14px; padding: 10px;")
        
        # 判断是否使用真实行情
        use_real = self._try_connect_real()
        
        if use_real:
            self.statusBar.showMessage("交易中 - 已连接 SimNow 真实行情")
            self.log_message("=== 交易开始 (真实行情模式) ===")
        else:
            self.statusBar.showMessage("交易中 - 演示模式 (本地模拟行情)")
            self.log_message("=== 交易开始 (演示模式) ===")
            self.log_message("⚠️ 提示：当前为本地模拟行情，如需真实行情请配置有效 CTP 账号")
        
        # 启动策略线程
        self.strategy_thread = threading.Thread(
            target=self.run_strategy_real if use_real else self.run_strategy_mock, 
            daemon=True
        )
        self.strategy_thread.start()
        
    def pause_trading(self):
        """暂停交易"""
        self.trading_active = False
        self.risk_manager.pause("手动暂停")
        self.btn_start.setText("▶ 开始交易")
        self.btn_start.setStyleSheet("background-color: #52c41a; color: white; font-size: 14px; padding: 10px;")
        self.statusBar.showMessage("已暂停 - 策略停止开新仓")
        self.log_message("=== 交易暂停 ===")
        
    def close_all_positions(self):
        """一键平仓"""
        reply = QMessageBox.warning(
            self,
            "确认平仓",
            "确定要平掉所有持仓吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.log_message("执行一键平仓...")
            # TODO: 调用实际平仓逻辑
            QMessageBox.information(self, "完成", "平仓指令已发送")
            
    def _try_connect_real(self) -> bool:
        """尝试连接真实行情，检查交易时间"""
        from datetime import datetime, time as dt_time
        
        # 检查交易时间
        now = datetime.now()
        current_time = now.time()
        weekday = now.weekday()  # 0=周一, 6=周日
        
        # 期货交易日：周一到周五
        if weekday >= 5:  # 周六周日
            self.log_message("⚠️ 今天是周末，期货市场休市")
            return False
        
        # 检查是否在交易时段
        # 日盘：09:00-11:30, 13:30-15:00
        # 夜盘：21:00-23:00 (部分品种到02:30)
        day_session_morning = (dt_time(9, 0) <= current_time <= dt_time(11, 30))
        day_session_afternoon = (dt_time(13, 30) <= current_time <= dt_time(15, 0))
        night_session = (dt_time(21, 0) <= current_time <= dt_time(23, 0))
        
        if not (day_session_morning or day_session_afternoon or night_session):
            self.log_message(f"⚠️ 当前时间 {current_time.strftime('%H:%M')} 非交易时段")
            self.log_message("   日盘：09:00-11:30, 13:30-15:00")
            self.log_message("   夜盘：21:00-23:00")
            return False
        
        # 在交易时间内，尝试连接真实行情
        try:
            from trader import CTPTrader
            self.real_trader = CTPTrader(self.risk_manager, self.on_trade_update)
            
            # 检查是否使用了模拟模式（vnpy_ctp 未安装时会自动切换）
            if hasattr(self.real_trader, 'use_mock') and self.real_trader.use_mock:
                self.log_message("⚠️ vnpy_ctp 未安装，无法连接真实行情")
                self.log_message("💡 提示: 运行 'pip install vnpy_ctp' 安装")
                return False
            
            if self.real_trader.connect():
                self.real_trader.subscribe(config.TRADING_SYMBOLS)
                self.real_trader.register_tick_callback(self.on_tick_update)
                self.log_message("✅ 已连接 SimNow 行情服务器")
                return True
            else:
                self.log_message("❌ 连接 SimNow 失败，切换到演示模式")
                return False
        except ImportError:
            self.log_message("❌ vnpy_ctp 未安装，切换到演示模式")
            self.log_message("   安装命令: pip install vnpy_ctp")
            return False
        except Exception as e:
            self.log_message(f"❌ 连接失败: {e}")
            return False
    
    def run_strategy_real(self):
        """真实行情模式 - 通过CTP回调驱动"""
        self.log_message("📡 正在接收真实行情...")
        # 真实行情由 CTP 回调驱动，这里只保持线程存活
        while self.trading_active:
            time.sleep(1)
    
    def run_strategy_mock(self):
        """演示模式 - 本地模拟行情"""
        import random
        import traceback
        
        base_prices = {"rb2505": 3500.0}
        
        # 初始化模拟账户
        self.mock_equity = 100000.0
        self.mock_available = 80000.0
        self.mock_margin = 20000.0
        self.daily_pnl = 0.0
        self.initial_equity = 100000.0
        self.risk_manager.set_account_balance(self.mock_equity)
        self.log_message(f"[演示账户] 初始权益: {self.mock_equity:.2f}")
        
        try:
            while self.trading_active:
                for symbol in config.TRADING_SYMBOLS:
                    try:
                        # 模拟行情
                        change = random.uniform(-5, 5)
                        base_prices[symbol] = max(3000, base_prices.get(symbol, 3500) + change)
                        price = round(base_prices[symbol], 2)
                        
                        self.signals.tick_signal.emit(symbol, price)
                    except Exception as e:
                        error_msg = f"策略循环错误: {str(e)}"
                        self.signals.log_signal.emit(error_msg)
                        traceback.print_exc()
                        
                time.sleep(2)
        except Exception as e:
            error_msg = f"策略线程崩溃: {str(e)}"
            self.signals.log_signal.emit(error_msg)
            traceback.print_exc()
            
    def on_tick_update(self, symbol: str, price: float):
        """行情更新回调"""
        # 更新K线图
        timestamp = int(datetime.now().timestamp() * 1000)
        open_p = price - 2
        high = price + 3
        low = price - 3
        self.kline_chart.update_kline(timestamp, open_p, high, low, price)
        
        # 驱动策略
        if self.trading_active:
            # 确保策略已添加（使用短周期，更快产生信号）
            if symbol not in self.strategy_manager.strategies:
                from strategy import DualMAStrategy
                self.strategy_manager.strategies[symbol] = DualMAStrategy(
                    symbol, short_period=3, long_period=8
                )
            
            result = self.strategy_manager.on_tick(symbol, price)
            if result:
                signal, action, volume = result
                msg = f"策略信号: {symbol} {action} {volume}手 @ {price:.2f}"
                self.signals.log_signal.emit(msg)
                
                # 执行模拟交易
                self._execute_mock_trade(symbol, action, volume, price)
            else:
                # 显示策略计算状态（调试用）
                strategy = self.strategy_manager.get_strategy(symbol)
                if strategy and len(strategy.prices) >= strategy.long_period:
                    status = strategy.get_status()
                    if status['data_points'] >= status.get('long_period', 20):
                        # 每10个点显示一次MA值
                        if status['data_points'] % 10 == 0:
                            self.signals.log_signal.emit(
                                f"MA状态: MA5={status['ma_short']:.2f}, MA20={status['ma_long']:.2f}, "
                                f"持仓={status['position']}, 数据点={status['data_points']}"
                            )

    def _check_daily_limits(self) -> tuple:
        """检查每日盈亏限制
        
        Returns:
            (bool, str) - (是否允许交易, 提示信息)
        """
        daily_profit_target = getattr(config, 'DAILY_PROFIT_TARGET', 0)
        daily_loss_limit = getattr(config, 'DAILY_LOSS_LIMIT', 0)
        
        if daily_profit_target > 0 and self.daily_pnl >= daily_profit_target:
            return False, f"🎯 每日盈利目标 {daily_profit_target}元 已达成，停止交易"
            
        if daily_loss_limit > 0 and self.daily_pnl <= -daily_loss_limit:
            return False, f"🛑 每日亏损上限 {daily_loss_limit}元 已触发，停止交易"
            
        return True, ""

    def _execute_mock_trade(self, symbol: str, action: str, volume: int, price: float):
        """执行模拟交易"""
        if action == 'hold' or volume <= 0:
            return
        
        # 检查每日限制（开仓时检查）
        if 'open' in action:
            can_trade, msg = self._check_daily_limits()
            if not can_trade:
                self.log_message(msg)
                # 如果达到限制，平掉所有持仓（落袋为安）
                self._close_all_positions(symbol, price)
                return
        
        # 获取合约乘数（默认10，螺纹钢）
        multiplier = config.CONTRACT_MULTIPLIER.get(symbol[:2], 10)
        
        # 获取当前持仓
        pos = self.mock_positions.get(symbol, {'volume': 0, 'avg_price': 0})
        current_volume = pos['volume']
        avg_price = pos['avg_price']
        
        pnl = 0  # 默认无盈亏
        
        # 计算新持仓和盈亏
        if 'buy_open' in action:
            # 开多 - 买入
            new_volume = current_volume + volume
            new_avg = (current_volume * avg_price + volume * price) / new_volume if new_volume > 0 else 0
            
        elif 'sell_open' in action:
            # 开空 - 卖出开仓
            new_volume = current_volume - volume
            new_avg = avg_price if current_volume != 0 else price
            # 如果有空仓，更新均价
            if current_volume < 0:
                total_volume = abs(current_volume) + volume
                new_avg = (abs(current_volume) * avg_price + volume * price) / total_volume
                
        elif 'buy_close' in action:
            # 平空 - 买入平仓（计算盈亏）
            close_volume = min(volume, abs(current_volume)) if current_volume < 0 else 0
            new_volume = current_volume + volume
            
            if current_volume < 0 and avg_price > 0:
                # 空仓盈利 = (开仓价 - 平仓价) * 手数 * 乘数
                pnl = (avg_price - price) * close_volume * multiplier
            new_avg = avg_price if new_volume < 0 else 0
            
        elif 'sell_close' in action:
            # 平多 - 卖出平仓（计算盈亏）
            close_volume = min(volume, current_volume) if current_volume > 0 else 0
            new_volume = current_volume - close_volume
            
            if current_volume > 0 and avg_price > 0:
                # 多仓盈利 = (平仓价 - 开仓价) * 手数 * 乘数
                pnl = (price - avg_price) * close_volume * multiplier
            new_avg = avg_price if new_volume > 0 else 0
        else:
            return
        
        # 更新持仓
        self.mock_positions[symbol] = {'volume': new_volume, 'avg_price': new_avg}
        
        # 更新策略持仓状态
        self.strategy_manager.update_position(symbol, new_volume, new_avg)
        
        # 累计当日盈亏（仅平仓时产生盈亏）
        if pnl != 0:
            self.daily_pnl += pnl
            # 更新权益
            self.mock_equity += pnl
            self.mock_available += pnl
        
        # 记录交易
        trade_msg = f"💰 模拟成交: {symbol} {action} {volume}手 @ {price:.2f}"
        if pnl != 0:
            trade_msg += f" 盈亏: {pnl:+.2f}"
        self.signals.log_signal.emit(trade_msg)
        
        # 更新持仓显示
        self._update_position_display()
        
    def _update_position_display(self):
        """更新持仓表格显示"""
        self.position_table.setRowCount(0)
        for symbol, pos in self.mock_positions.items():
            if pos['volume'] != 0:
                row = self.position_table.rowCount()
                self.position_table.insertRow(row)
                
                direction = "多" if pos['volume'] > 0 else "空"
                volume = abs(pos['volume'])
                
                self.position_table.setItem(row, 0, QTableWidgetItem(symbol))
                self.position_table.setItem(row, 1, QTableWidgetItem(direction))
                self.position_table.setItem(row, 2, QTableWidgetItem(str(volume)))
                self.position_table.setItem(row, 3, QTableWidgetItem(f"{pos['avg_price']:.2f}"))
                self.position_table.setItem(row, 4, QTableWidgetItem("--"))
        
    def on_trade_update(self, trade_info: dict):
        """交易更新回调"""
        symbol = trade_info.get('symbol', 'Unknown')
        action = trade_info.get('action', 'Unknown')
        volume = trade_info.get('volume', 0)
        price = trade_info.get('price', 0)
        msg = f"交易成交: {symbol} {action} {volume}手 @ {price}"
        self.log_message(msg)
                
    def update_quote_table(self, symbol: str, price: float):
        """更新行情表格"""
        # 查找或创建行
        row = -1
        for i in range(self.quote_table.rowCount()):
            if self.quote_table.item(i, 0) and self.quote_table.item(i, 0).text() == symbol:
                row = i
                break
                
        if row == -1:
            row = self.quote_table.rowCount()
            self.quote_table.insertRow(row)
            
        change = price - 3500  # 假设昨收3500
        change_pct = (change / 3500) * 100
        
        self.quote_table.setItem(row, 0, QTableWidgetItem(symbol))
        self.quote_table.setItem(row, 1, QTableWidgetItem(f"{price:.2f}"))
        
        change_item = QTableWidgetItem(f"{change:+.2f} ({change_pct:+.2f}%)")
        if change > 0:
            change_item.setForeground(QColor("red"))
        else:
            change_item.setForeground(QColor("green"))
        self.quote_table.setItem(row, 2, change_item)
        
        self.quote_table.setItem(row, 3, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
        
    def _execute_ai_advice(self, action, *args):
        """执行 AI 建议的操作"""
        if action == 'close_all':
            self.log_message("[AI] 执行一键平仓")
            self.close_all_positions()
        elif action == 'pause':
            self.log_message("[AI] 执行暂停交易")
            self.pause_trading()
        elif action == 'reduce':
            symbol, volume = args
            self.log_message(f"[AI] 建议减仓 {symbol} {volume}手")
            # TODO: 实现减仓逻辑

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止 AI 助手
        if self.ai_assistant:
            self.ai_assistant.stop()
        
        # 停止交易
        if self.trading_active:
            self.stop()
        
        event.accept()
        
    def on_log_message(self, message: str):
        """日志消息回调"""
        self.log_message(message)
        
    def log_message(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    def on_status_update(self, status: dict):
        """状态更新回调"""
        status_type = status.get('type', '')
        
        if status_type == 'update_check':
            self._handle_update_check_result(status['result'])
        elif status_type == 'update_check_error':
            self.btn_update.setEnabled(True)
            self.btn_update.setText("🔄 检查更新")
            QMessageBox.warning(self, "错误", f"检查更新失败: {status.get('error', '未知错误')}")
        elif status_type == 'update_progress':
            self._handle_update_progress(status['value'])
        elif status_type == 'update_download':
            self._handle_download_result(status['result'])
        elif status_type == 'update_download_error':
            self.btn_update.setEnabled(True)
            self.btn_update.setText("🔄 检查更新")
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.close()
            QMessageBox.warning(self, "错误", f"下载更新失败: {status.get('error', '未知错误')}")
        
    def update_status(self):
        """定时更新状态"""
        # 更新风控状态
        risk = self.risk_manager.get_status()
        
        if risk['circuit_breaker']:
            self.lbl_risk_status.setText("状态: 熔断")
            self.lbl_risk_status.setStyleSheet("color: red; font-weight: bold;")
        elif risk['paused']:
            self.lbl_risk_status.setText("状态: 暂停")
            self.lbl_risk_status.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.lbl_risk_status.setText("状态: 正常")
            self.lbl_risk_status.setStyleSheet("color: green; font-weight: bold;")
            
        self.lbl_error_count.setText(f"错误计数: {risk['error_count']}")
        self.lbl_order_rate.setText(f"报单频率: {risk['orders_per_min']}/{config.MAX_ORDERS_PER_MIN}")
        
        # 更新账户信息 - 使用模拟账户数据或风控数据
        if self.trading_active and hasattr(self, 'mock_equity'):
            # 使用模拟账户数据
            equity = self.mock_equity
            available = self.mock_available
            margin = self.mock_margin
            pnl = self.daily_pnl
        else:
            # 使用风控数据（实盘或初始值）
            equity = risk.get('account_balance', 0) or self.mock_equity
            available = self.mock_available
            margin = self.mock_margin
            pnl = self.daily_pnl
        
        self.lbl_equity.setText(f"权益: {equity:.2f}")
        self.lbl_available.setText(f"可用: {available:.2f}")
        self.lbl_margin.setText(f"保证金: {margin:.2f}")
        
        # 当日盈亏显示（带颜色）
        pnl_text = f"当日盈亏: {pnl:+.2f}"
        self.lbl_pnl.setText(pnl_text)
        if pnl > 0:
            self.lbl_pnl.setStyleSheet("color: red; font-weight: bold;")  # 红色表示盈利（期货惯例）
        elif pnl < 0:
            self.lbl_pnl.setStyleSheet("color: green; font-weight: bold;")  # 绿色表示亏损
        else:
            self.lbl_pnl.setStyleSheet("")
        
        # 同步更新风控模块的账户余额
        if equity > 0:
            self.risk_manager.set_account_balance(equity)
        
    def check_update_on_startup(self):
        """启动时检查更新（静默）"""
        if not HAS_UPDATER:
            return
        
        try:
            checker = UpdateChecker(APP_VERSION)
            result = checker.check_silently()
            
            if result:
                self.log_message(f"[更新] 发现新版本: v{result['latest_version']}")
                self.log_message(f"[更新] 请点击'检查更新'按钮获取更新")
        except:
            pass  # 静默失败，不打扰用户
    
    def check_update_manual(self):
        """手动检查更新 - 异步线程"""
        if not HAS_UPDATER:
            QMessageBox.warning(self, "提示", "更新模块未加载")
            return
        
        self.log_message("[更新] 正在检查更新...")
        self.btn_update.setEnabled(False)
        self.btn_update.setText("🔄 检查中...")
        
        # 在后台线程执行检查
        def check_worker():
            try:
                updater = Updater(APP_VERSION)
                result = updater.check_update()
                # 发送信号到主线程
                self.signals.status_signal.emit({
                    'type': 'update_check',
                    'result': result
                })
            except Exception as e:
                self.signals.status_signal.emit({
                    'type': 'update_check_error',
                    'error': str(e)
                })
        
        thread = threading.Thread(target=check_worker, daemon=True)
        thread.start()
    
    def _handle_update_check_result(self, result):
        """处理更新检查结果"""
        self.btn_update.setEnabled(True)
        self.btn_update.setText("🔄 检查更新")
        
        if result.get('error'):
            QMessageBox.warning(self, "检查更新失败", result['error'])
            return
        
        if not result['has_update']:
            QMessageBox.information(self, "检查更新", 
                f"当前已是最新版本: v{APP_VERSION}")
            return
        
        # 有新版本
        msg = f"""发现新版本!

当前版本: v{APP_VERSION}
最新版本: v{result['latest_version']}

更新内容:
{result['changelog']}

是否立即下载更新?"""
        
        reply = QMessageBox.question(self, "发现新版本", msg,
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # 保存版本信息供下载使用
            self.latest_version_info = result
            self.download_update()
    
    def download_update(self):
        """下载更新 - 异步线程"""
        self.log_message("[更新] 开始下载更新包...")
        self.btn_update.setEnabled(False)
        self.btn_update.setText("⬇️ 下载中...")
        
        # 创建进度对话框
        from PyQt5.QtWidgets import QProgressDialog
        self.progress_dialog = QProgressDialog("正在下载更新...", "取消", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.NonModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
        
        # 下载进度回调
        def progress_callback(p):
            self.signals.status_signal.emit({
                'type': 'update_progress',
                'value': p
            })
        
        # 在后台线程执行下载
        def download_worker():
            try:
                updater = Updater(APP_VERSION)
                # 使用最新版本号下载
                latest_version = self.latest_version_info.get('latest_version', '1.9.1')
                result_download = updater.download_update(version=latest_version)
                self.signals.status_signal.emit({
                    'type': 'update_download',
                    'result': result_download
                })
            except Exception as e:
                self.signals.status_signal.emit({
                    'type': 'update_download_error',
                    'error': str(e)
                })
        
        thread = threading.Thread(target=download_worker, daemon=True)
        thread.start()
    
    def _handle_update_progress(self, value):
        """更新进度条"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setValue(value)
    
    def _handle_download_result(self, result):
        """处理下载结果"""
        self.btn_update.setEnabled(True)
        self.btn_update.setText("🔄 检查更新")
        
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
        
        if not result['success']:
            QMessageBox.warning(self, "下载失败", result['message'])
            return
        
        # 下载成功
        msg = """更新包下载完成!

请在关闭软件后，双击运行 run_update.bat 完成更新。

注意:
1. 更新前会自动备份 config.json
2. 请确保关闭 AquaTrade 后再运行更新脚本
3. 更新完成后会自动启动新版本

是否现在关闭软件并开始更新?"""
        
        reply = QMessageBox.question(self, "准备更新", msg,
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            # 应用更新并退出
            try:
                updater = Updater(APP_VERSION)
                result = updater.apply_update()
                if result['success']:
                    self.log_message("[更新] 正在启动更新程序...")
                    QApplication.quit()
                else:
                    QMessageBox.warning(self, "更新失败", result['message'])
            except Exception as e:
                QMessageBox.warning(self, "错误", f"启动更新失败: {str(e)}")
        else:
            self.log_message("[更新] 已下载，稍后请手动运行 run_update.bat")

    def _on_factor_changed(self, factor_name, settings):
        """因子配置变更回调"""
        self.log_message(f"[多因子] {factor_name} 配置已更新")
        self.log_message(f"[多因子] 活跃因子: {list(self.config_manager.get_active_factors().keys())}")
    
    def _on_symbol_selected(self, symbol):
        """品种选择回调"""
        self.log_message(f"[多因子] 选中品种: {symbol}")
        # 可以在这里切换K线图显示的品种
        if hasattr(self, 'kline_chart'):
            self.log_message(f"[多因子] 切换K线图到 {symbol}")


def main():
    """主函数"""
    # 尝试加载配置文件
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_cfg = json.load(f)
                # 更新 config 模块
                for key, value in user_cfg.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
            print(f"已加载配置文件: {config_path}")
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    if not HAS_PYQT:
        print("错误: 未找到 PyQt5，请先安装: pip install PyQt5")
        print("或使用命令行版本: python main.py")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 设置应用字体
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)
    
    window = AquaTradeMainWindow()
    
    # 启动 AI 助手（如果启用）
    if window.ai_assistant:
        window.ai_assistant.start()
    
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
AquaTrade Pro - 多因子配置面板
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QGroupBox, QGridLayout, QSpinBox,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QProgressBar, QSplitter, QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor

import pandas as pd
from config_manager import ConfigManager, ConfigChangeEvent
from factor_engine import MultiFactorEngine
from symbol_scanner import SymbolScanner, ScanResult


class FactorConfigPanel(QWidget):
    """因子配置面板 - 支持实时调整"""
    
    factor_changed = pyqtSignal(str, dict)  # 因子变更信号
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.factor_engine = MultiFactorEngine(config_manager)
        
        self._init_ui()
        self._load_config()
        self._setup_listeners()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("⚙️ 多因子配置")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        
        # 说明文字
        desc = QLabel("调整因子权重和参数，更改将实时生效（下一根K线）")
        desc.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(desc)
        
        # 因子列表
        self.factor_widgets = {}
        
        factors = ['momentum', 'trend', 'volatility', 'volume']
        factor_names = {
            'momentum': '动量因子',
            'trend': '趋势因子', 
            'volatility': '波动率因子',
            'volume': '成交量因子'
        }
        factor_desc = {
            'momentum': '近期涨幅排名，追涨策略',
            'trend': '均线多头排列，趋势跟踪',
            'volatility': 'ATR波动率，低波动高分',
            'volume': '放量上涨，资金关注度'
        }
        
        for factor in factors:
            group = QGroupBox(factor_names.get(factor, factor))
            group.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
            """)
            
            g_layout = QGridLayout(group)
            
            # 启用/禁用
            enabled_cb = QCheckBox("启用")
            enabled_cb.setObjectName(f"{factor}_enabled")
            g_layout.addWidget(enabled_cb, 0, 0)
            
            # 描述
            desc_label = QLabel(factor_desc.get(factor, ''))
            desc_label.setStyleSheet("color: #666; font-size: 11px;")
            g_layout.addWidget(desc_label, 0, 1, 1, 2)
            
            # 权重滑块
            g_layout.addWidget(QLabel("权重:"), 1, 0)
            weight_slider = QSlider(Qt.Horizontal)
            weight_slider.setRange(0, 100)
            weight_slider.setObjectName(f"{factor}_weight_slider")
            weight_slider.valueChanged.connect(
                lambda v, f=factor: self._on_weight_changed(f, v)
            )
            g_layout.addWidget(weight_slider, 1, 1)
            
            weight_label = QLabel("0%")
            weight_label.setObjectName(f"{factor}_weight_label")
            weight_label.setMinimumWidth(40)
            g_layout.addWidget(weight_label, 1, 2)
            
            # 参数设置（展开/收起）
            if factor == 'momentum':
                g_layout.addWidget(QLabel("周期:"), 2, 0)
                period_spin = QSpinBox()
                period_spin.setRange(5, 60)
                period_spin.setObjectName(f"{factor}_period")
                period_spin.valueChanged.connect(
                    lambda v, f=factor: self._on_param_changed(f, 'period', v)
                )
                g_layout.addWidget(period_spin, 2, 1)
                
            elif factor == 'trend':
                g_layout.addWidget(QLabel("短周期:"), 2, 0)
                short_spin = QSpinBox()
                short_spin.setRange(3, 20)
                short_spin.setObjectName(f"{factor}_short")
                short_spin.valueChanged.connect(
                    lambda v, f=factor: self._on_param_changed(f, 'period_short', v)
                )
                g_layout.addWidget(short_spin, 2, 1)
                
                g_layout.addWidget(QLabel("长周期:"), 3, 0)
                long_spin = QSpinBox()
                long_spin.setRange(10, 60)
                long_spin.setObjectName(f"{factor}_long")
                long_spin.valueChanged.connect(
                    lambda v, f=factor: self._on_param_changed(f, 'period_long', v)
                )
                g_layout.addWidget(long_spin, 3, 1)
                
            elif factor == 'volatility':
                g_layout.addWidget(QLabel("ATR周期:"), 2, 0)
                period_spin = QSpinBox()
                period_spin.setRange(5, 30)
                period_spin.setObjectName(f"{factor}_period")
                period_spin.valueChanged.connect(
                    lambda v, f=factor: self._on_param_changed(f, 'period', v)
                )
                g_layout.addWidget(period_spin, 2, 1)
            
            layout.addWidget(group)
            
            # 保存引用
            self.factor_widgets[factor] = {
                'enabled': enabled_cb,
                'weight_slider': weight_slider,
                'weight_label': weight_label,
            }
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        
        self.btn_apply = QPushButton("⚡ 应用更改")
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px 20px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_apply.clicked.connect(self._apply_changes)
        btn_layout.addWidget(self.btn_apply)
        
        self.btn_reset = QPushButton("🔄 重置默认")
        self.btn_reset.clicked.connect(self._reset_default)
        btn_layout.addWidget(self.btn_reset)
        
        layout.addLayout(btn_layout)
        
        # 状态提示
        self.status_label = QLabel("配置已加载")
        self.status_label.setStyleSheet("color: #2196F3; font-size: 12px;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
    def _load_config(self):
        """从配置加载"""
        factors = self.config.get('factors', {})
        
        for factor_name, settings in factors.items():
            if factor_name not in self.factor_widgets:
                continue
                
            widgets = self.factor_widgets[factor_name]
            
            # 启用状态
            enabled = settings.get('enabled', False)
            widgets['enabled'].setChecked(enabled)
            
            # 权重
            weight = settings.get('weight', 0.0)
            widgets['weight_slider'].setValue(int(weight * 100))
            widgets['weight_label'].setText(f"{int(weight * 100)}%")
            
            # 参数
            if factor_name == 'momentum':
                period = settings.get('period', 20)
                spin = self.findChild(QSpinBox, f"{factor_name}_period")
                if spin:
                    spin.setValue(period)
                    
            elif factor_name == 'trend':
                short = settings.get('period_short', 5)
                long = settings.get('period_long', 20)
                spin_short = self.findChild(QSpinBox, f"{factor_name}_short")
                spin_long = self.findChild(QSpinBox, f"{factor_name}_long")
                if spin_short:
                    spin_short.setValue(short)
                if spin_long:
                    spin_long.setValue(long)
                    
            elif factor_name == 'volatility':
                period = settings.get('period', 14)
                spin = self.findChild(QSpinBox, f"{factor_name}_period")
                if spin:
                    spin.setValue(period)
    
    def _setup_listeners(self):
        """设置配置变更监听"""
        self.config.add_global_listener(self._on_config_changed)
    
    def _on_config_changed(self, event: ConfigChangeEvent):
        """配置变更回调"""
        if 'factors' in event.key:
            self.status_label.setText(f"✅ 配置已更新: {event.key}")
            self._load_config()
    
    def _on_weight_changed(self, factor: str, value: int):
        """权重滑块变化"""
        weight = value / 100.0
        self.factor_widgets[factor]['weight_label'].setText(f"{value}%")
        
        # 实时更新配置
        self.config.set(f'factors.{factor}.weight', weight)
        
    def _on_param_changed(self, factor: str, param: str, value: int):
        """参数变化"""
        self.config.set(f'factors.{factor}.{param}', value)
        self.status_label.setText(f"📝 {factor}.{param} = {value}")
        
    def _apply_changes(self):
        """应用所有更改"""
        # 收集所有因子的启用状态
        for factor, widgets in self.factor_widgets.items():
            enabled = widgets['enabled'].isChecked()
            self.config.set(f'factors.{factor}.enabled', enabled)
        
        # 通知因子引擎更新
        self.factor_engine._init_factors()
        
        self.status_label.setText("✅ 所有更改已应用，下一根K线生效！")
        
        # 发送信号
        active_factors = self.config.get_active_factors()
        self.factor_changed.emit('all', active_factors)
    
    def _reset_default(self):
        """重置为默认"""
        reply = QMessageBox.question(
            self, '确认重置', 
            '确定要重置所有因子配置为默认值吗？',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.config.reset_to_default()
            self._load_config()
            self.status_label.setText("🔄 已重置为默认配置")


class SymbolRankingPanel(QWidget):
    """品种排行榜面板"""
    
    symbol_selected = pyqtSignal(str)  # 品种选择信号
    
    def __init__(self, scanner, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        
        self._init_ui()
        self._setup_timer()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 标题和刷新按钮
        header = QHBoxLayout()
        
        title = QLabel("🏆 品种排行榜")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        
        self.lbl_update_time = QLabel("未更新")
        self.lbl_update_time.setStyleSheet("color: #666;")
        header.addWidget(self.lbl_update_time)
        
        header.addStretch()
        
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.clicked.connect(self._refresh)
        header.addWidget(self.btn_refresh)
        
        self.btn_auto = QPushButton("▶️ 自动")
        self.btn_auto.setCheckable(True)
        self.btn_auto.clicked.connect(self._toggle_auto)
        header.addWidget(self.btn_auto)
        
        layout.addLayout(header)
        
        # 排行榜表格
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "排名", "品种", "综合得分", "动量", "趋势", "波动", "价格", "涨跌"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.table)
        
        # 状态栏
        self.lbl_status = QLabel("点击刷新获取排行榜")
        layout.addWidget(self.lbl_status)
        
    def _setup_timer(self):
        """设置定时刷新"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        
    def _refresh(self):
        """刷新排行榜"""
        results = self.scanner.get_top_symbols()
        
        if not results:
            self.lbl_status.setText("暂无数据，请先执行扫描")
            return
        
        # 更新表格
        self.table.setRowCount(len(results))
        
        for i, r in enumerate(results):
            # 排名
            item = QTableWidgetItem(str(r.rank))
            if r.rank <= 3:
                item.setBackground(QColor(255, 215, 0))  # 金色
            self.table.setItem(i, 0, item)
            
            # 品种
            self.table.setItem(i, 1, QTableWidgetItem(r.symbol))
            
            # 综合得分
            score_item = QTableWidgetItem(f"{r.score:.1f}")
            if r.score >= 80:
                score_item.setForeground(QColor(0, 150, 0))
            elif r.score < 60:
                score_item.setForeground(QColor(200, 0, 0))
            self.table.setItem(i, 2, score_item)
            
            # 各因子得分
            self.table.setItem(i, 3, QTableWidgetItem(f"{r.momentum_score:.0f}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{r.trend_score:.0f}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{r.volatility_score:.0f}"))
            
            # 价格
            self.table.setItem(i, 6, QTableWidgetItem(f"{r.last_price:.2f}"))
            
            # 涨跌
            change_item = QTableWidgetItem(f"{r.change_pct:+.2f}%")
            if r.change_pct > 0:
                change_item.setForeground(QColor(200, 0, 0))
            elif r.change_pct < 0:
                change_item.setForeground(QColor(0, 150, 0))
            self.table.setItem(i, 7, change_item)
        
        # 更新时间
        if self.scanner.last_scan_time:
            self.lbl_update_time.setText(
                f"更新: {self.scanner.last_scan_time.strftime('%H:%M:%S')}"
            )
        
        self.lbl_status.setText(f"共 {len(results)} 个品种符合条件")
    
    def _toggle_auto(self, checked):
        """切换自动刷新"""
        if checked:
            self.timer.start(5000)  # 5秒刷新
            self.btn_auto.setText("⏸️ 暂停")
        else:
            self.timer.stop()
            self.btn_auto.setText("▶️ 自动")
    
    def _on_item_clicked(self, item):
        """点击品种"""
        row = item.row()
        symbol = self.table.item(row, 1).text()
        self.symbol_selected.emit(symbol)


# 测试代码
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # 创建配置管理器
    config_mgr = ConfigManager()
    
    # 创建面板
    panel = FactorConfigPanel(config_mgr)
    panel.setWindowTitle("多因子配置测试")
    panel.resize(400, 600)
    panel.show()
    
    sys.exit(app.exec_())

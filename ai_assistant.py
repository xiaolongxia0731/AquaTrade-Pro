#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AquaTrade Pro - AI 监控助手模块
实时上报交易状态，接收 AI 建议，支持自动/手动执行
"""

import json
import time
import threading
import requests
from datetime import datetime
from typing import Dict, Callable, Optional
from logger import logger


class AIAssistant:
    """
    AI 交易助手
    - 上报交易状态到云端/本地网关
    - 接收 AI 分析和建议
    - 支持自动执行或人工确认
    """
    
    def __init__(self, enabled: bool = False, auto_mode: bool = False):
        self.enabled = enabled  # 是否启用 AI 助手
        self.auto_mode = auto_mode  # 自动执行模式（无需确认）
        
        # 服务器配置
        self.gateway_url = "http://localhost:10489"  # OpenClaw 网关
        self.report_interval = 30  # 上报间隔（秒）
        
        # 状态缓存
        self.last_status = {}
        self.last_report_time = 0
        
        # 建议回调
        self.on_advice_callback: Optional[Callable] = None
        self.execute_callback: Optional[Callable] = None  # 执行操作的回调
        
        # 上报线程
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 消息历史
        self.messages = []
        
    def start(self):
        """启动 AI 助手"""
        if not self.enabled:
            logger.info("[AI] 助手未启用")
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._report_loop, daemon=True)
        self._thread.start()
        logger.info("[AI] 助手已启动")
        
    def stop(self):
        """停止 AI 助手"""
        self._running = False
        logger.info("[AI] 助手已停止")
        
    def _report_loop(self):
        """定时上报循环"""
        while self._running:
            try:
                if self.last_status:
                    self._report_status(self.last_status)
            except Exception as e:
                logger.error(f"[AI] 上报失败: {e}")
            
            time.sleep(self.report_interval)
    
    def update_status(self, status: Dict):
        """
        更新交易状态（由主程序调用）
        
        status 包含：
        - account: 账户信息（权益、可用、保证金）
        - positions: 持仓信息
        - risk: 风控状态
        - signals: 最近的交易信号
        - logs: 最近的交易日志
        """
        self.last_status = status
        
        # 实时检查是否需要立即上报（异常情况）
        if self._need_immediate_report(status):
            try:
                self._report_status(status, urgent=True)
            except Exception as e:
                logger.error(f"[AI] 紧急上报失败: {e}")
    
    def _need_immediate_report(self, status: Dict) -> bool:
        """判断是否需要立即上报（异常情况）"""
        risk = status.get('risk', {})
        
        # 触发熔断
        if risk.get('circuit_breaker'):
            return True
        
        # 连续错误超过阈值
        if risk.get('error_count', 0) >= 3:
            return True
        
        # 回撤过大（超过5%）
        account = status.get('account', {})
        equity = account.get('equity', 0)
        daily_high = account.get('daily_high', equity)
        if daily_high > 0 and (daily_high - equity) / daily_high > 0.05:
            return True
        
        return False
    
    def _report_status(self, status: Dict, urgent: bool = False):
        """上报状态到 AI 服务器"""
        payload = {
            'timestamp': datetime.now().isoformat(),
            'urgent': urgent,
            'data': status
        }
        
        try:
            # 发送到 OpenClaw 网关
            response = requests.post(
                f"{self.gateway_url}/api/aquatrade/report",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # 处理 AI 返回的建议
                if 'advice' in result:
                    self._handle_advice(result['advice'])
                    
        except requests.exceptions.ConnectionError:
            # 网关未启动，静默失败
            if urgent:
                logger.warning("[AI] 网关未连接，无法上报紧急状态")
        except Exception as e:
            logger.error(f"[AI] 上报异常: {e}")
    
    def _handle_advice(self, advice: Dict):
        """处理 AI 建议"""
        action = advice.get('action')
        reason = advice.get('reason', '')
        confidence = advice.get('confidence', 0)  # 置信度 0-1
        
        # 记录建议
        msg = {
            'time': datetime.now().strftime("%H:%M:%S"),
            'action': action,
            'reason': reason,
            'confidence': confidence
        }
        self.messages.append(msg)
        
        # 回调通知 GUI
        if self.on_advice_callback:
            self.on_advice_callback(advice)
        
        # 自动执行判断
        if self.auto_mode and confidence > 0.8:
            # 高置信度 + 自动模式 = 自动执行
            self._execute_advice(advice)
        elif confidence > 0.6:
            # 中等置信度 = 提示用户确认
            logger.info(f"[AI] 建议: {reason}")
    
    def _execute_advice(self, advice: Dict):
        """执行 AI 建议的操作"""
        action = advice.get('action')
        
        if action == 'close_all':
            logger.warning("[AI] 执行: 一键平仓")
            if self.execute_callback:
                self.execute_callback('close_all')
                
        elif action == 'pause':
            logger.warning("[AI] 执行: 暂停交易")
            if self.execute_callback:
                self.execute_callback('pause')
                
        elif action == 'reduce_position':
            symbol = advice.get('symbol')
            volume = advice.get('volume', 1)
            logger.warning(f"[AI] 执行: 减仓 {symbol} {volume}手")
            if self.execute_callback:
                self.execute_callback('reduce', symbol, volume)
                
        elif action == 'hold':
            logger.info("[AI] 建议: 持仓观望")
    
    def confirm_execute(self, advice: Dict):
        """
        用户确认执行建议
        由 GUI 调用，当用户点击"确认执行"按钮时
        """
        self._execute_advice(advice)
    
    def get_recent_messages(self, count: int = 10) -> list:
        """获取最近的 AI 消息"""
        return self.messages[-count:]
    
    def set_auto_mode(self, enabled: bool):
        """设置自动执行模式"""
        self.auto_mode = enabled
        mode = "自动" if enabled else "手动"
        logger.info(f"[AI] 已切换到{mode}模式")


class AIAssistantPanel:
    """
    AI 助手面板（GUI 组件）
    可以集成到主界面
    """
    
    def __init__(self, ai_assistant: AIAssistant):
        self.ai = ai_assistant
        self.ai.on_advice_callback = self._on_advice
        
        self.pending_advice = None  # 待确认的建议
        
    def _on_advice(self, advice: Dict):
        """收到 AI 建议时的回调"""
        # 这里会更新 GUI 显示
        # 实际实现需要在主 GUI 中集成
        pass
    
    def create_widget(self):
        """
        创建 PyQt5 组件
        返回 QWidget 供主界面嵌入
        """
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, 
            QCheckBox, QTextEdit, QHBoxLayout
        )
        
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 标题
        title = QLabel("🤖 AI 交易助手")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # 状态显示
        self.status_label = QLabel("状态: 未启用")
        layout.addWidget(self.status_label)
        
        # 自动模式开关
        self.auto_checkbox = QCheckBox("自动执行模式（无需确认）")
        self.auto_checkbox.stateChanged.connect(self._toggle_auto)
        layout.addWidget(self.auto_checkbox)
        
        # 消息显示区域
        self.msg_display = QTextEdit()
        self.msg_display.setReadOnly(True)
        self.msg_display.setMaximumHeight(150)
        layout.addWidget(self.msg_display)
        
        # 确认按钮区域（隐藏，有建议时显示）
        self.confirm_layout = QHBoxLayout()
        self.confirm_btn = QPushButton("✓ 确认执行")
        self.ignore_btn = QPushButton("✗ 忽略")
        self.confirm_btn.clicked.connect(self._confirm)
        self.ignore_btn.clicked.connect(self._ignore)
        self.confirm_layout.addWidget(self.confirm_btn)
        self.confirm_layout.addWidget(self.ignore_btn)
        layout.addLayout(self.confirm_layout)
        
        # 默认隐藏确认按钮
        self.confirm_btn.setVisible(False)
        self.ignore_btn.setVisible(False)
        
        return panel
    
    def _toggle_auto(self, state):
        """切换自动模式"""
        self.ai.set_auto_mode(state == 2)  # Qt.Checked = 2
    
    def _confirm(self):
        """确认执行建议"""
        if self.pending_advice:
            self.ai.confirm_execute(self.pending_advice)
            self.pending_advice = None
            self._hide_confirm()
    
    def _ignore(self):
        """忽略建议"""
        self.pending_advice = None
        self._hide_confirm()
    
    def _hide_confirm(self):
        """隐藏确认按钮"""
        self.confirm_btn.setVisible(False)
        self.ignore_btn.setVisible(False)
    
    def show_advice(self, advice: Dict):
        """显示新的建议（由主程序调用）"""
        self.pending_advice = advice
        
        # 显示确认按钮
        if not self.ai.auto_mode:
            self.confirm_btn.setVisible(True)
            self.ignore_btn.setVisible(True)
        
        # 添加到消息显示
        msg = f"[{advice.get('time')}] {advice.get('reason')}"
        self.msg_display.append(msg)


# 使用示例
if __name__ == '__main__':
    # 创建 AI 助手
    ai = AIAssistant(enabled=True, auto_mode=False)
    
    # 设置执行回调
    def execute(action, *args):
        print(f"执行操作: {action}, 参数: {args}")
    
    ai.execute_callback = execute
    
    # 启动
    ai.start()
    
    # 模拟上报状态
    for i in range(10):
        status = {
            'account': {'equity': 100000 + i * 100, 'daily_high': 100000},
            'positions': {'rb2505': {'volume': 2}},
            'risk': {'error_count': 0, 'circuit_breaker': False}
        }
        ai.update_status(status)
        time.sleep(5)
    
    ai.stop()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AquaTrade Pro - K线图表模块 (纯 PyQt5 实现)
不依赖 PyQtChart，使用 QPainter 绘制
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from datetime import datetime
from collections import deque
import math


class KLineChart(QWidget):
    """K线图表组件 - 纯 PyQt5 实现"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 数据存储
        self.kline_data = deque(maxlen=100)
        self.ma5_data = []
        self.ma20_data = []
        
        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题
        self.title_label = QLabel("实时行情 - K线图")
        self.title_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.title_label)
        
        # 图表画布
        self.canvas = KLineCanvas()
        layout.addWidget(self.canvas)
        
        # 图例
        legend_layout = QHBoxLayout()
        legend_layout.addStretch()
        
        # MA5 图例 (黄色)
        ma5_label = QLabel("● MA5")
        ma5_label.setStyleSheet("color: #FFD700;")
        legend_layout.addWidget(ma5_label)
        
        # MA20 图例 (紫色)
        ma20_label = QLabel("● MA20")
        ma20_label.setStyleSheet("color: #DA70D6;")
        legend_layout.addWidget(ma20_label)
        
        legend_layout.addStretch()
        layout.addLayout(legend_layout)
        
    def update_kline(self, timestamp, open_price, high, low, close):
        """更新K线数据"""
        # 保存数据
        self.kline_data.append({
            'timestamp': timestamp,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close
        })
        
        # 计算MA5
        if len(self.kline_data) >= 5:
            ma5 = sum(d['close'] for d in list(self.kline_data)[-5:]) / 5
            self.ma5_data.append({'timestamp': timestamp, 'value': ma5})
        
        # 计算MA20
        if len(self.kline_data) >= 20:
            ma20 = sum(d['close'] for d in list(self.kline_data)[-20:]) / 20
            self.ma20_data.append({'timestamp': timestamp, 'value': ma20})
        
        # 更新画布
        self.canvas.set_data(
            list(self.kline_data),
            self.ma5_data[-50:] if len(self.ma5_data) > 50 else self.ma5_data,
            self.ma20_data[-50:] if len(self.ma20_data) > 50 else self.ma20_data
        )
        
    def clear(self):
        """清空图表"""
        self.kline_data.clear()
        self.ma5_data.clear()
        self.ma20_data.clear()
        self.canvas.set_data([], [], [])


class KLineCanvas(QWidget):
    """K线绘制画布"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        
        # 数据
        self.kline_data = []
        self.ma5_data = []
        self.ma20_data = []
        
        # 颜色
        self.color_up = QColor("#FF4040")  # 涨 - 红色
        self.color_down = QColor("#00C851")  # 跌 - 绿色
        self.color_ma5 = QColor("#FFD700")  # MA5 - 黄色
        self.color_ma20 = QColor("#DA70D6")  # MA20 - 紫色
        self.color_grid = QColor("#E0E0E0")
        self.color_text = QColor("#666666")
        
    def set_data(self, kline_data, ma5_data, ma20_data):
        """设置数据并刷新"""
        self.kline_data = kline_data
        self.ma5_data = ma5_data
        self.ma20_data = ma20_data
        self.update()
        
    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 背景
        painter.fillRect(self.rect(), QColor("#FAFAFA"))
        
        if not self.kline_data:
            # 无数据提示
            painter.setPen(self.color_text)
            painter.setFont(QFont("Microsoft YaHei", 12))
            text = "等待行情数据..."
            rect = self.rect()
            painter.drawText(rect, Qt.AlignCenter, text)
            return
        
        # 计算绘图区域
        margin = 50
        top = margin
        bottom = self.height() - margin
        left = margin
        right = self.width() - margin
        
        chart_width = right - left
        chart_height = bottom - top
        
        # 计算价格范围
        all_prices = []
        for d in self.kline_data:
            all_prices.extend([d['high'], d['low']])
        
        if self.ma5_data:
            all_prices.extend([d['value'] for d in self.ma5_data])
        if self.ma20_data:
            all_prices.extend([d['value'] for d in self.ma20_data])
        
        if not all_prices:
            return
            
        price_min = min(all_prices)
        price_max = max(all_prices)
        price_range = price_max - price_min
        
        # 添加边距
        price_min -= price_range * 0.1
        price_max += price_range * 0.1
        price_range = price_max - price_min
        
        # 绘制网格
        self._draw_grid(painter, left, top, chart_width, chart_height, price_min, price_max)
        
        # 绘制K线
        visible_count = min(len(self.kline_data), 50)  # 最多显示50根
        candle_width = max(4, chart_width / (visible_count + 1))
        
        for i, d in enumerate(self.kline_data[-visible_count:]):
            x = left + (i + 0.5) * candle_width
            
            # 计算Y坐标
            y_open = bottom - (d['open'] - price_min) / price_range * chart_height
            y_close = bottom - (d['close'] - price_min) / price_range * chart_height
            y_high = bottom - (d['high'] - price_min) / price_range * chart_height
            y_low = bottom - (d['low'] - price_min) / price_range * chart_height
            
            # 确定涨跌
            is_up = d['close'] >= d['open']
            color = self.color_up if is_up else self.color_down
            
            pen = QPen(color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(color)
            
            # 绘制影线
            painter.drawLine(int(x), int(y_high), int(x), int(y_low))
            
            # 绘制实体
            body_height = max(1, abs(y_close - y_open))
            body_top = min(y_open, y_close)
            body_rect = QRect(
                int(x - candle_width * 0.4),
                int(body_top),
                int(candle_width * 0.8),
                int(body_height)
            )
            painter.drawRect(body_rect)
        
        # 绘制MA5
        if len(self.ma5_data) >= 2:
            self._draw_line(painter, self.ma5_data[-visible_count:], 
                          left, bottom, chart_width, chart_height, 
                          price_min, price_range, self.color_ma5, candle_width)
        
        # 绘制MA20
        if len(self.ma20_data) >= 2:
            self._draw_line(painter, self.ma20_data[-visible_count:], 
                          left, bottom, chart_width, chart_height, 
                          price_min, price_range, self.color_ma20, candle_width)
        
        # 绘制坐标轴标签
        self._draw_labels(painter, left, right, top, bottom, price_min, price_max)
        
    def _draw_grid(self, painter, left, top, width, height, price_min, price_max):
        """绘制网格"""
        pen = QPen(self.color_grid)
        pen.setWidth(1)
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        
        # 水平线
        for i in range(5):
            y = top + height * i / 4
            painter.drawLine(int(left), int(y), int(left + width), int(y))
        
        # 垂直线
        for i in range(6):
            x = left + width * i / 5
            painter.drawLine(int(x), int(top), int(x), int(top + height))
    
    def _draw_line(self, painter, data, left, bottom, width, height, 
                   price_min, price_range, color, candle_width):
        """绘制均线"""
        if len(data) < 2:
            return
        
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        
        points = []
        for i, d in enumerate(data):
            x = left + (i + 0.5) * candle_width
            y = bottom - (d['value'] - price_min) / price_range * height
            points.append(QPoint(int(x), int(y)))
        
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
    
    def _draw_labels(self, painter, left, right, top, bottom, price_min, price_max):
        """绘制坐标轴标签"""
        painter.setPen(self.color_text)
        painter.setFont(QFont("Microsoft YaHei", 8))
        
        # 价格标签（右侧）
        for i in range(5):
            price = price_max - (price_max - price_min) * i / 4
            y = top + (bottom - top) * i / 4
            text = f"{price:.1f}"
            painter.drawText(int(right + 5), int(y - 6), 50, 12, Qt.AlignLeft, text)
        
        # 时间标签（底部）
        if self.kline_data:
            visible_count = min(len(self.kline_data), 50)
            candle_width = (right - left) / (visible_count + 1)
            
            # 显示开始和结束时间
            start_time = self.kline_data[-visible_count]['timestamp']
            end_time = self.kline_data[-1]['timestamp']
            
            start_str = datetime.fromtimestamp(start_time / 1000).strftime("%H:%M")
            end_str = datetime.fromtimestamp(end_time / 1000).strftime("%H:%M")
            
            painter.drawText(int(left), int(bottom + 5), 50, 15, Qt.AlignLeft, start_str)
            painter.drawText(int(right - 50), int(bottom + 5), 50, 15, Qt.AlignRight, end_str)

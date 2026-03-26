#!/usr/bin/env python3
"""
AquaTrade - 主程序入口
本地期货程序化交易系统

使用方法:
    python main.py

命令:
    pause   - 暂停交易
    resume  - 恢复交易
    close   - 一键平仓
    status  - 查看状态
    quit    - 退出程序
"""

import sys
import time
import threading
from typing import Dict, Optional

import config
from logger import logger
from risk_manager import RiskManager
from strategy import StrategyManager, Signal
from trader import CTPTrader, MockCTPTrader


class AquaTrade:
    """AquaTrade 主控类"""
    
    def __init__(self):
        logger.info("=" * 50)
        logger.info("AquaTrade 启动")
        logger.info("=" * 50)
        
        # 初始化风控
        self.risk_manager = RiskManager()
        
        # 初始化策略管理器
        self.strategy_manager = StrategyManager()
        for symbol in config.TRADING_SYMBOLS:
            self.strategy_manager.add_strategy(symbol)
            
        # 初始化交易器
        self.trader = CTPTrader(self.risk_manager, self._on_trade_callback)
        self.trader.register_tick_callback(self._on_tick)
        
        # 运行状态
        self.running = False
        self.command_thread: Optional[threading.Thread] = None
        
        # 持仓状态缓存
        self.positions: Dict[str, dict] = {}
        
    def _on_tick(self, symbol: str, price: float):
        """行情回调 - 驱动策略"""
        if not self.running:
            return
            
        # 更新风控行情
        self.risk_manager.update_quote(symbol, price, price, price)
        
        # 驱动策略
        result = self.strategy_manager.on_tick(symbol, price)
        if result:
            signal, action, volume = result
            if action != 'hold' and volume > 0:
                self._execute_trade(symbol, action, volume, price)
                
    def _on_trade_callback(self, trade_info: dict):
        """成交回调"""
        symbol = trade_info['symbol']
        direction = trade_info['direction']
        volume = trade_info['volume']
        
        # 更新风控
        self.risk_manager.clear_error()
        
        # 更新策略持仓状态
        current_pos = self.strategy_manager.get_strategy(symbol)
        if current_pos:
            # 简化处理：根据成交方向更新持仓
            if 'buy' in direction and 'open' in direction:
                new_pos = current_pos.position + volume
            elif 'sell' in direction and 'close' in direction:
                new_pos = current_pos.position - volume
            elif 'sell' in direction and 'open' in direction:
                new_pos = current_pos.position - volume
            elif 'buy' in direction and 'close' in direction:
                new_pos = current_pos.position + volume
            else:
                new_pos = current_pos.position
                
            self.strategy_manager.update_position(symbol, new_pos, trade_info['price'])
            self.risk_manager.update_position(symbol, 
                max(0, new_pos), 
                max(0, -new_pos)
            )
            
    def _execute_trade(self, symbol: str, action: str, volume: int, price: float):
        """执行交易"""
        # 价格稍微优化（买低卖高）
        if 'buy' in action:
            order_price = price * 0.999  # 买价略低
        else:
            order_price = price * 1.001  # 卖价略高
            
        order_id = self.trader.send_order(symbol, action, volume, round(order_price, 2))
        
        if order_id:
            logger.info(f"报单成功: {symbol} {action} {volume}手 @ {order_price}")
        else:
            logger.warning(f"报单失败: {symbol} {action} {volume}手")
            
    def _command_loop(self):
        """命令监听线程"""
        while self.running:
            try:
                cmd = input("\n[AquaTrade] 输入命令: ").strip().lower()
                self._handle_command(cmd)
            except EOFError:
                # 非交互环境
                time.sleep(1)
            except Exception as e:
                logger.error(f"命令处理错误: {e}")
                
    def _handle_command(self, cmd: str):
        """处理命令"""
        if not cmd:
            return
            
        if cmd == 'pause':
            self.risk_manager.pause("手动暂停")
            print("✓ 交易已暂停")
            
        elif cmd == 'resume':
            if self.risk_manager.resume():
                print("✓ 交易已恢复")
            else:
                print("✗ 无法恢复（可能处于熔断状态）")
                
        elif cmd == 'close':
            print("⚠ 执行一键平仓...")
            self.trader.close_all_positions()
            
        elif cmd == 'status':
            self._print_status()
            
        elif cmd == 'quit' or cmd == 'exit':
            print("⚠ 正在退出...")
            self.stop()
            
        elif cmd == 'help':
            self._print_help()
            
        else:
            print(f"未知命令: {cmd}, 输入 help 查看帮助")
            
    def _print_status(self):
        """打印状态"""
        print("\n" + "=" * 50)
        print("AquaTrade 状态")
        print("=" * 50)
        
        # 风控状态
        risk = self.risk_manager.get_status()
        print(f"\n[风控状态]")
        print(f"  暂停: {risk['paused']} ({risk['pause_reason']})")
        print(f"  熔断: {risk['circuit_breaker']}")
        print(f"  错误计数: {risk['error_count']}")
        print(f"  报单频率: {risk['orders_per_min']}/{config.MAX_ORDERS_PER_MIN}/min")
        
        # 账户状态
        print(f"\n[账户状态]")
        print(f"  权益: {risk['account_balance']:.2f}")
        print(f"  今日最高: {risk['daily_high']:.2f}")
        
        # 策略状态
        print(f"\n[策略状态]")
        for s in self.strategy_manager.get_all_status():
            pos_str = f"多{s['position']}" if s['position'] > 0 else f"空{abs(s['position'])}" if s['position'] < 0 else "空仓"
            print(f"  {s['symbol']}: {pos_str} | MA5={s['ma_short']} MA20={s['ma_long']}")
            
        print("\n" + "=" * 50)
        
    def _print_help(self):
        """打印帮助"""
        print("""
命令列表:
    pause   - 暂停策略（不平仓，停止开新仓）
    resume  - 恢复策略
    close   - 一键平仓（全部品种）
    status  - 查看当前状态
    quit    - 退出程序（先平仓再退出）
    help    - 显示此帮助
        """)
        
    def start(self):
        """启动系统"""
        logger.info("正在启动交易系统...")
        
        # 连接CTP
        if not self.trader.connect():
            logger.error("连接失败，退出")
            return False
            
        # 订阅行情
        self.trader.subscribe(config.TRADING_SYMBOLS)
        
        # 启动命令线程
        self.running = True
        self.command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self.command_thread.start()
        
        logger.info("系统启动完成")
        logger.info("输入 help 查看可用命令")
        
        return True
        
    def stop(self):
        """停止系统"""
        logger.info("正在停止交易系统...")
        self.running = False
        
        # 先暂停
        self.risk_manager.pause("系统停止")
        
        # 断开连接
        self.trader.disconnect()
        
        logger.info("系统已停止")
        
    def run(self):
        """主循环"""
        if not self.start():
            sys.exit(1)
            
        try:
            # 模拟行情（如果处于模拟模式）
            if hasattr(self.trader, 'use_mock') and self.trader.use_mock:
                self._mock_market_loop()
            else:
                # 实盘模式：保持运行，等待行情回调
                while self.running:
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("\n检测到中断信号...")
        finally:
            self.stop()
            
    def _mock_market_loop(self):
        """模拟行情循环（用于测试）"""
        import random
        
        base_prices = {s: 3500.0 for s in config.TRADING_SYMBOLS}  # 模拟螺纹钢
        
        print("\n[模拟模式] 生成模拟行情中...")
        print("可用命令: pause, resume, close, status, quit\n")
        
        while self.running:
            for symbol in config.TRADING_SYMBOLS:
                # 模拟价格波动
                change = random.uniform(-5, 5)
                base_prices[symbol] += change
                price = round(base_prices[symbol], 2)
                
                # 触发行情回调
                self._on_tick(symbol, price)
                
            time.sleep(2)  # 每2秒更新一次


def main():
    """主函数"""
    print("""
    ╔══════════════════════════════════════════╗
    ║           AquaTrade 期货交易系统           ║
    ║              版本: 1.0.0                  ║
    ╚══════════════════════════════════════════╝
    """)
    
    # 检查配置
    if config.CTP_USER_ID in ('', 'your_user_id'):
        print("⚠ 警告: CTP账号未配置，请编辑 config.py")
        print("将使用模拟模式运行...\n")
        
    # 风险提示
    print("⚠ 风险提示:")
    print("  1. 程序化交易存在亏损风险")
    print("  2. 首次运行请使用模拟盘测试")
    print("  3. 确保理解代码逻辑后再实盘交易")
    print()
    
    # 启动系统
    app = AquaTrade()
    app.run()
    
    print("\n再见!")


if __name__ == '__main__':
    main()

"""交易日志功能联调测试策略

覆盖场景：
- context.log() 三种级别 (info / warning / error)
- 买入/卖出触发 order + fill 日志
- 按仓位卖出避免超额
- 10 bar 一个完整周期
"""
from decimal import Decimal

from squant.engine.backtest.strategy_base import Strategy


class TradingLogTestStrategy(Strategy):
    def on_init(self):
        self.bar_count = 0

    def on_bar(self, bar):
        self.bar_count = self.bar_count + 1
        pos = self.ctx.get_position(bar.symbol)

        # Bar 1: 测试三种日志级别
        if self.bar_count == 1:
            self.ctx.log("策略启动，等待入场信号")
            self.ctx.log("这是一条警告测试", level="warning")
            self.ctx.log("这是一条错误测试", level="error")

        # Bar 3: 买入
        if self.bar_count == 3 and not pos:
            self.ctx.log(f"价格 {bar.close}，准备买入")
            self.ctx.buy(bar.symbol, Decimal("0.01"))

        # Bar 5: 记录持仓状态
        if self.bar_count == 5:
            if pos:
                self.ctx.log(f"持仓中: {pos.amount} @ {pos.avg_entry_price}")
            else:
                self.ctx.log("未持仓", level="warning")

        # Bar 8: 按实际仓位卖出
        if self.bar_count == 8 and pos:
            self.ctx.log(f"价格 {bar.close}，准备卖出 {pos.amount}")
            self.ctx.sell(bar.symbol, pos.amount)
            self.bar_count = 0

    def on_fill(self, fill):
        self.ctx.log(f"收到成交回调: {fill.side.value} {fill.amount} @ {fill.price}")

    def on_order_done(self, order):
        self.ctx.log(f"订单完成: {order.id[:8]} 状态={order.status.value}")

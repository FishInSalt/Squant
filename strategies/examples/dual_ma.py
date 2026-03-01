"""双均线策略示例

这是一个简单的双均线交叉策略示例，用于演示策略编写规范。

系统自动注入以下类型到策略运行环境：
- Strategy: 策略基类（必须继承）
- Bar: K线数据 (time, symbol, open, high, low, close, volume)
- Position: 持仓信息 (symbol, amount, avg_entry_price)
- Decimal: 精确小数计算
- math: 数学函数模块

策略参数通过 self.ctx.params.get(key, default) 获取。
"""

from decimal import Decimal


class DualMAStrategy(Strategy):  # noqa: F821
    """双均线交叉策略

    当短期均线上穿长期均线时买入，下穿时卖出。

    参数:
        fast_period (int): 短期均线周期，默认 5
        slow_period (int): 长期均线周期，默认 20
        amount (Decimal): 每次买入数量，默认 0.01
    """

    def on_init(self) -> None:
        """策略初始化"""
        self.fast_period = self.ctx.params.get("fast_period", 5)
        self.slow_period = self.ctx.params.get("slow_period", 20)
        self.amount = Decimal(str(self.ctx.params.get("amount", "0.01")))
        self.prev_fast_ma = None
        self.prev_slow_ma = None

    def on_bar(self, bar) -> None:
        """K线数据回调"""
        closes = self.ctx.get_closes(self.slow_period)
        if len(closes) < self.slow_period:
            return

        curr_fast = sum(closes[-self.fast_period:]) / self.fast_period
        curr_slow = sum(closes) / self.slow_period

        if self.prev_fast_ma is not None:
            pos = self.ctx.get_position(bar.symbol)

            # 金叉：短期均线上穿长期均线
            if self.prev_fast_ma < self.prev_slow_ma and curr_fast > curr_slow:
                if not pos or pos.amount <= 0:
                    self.ctx.buy(symbol=bar.symbol, amount=self.amount)
                    self.ctx.log(f"金叉买入: {bar.close}")

            # 死叉：短期均线下穿长期均线
            elif self.prev_fast_ma > self.prev_slow_ma and curr_fast < curr_slow:
                if pos and pos.amount > 0:
                    self.ctx.sell(symbol=bar.symbol, amount=pos.amount)
                    self.ctx.log(f"死叉卖出: {bar.close}")

        self.prev_fast_ma = curr_fast
        self.prev_slow_ma = curr_slow

    def on_stop(self) -> None:
        """策略停止"""
        pos_info = self.ctx.positions
        self.ctx.log(f"策略停止，最终持仓: {pos_info}")

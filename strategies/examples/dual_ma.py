"""双均线策略示例

这是一个简单的双均线交叉策略示例，用于演示策略编写规范。
"""

from decimal import Decimal

# 策略基类和数据类型由系统注入
# from squant.engine import Strategy, Bar, Order


class DualMAStrategy:  # (Strategy)
    """双均线交叉策略

    当短期均线上穿长期均线时买入，下穿时卖出。
    """

    # 策略参数
    fast_period: int = 5  # 短期均线周期
    slow_period: int = 20  # 长期均线周期

    def on_init(self) -> None:
        """策略初始化"""
        self.fast_ma: list[Decimal] = []
        self.slow_ma: list[Decimal] = []
        self.position = Decimal("0")

    def on_bar(self, bar) -> None:  # bar: Bar
        """K线数据回调"""
        # 计算均线
        closes = self.ctx.get_closes(self.slow_period)
        if len(closes) < self.slow_period:
            return

        fast_ma = sum(closes[-self.fast_period :]) / self.fast_period
        slow_ma = sum(closes) / self.slow_period

        self.fast_ma.append(fast_ma)
        self.slow_ma.append(slow_ma)

        if len(self.fast_ma) < 2:
            return

        # 金叉：短期均线上穿长期均线
        if self.fast_ma[-2] < self.slow_ma[-2] and self.fast_ma[-1] > self.slow_ma[-1]:
            if self.position <= 0:
                self.ctx.buy(
                    symbol=bar.symbol,
                    amount=Decimal("0.01"),
                    price=bar.close,
                )
                self.ctx.log(f"金叉买入: {bar.close}")

        # 死叉：短期均线下穿长期均线
        elif self.fast_ma[-2] > self.slow_ma[-2] and self.fast_ma[-1] < self.slow_ma[-1]:
            if self.position > 0:
                self.ctx.sell(
                    symbol=bar.symbol,
                    amount=self.position,
                    price=bar.close,
                )
                self.ctx.log(f"死叉卖出: {bar.close}")

    def on_order(self, order) -> None:  # order: Order
        """订单状态回调"""
        if order.status == "filled":
            if order.side == "buy":
                self.position += order.filled_amount
            else:
                self.position -= order.filled_amount

    def on_stop(self) -> None:
        """策略停止"""
        self.ctx.log(f"策略停止，最终持仓: {self.position}")

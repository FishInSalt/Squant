"""双均线策略示例

经典趋势跟踪策略：短期均线上穿长期均线时买入（金叉），下穿时卖出（死叉）。
使用 ta 模块的 sma() 计算均线，close_position() 快速平仓。

系统自动注入以下对象到策略运行环境（无需 import）：
- Strategy: 策略基类（必须继承）
- Bar: K线数据 (time, symbol, open, high, low, close, volume)
- Position: 持仓信息 (symbol, amount, avg_entry_price)
- OrderSide / OrderType: 订单方向与类型枚举
- Fill: 成交回报 (order_id, symbol, side, price, amount, fee, timestamp)
- OrderStatus: 订单状态枚举 (PENDING, FILLED, PARTIAL, CANCELLED)
- ta: 内置技术指标模块 (sma, ema, rsi, macd, bollinger_bands, atr, ...)
- Decimal: 精确小数计算
- math: 数学函数模块
- statistics: 统计函数模块 (mean, median, stdev, variance, ...)

策略参数通过 self.ctx.params.get(key, default) 获取。
"""

from decimal import Decimal


class DualMAStrategy(Strategy):  # noqa: F821
    """双均线交叉策略

    当短期均线上穿长期均线时买入，下穿时卖出。

    参数:
        fast_period (int): 短期均线周期，默认 5
        slow_period (int): 长期均线周期，默认 20
        position_ratio (float): 仓位比例，默认 0.9
    """

    def on_init(self):
        self.fast_period = self.ctx.params.get("fast_period", 5)
        self.slow_period = self.ctx.params.get("slow_period", 20)
        self.position_ratio = Decimal(str(self.ctx.params.get("position_ratio", 0.9)))

    def on_bar(self, bar):
        closes = self.ctx.get_closes(self.slow_period + 1)
        if len(closes) < self.slow_period + 1:
            return

        # 计算当前和上一根 K 线的均线值
        fast_now = ta.sma(closes, self.fast_period)  # noqa: F821
        slow_now = ta.sma(closes, self.slow_period)  # noqa: F821
        fast_prev = ta.sma(closes[:-1], self.fast_period)  # noqa: F821
        slow_prev = ta.sma(closes[:-1], self.slow_period)  # noqa: F821

        if None in (fast_now, slow_now, fast_prev, slow_prev):
            return

        pos = self.ctx.get_position(bar.symbol)

        # 金叉：短期均线上穿长期均线
        if fast_prev <= slow_prev and fast_now > slow_now:
            if not pos:
                amount = self.ctx.cash * self.position_ratio / bar.close
                if amount > 0:
                    self.ctx.buy(bar.symbol, amount)
                    self.ctx.log(f"金叉买入: {bar.close}")

        # 死叉：短期均线下穿长期均线
        elif fast_prev >= slow_prev and fast_now < slow_now:
            if pos:
                self.ctx.close_position(bar.symbol)
                self.ctx.log(f"死叉平仓: {bar.close}")

    def on_stop(self):
        self.ctx.log(
            f"策略停止 | 收益率: {self.ctx.return_pct:.2%} | 最大回撤: {self.ctx.max_drawdown:.2%}"
        )

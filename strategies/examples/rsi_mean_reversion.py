"""RSI 均值回归策略示例

基于相对强弱指标 (RSI) 的均值回归策略。
当 RSI 进入超卖区间时买入（预期价格回升），进入超买区间时卖出（预期价格回落）。
使用 ta 模块的 rsi() 计算指标，演示 on_fill 回调的使用方式。

系统自动注入以下对象到策略运行环境（无需 import）：
- Strategy: 策略基类（必须继承）
- Bar: K线数据 (time, symbol, open, high, low, close, volume)
- Position: 持仓信息 (symbol, amount, avg_entry_price)
- OrderSide / OrderType: 订单方向与类型枚举
- Fill: 成交回报 (symbol, side, price, amount, fee, pnl, ...)
- OrderStatus: 订单状态枚举 (PENDING, FILLED, CANCELLED, EXPIRED)
- ta: 内置技术指标模块 (sma, ema, rsi, macd, bollinger_bands, atr, ...)
- Decimal: 精确小数计算
- math: 数学函数模块

策略参数通过 self.ctx.params.get(key, default) 获取。
"""

from decimal import Decimal


class RSIMeanReversionStrategy(Strategy):  # noqa: F821
    """RSI 均值回归策略

    当 RSI 低于超卖线时买入，高于超买线时卖出。
    使用 ta.rsi() 内置的 Wilder 平滑法计算 RSI。

    参数:
        rsi_period (int): RSI 计算周期，默认 14
        oversold (int): 超卖阈值，默认 30
        overbought (int): 超买阈值，默认 70
        position_ratio (float): 仓位比例，默认 0.9
    """

    def on_init(self):
        self.rsi_period = self.ctx.params.get("rsi_period", 14)
        self.oversold = self.ctx.params.get("oversold", 30)
        self.overbought = self.ctx.params.get("overbought", 70)
        self.position_ratio = Decimal(str(self.ctx.params.get("position_ratio", 0.9)))
        self.trade_count = 0

    def on_bar(self, bar):
        # 需要 period+1 根 K 线来计算 RSI
        closes = self.ctx.get_closes(self.rsi_period + 1)
        if len(closes) < self.rsi_period + 1:
            return

        current_rsi = ta.rsi(closes, self.rsi_period)  # noqa: F821
        if current_rsi is None:
            return

        pos = self.ctx.get_position(bar.symbol)

        # 超卖区间 → 买入信号
        if current_rsi < self.oversold and not pos:
            amount = self.ctx.cash * self.position_ratio / bar.close
            if amount > 0:
                self.ctx.buy(bar.symbol, amount)
                self.ctx.log(f"RSI={current_rsi:.1f} 超卖买入: {bar.close}")

        # 超买区间 → 卖出信号
        elif current_rsi > self.overbought and pos:
            self.ctx.close_position(bar.symbol)
            self.ctx.log(f"RSI={current_rsi:.1f} 超买平仓: {bar.close}")

    def on_fill(self, fill):
        """成交回调：记录每笔成交"""
        self.trade_count = self.trade_count + 1
        self.ctx.log(f"成交 #{self.trade_count}: {fill.side.value} {fill.amount} @ {fill.price}")

    def on_stop(self):
        self.ctx.log(
            f"策略停止 | 交易次数: {self.trade_count} | "
            f"收益率: {self.ctx.return_pct:.2%} | "
            f"最大回撤: {self.ctx.max_drawdown:.2%}"
        )

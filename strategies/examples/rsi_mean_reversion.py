"""RSI 均值回归策略示例

基于相对强弱指标 (RSI) 的均值回归策略。
当 RSI 进入超卖区间时买入（预期价格回升），进入超买区间时卖出（预期价格回落）。

系统自动注入以下类型到策略运行环境：
- Strategy: 策略基类（必须继承）
- Bar: K线数据 (time, symbol, open, high, low, close, volume)
- Position: 持仓信息 (symbol, amount, avg_entry_price)
- Decimal: 精确小数计算
- math: 数学函数模块

策略参数通过 self.ctx.params.get(key, default) 获取。
"""

from decimal import Decimal


class RSIMeanReversionStrategy(Strategy):  # noqa: F821
    """RSI 均值回归策略

    当 RSI 低于超卖线时买入，高于超买线时卖出。
    使用 Wilder 平滑法计算 RSI。

    参数:
        rsi_period (int): RSI 计算周期，默认 14
        oversold (int): 超卖阈值，默认 30
        overbought (int): 超买阈值，默认 70
        amount (str): 每次买入数量，默认 "0.01"
    """

    def on_init(self) -> None:
        """策略初始化"""
        self.rsi_period = self.ctx.params.get("rsi_period", 14)
        self.oversold = Decimal(str(self.ctx.params.get("oversold", 30)))
        self.overbought = Decimal(str(self.ctx.params.get("overbought", 70)))
        self.amount = Decimal(str(self.ctx.params.get("amount", "0.01")))

        self.prev_close = None
        self.avg_gain = Decimal("0")
        self.avg_loss = Decimal("0")
        self.bar_count = 0

    def on_bar(self, bar) -> None:
        """K线数据回调"""
        if self.prev_close is None:
            self.prev_close = bar.close
            return

        # 计算价格变动
        change = bar.close - self.prev_close
        self.prev_close = bar.close

        gain = change if change > 0 else Decimal("0")
        loss = -change if change < 0 else Decimal("0")

        self.bar_count = self.bar_count + 1
        period = Decimal(str(self.rsi_period))

        if self.bar_count < self.rsi_period:
            # 累积阶段：收集初始数据
            self.avg_gain = self.avg_gain + gain
            self.avg_loss = self.avg_loss + loss
            return

        if self.bar_count == self.rsi_period:
            # 第一次计算：简单平均
            self.avg_gain = (self.avg_gain + gain) / period
            self.avg_loss = (self.avg_loss + loss) / period
        else:
            # Wilder 平滑法
            self.avg_gain = (self.avg_gain * (period - 1) + gain) / period
            self.avg_loss = (self.avg_loss * (period - 1) + loss) / period

        # 计算 RSI
        if self.avg_loss == 0:
            rsi = Decimal("100")
        else:
            rs = self.avg_gain / self.avg_loss
            rsi = Decimal("100") - Decimal("100") / (1 + rs)

        pos = self.ctx.get_position(bar.symbol)

        # 超卖区间 → 买入信号
        if rsi < self.oversold:
            if not pos or pos.amount <= 0:
                self.ctx.buy(
                    symbol=bar.symbol,
                    amount=self.amount,
                    price=bar.close,
                )
                self.ctx.log(f"RSI={rsi:.1f} 超卖买入: {bar.close}")

        # 超买区间 → 卖出信号
        elif rsi > self.overbought:
            if pos and pos.amount > 0:
                self.ctx.sell(
                    symbol=bar.symbol,
                    amount=pos.amount,
                    price=bar.close,
                )
                self.ctx.log(f"RSI={rsi:.1f} 超买卖出: {bar.close}")

    def on_stop(self) -> None:
        """策略停止"""
        self.ctx.log(f"策略停止，共处理 {self.bar_count} 根K线")

"""保守型均值回归策略 — Bollinger Band 超跌抄底（现货仅做多）

在震荡行情中，利用布林带下轨作为超卖区域，配合 RSI 过滤假信号，
执行高胜率的均值回归交易。仅在市场环境非 RED 时做多。

适用场景：横盘震荡、支撑位反弹（如 ETH/USDT $1,900–$2,150 区间）。

注意事项：
- 现货市场仅支持做多。空仓等待即为"做空替代"。
- 15m 环境过滤：RED 状态下停止开仓，YELLOW 状态下提高入场门槛。
- 止损/止盈/移动止损均在 on_bar 中逐K线检查，非实时订单。
- K 线形态过滤：要求阳线或锤子线确认买方力量。

系统自动注入以下对象到策略运行环境（无需 import）：
- Strategy, Bar, Position, OrderSide, OrderType, Fill, OrderStatus
- ta: 内置技术指标模块 (sma, ema, rsi, macd, bollinger_bands, atr, ...)
- Decimal, math, statistics

策略参数通过 self.ctx.params.get(key, default) 获取。
"""

from decimal import Decimal


class BBMeanReversionStrategy(Strategy):  # noqa: F821
    """保守型布林带均值回归策略

    做多条件：环境非RED + BB 下轨 + RSI 超卖 + 放量 + 阳线/锤子线
    平仓条件：止损 / 止盈 / 追踪止损 / 均值回归 / BB上轨 / RSI中性 / 时间止损

    参数:
        bb_period (int): 布林带周期，默认 20
        bb_std (float): 布林带标准差倍数，默认 2.0
        rsi_period (int): RSI 周期，默认 14
        rsi_oversold (int): RSI 超卖阈值（GREEN），默认 28
        rsi_oversold_yellow (int): RSI 超卖阈值（YELLOW），默认 25
        rsi_neutral_exit (int): RSI 中性出场阈值，默认 55
        volume_ma_period (int): 成交量均线周期，默认 20
        ema_regime_period (int): 15m 环境判断 EMA 周期，默认 50
        position_size_pct (float): 每笔仓位占总资金比例，默认 0.02
        take_profit_pct (float): 止盈百分比，默认 0.003
        stop_loss_pct (float): 止损百分比，默认 0.002
        trailing_stop_pct (float): 追踪止损百分比，默认 0.0015
        max_daily_trades (int): 日内最大交易次数，默认 8
        cooldown_bars (int): 交易冷却K线数，默认 2
        min_volume_multiplier (float): 最小成交量倍数，默认 1.3
        min_bb_bandwidth (float): 最小带宽（排除极窄盘整），默认 0.005
        time_exit_bars (int): 持仓超时K线数（未盈利则平仓），默认 5
        daily_loss_limit (float): 日内止损上限占总资金比，默认 0.002
        max_consecutive_losses (int): 连续亏损多少次后当日停止，默认 3
        support_level (float): 强支撑位（跌破则 RED），默认 1900
    """

    def on_init(self):
        # 指标参数
        self.bb_period = self.ctx.params.get("bb_period", 20)
        self.bb_std = Decimal(str(self.ctx.params.get("bb_std", 2.0)))
        self.rsi_period = self.ctx.params.get("rsi_period", 14)
        self.rsi_oversold = Decimal(str(self.ctx.params.get("rsi_oversold", 28)))
        self.rsi_oversold_yellow = Decimal(str(self.ctx.params.get("rsi_oversold_yellow", 25)))
        self.rsi_neutral_exit = Decimal(str(self.ctx.params.get("rsi_neutral_exit", 55)))
        self.vol_ma_period = self.ctx.params.get("volume_ma_period", 20)

        # 15m 环境参数
        self.ema_regime_period = self.ctx.params.get("ema_regime_period", 50)
        self.support_level = Decimal(str(self.ctx.params.get("support_level", 1900)))

        # 仓位管理
        self.position_size_pct = Decimal(str(self.ctx.params.get("position_size_pct", 0.02)))
        self.max_daily_trades = self.ctx.params.get("max_daily_trades", 8)

        # 出场参数
        self.take_profit_pct = Decimal(str(self.ctx.params.get("take_profit_pct", 0.003)))
        self.stop_loss_pct = Decimal(str(self.ctx.params.get("stop_loss_pct", 0.002)))
        self.trailing_stop_pct = Decimal(str(self.ctx.params.get("trailing_stop_pct", 0.0015)))
        self.time_exit_bars = self.ctx.params.get("time_exit_bars", 5)
        self.mean_reversion_threshold = Decimal(
            str(self.ctx.params.get("mean_reversion_threshold", 0.001))
        )

        # 过滤器
        self.min_vol_mult = Decimal(str(self.ctx.params.get("min_volume_multiplier", 1.3)))
        self.min_bb_bandwidth = Decimal(str(self.ctx.params.get("min_bb_bandwidth", 0.005)))
        self.cooldown_bars = self.ctx.params.get("cooldown_bars", 2)

        # 风控
        self.daily_loss_limit = Decimal(str(self.ctx.params.get("daily_loss_limit", 0.002)))
        self.max_consecutive_losses = self.ctx.params.get("max_consecutive_losses", 3)

        # 运行状态
        self.regime_closes = []
        self.bar_count = 0
        self.daily_trades = 0
        self.last_trade_day = None
        self.bars_since_trade = 999
        self.entry_bar = 0
        self.highest_since_entry = Decimal("0")
        self.daily_start_equity = Decimal("0")
        self.consecutive_losses = 0

    def get_regime(self, current_price):
        """15m 环境评估：GREEN / YELLOW / RED"""
        if current_price < self.support_level:
            return "RED"

        if len(self.regime_closes) < self.ema_regime_period:
            return "YELLOW"

        ema50 = ta.ema(self.regime_closes, self.ema_regime_period)  # noqa: F821
        if ema50 is None:
            return "YELLOW"

        if current_price > ema50 * Decimal("1.002"):
            return "GREEN"
        return "YELLOW"

    def on_bar(self, bar):
        self.bar_count = self.bar_count + 1
        self.bars_since_trade = self.bars_since_trade + 1

        # 每 15 根 1m K 线聚合一根 15m 收盘价
        if self.bar_count % 15 == 0:
            self.regime_closes.append(bar.close)
            if len(self.regime_closes) > 200:
                self.regime_closes.pop(0)

        # 日切重置
        today = bar.time.date()
        if today != self.last_trade_day:
            self.daily_trades = 0
            self.last_trade_day = today
            self.daily_start_equity = self.ctx.equity
            self.consecutive_losses = 0

        # 日内止损检查
        if self.daily_start_equity > Decimal("0"):
            daily_pnl = (self.ctx.equity - self.daily_start_equity) / self.daily_start_equity
            if daily_pnl <= -self.daily_loss_limit:
                return

        # 连续亏损当日停止
        if self.consecutive_losses >= self.max_consecutive_losses:
            return

        # 数据准备
        need = max(self.bb_period, self.rsi_period + 1, self.vol_ma_period) + 5
        closes = self.ctx.get_closes(need)
        volumes = self.ctx.get_volumes(self.vol_ma_period + 1)
        if len(closes) < self.bb_period or len(volumes) < self.vol_ma_period:
            return

        # 计算指标
        bb = ta.bollinger_bands(closes, self.bb_period, self.bb_std)  # noqa: F821
        rsi_val = ta.rsi(closes, self.rsi_period)  # noqa: F821
        vol_ma = ta.sma(volumes, self.vol_ma_period)  # noqa: F821

        if bb is None or rsi_val is None or vol_ma is None:
            return

        upper = bb[0]
        middle = bb[1]
        lower = bb[2]

        # 环境评估
        regime = self.get_regime(bar.close)
        pos = self.ctx.get_position(bar.symbol)

        # ============ 持仓管理 ============
        if pos:
            entry_price = pos.avg_entry_price
            if entry_price <= Decimal("0"):
                return

            self.highest_since_entry = max(self.highest_since_entry, bar.high)
            pnl_pct = (bar.close - entry_price) / entry_price
            bars_held = self.bar_count - self.entry_bar
            exit_reason = None

            # 0. 环境恶化 → RED 立即平仓
            if regime == "RED":
                exit_reason = "环境RED清仓"

            # 1. 固定止损
            if exit_reason is None and pnl_pct <= -self.stop_loss_pct:
                exit_reason = f"止损 PnL={pnl_pct:.4%}"

            # 2. 固定止盈
            if exit_reason is None and pnl_pct >= self.take_profit_pct:
                exit_reason = f"止盈 PnL={pnl_pct:.4%}"

            # 3. 追踪止损（仅在盈利时生效）
            if (
                exit_reason is None
                and pnl_pct > Decimal("0")
                and self.highest_since_entry > Decimal("0")
            ):
                trail_stop = self.highest_since_entry * (Decimal("1") - self.trailing_stop_pct)
                if bar.close <= trail_stop:
                    exit_reason = f"追踪止损 最高={self.highest_since_entry:.2f}"

            # 4. BB 上轨止盈（现货不做空，但上轨是卖出信号）
            if exit_reason is None and bar.close >= upper:
                exit_reason = f"BB上轨止盈 upper={upper:.2f}"

            # 5. 均值回归：价格回到 BB 中轨附近
            if exit_reason is None and middle > Decimal("0"):
                if abs(bar.close - middle) / middle < self.mean_reversion_threshold:
                    exit_reason = f"回归中轨 {middle:.2f}"

            # 6. RSI 回到中性区间 + 盈利 → 获利了结
            if exit_reason is None and rsi_val >= self.rsi_neutral_exit:
                if pnl_pct > Decimal("0.001"):
                    exit_reason = f"RSI中性止盈={rsi_val:.1f} PnL={pnl_pct:.4%}"

            # 7. 时间止损：持仓超时且未盈利
            if exit_reason is None and bars_held >= self.time_exit_bars:
                if pnl_pct < Decimal("0.001"):
                    exit_reason = f"超时{bars_held}根 PnL={pnl_pct:.4%}"

            if exit_reason:
                self.ctx.close_position(bar.symbol)
                self.ctx.log(f"平仓[{exit_reason}] @ {bar.close}")
                self.daily_trades = self.daily_trades + 1
                self.bars_since_trade = 0
                self.highest_since_entry = Decimal("0")
                if pnl_pct < Decimal("0"):
                    self.consecutive_losses = self.consecutive_losses + 1
                else:
                    self.consecutive_losses = 0
            return

        # ============ 入场逻辑（仅做多）============
        if self.daily_trades >= self.max_daily_trades:
            return
        if self.bars_since_trade < self.cooldown_bars:
            return

        # 环境过滤：RED 不开仓
        if regime == "RED":
            return

        # YELLOW 状态下使用更严格的 RSI 阈值
        rsi_threshold = self.rsi_oversold
        if regime == "YELLOW":
            rsi_threshold = self.rsi_oversold_yellow

        # 带宽过滤：排除极度缩量横盘
        bandwidth = Decimal("0")
        if middle > Decimal("0"):
            bandwidth = (upper - lower) / middle
            if bandwidth < self.min_bb_bandwidth:
                return

        # K线形态过滤：阳线或锤子线
        body = abs(bar.close - bar.open)
        lower_shadow = min(bar.open, bar.close) - bar.low
        is_bullish_candle = bar.close > bar.open
        is_hammer = body > Decimal("0") and lower_shadow > body * Decimal("2")
        if not is_bullish_candle and not is_hammer:
            return

        # 做多信号：BB 下轨 + RSI 超卖 + 放量
        if (
            bar.close <= lower
            and rsi_val <= rsi_threshold
            and vol_ma > Decimal("0")
            and bar.volume > vol_ma * self.min_vol_mult
        ):
            amount = self.ctx.equity * self.position_size_pct / bar.close
            if amount > Decimal("0"):
                self.ctx.buy(bar.symbol, amount)
                self.entry_bar = self.bar_count
                self.highest_since_entry = bar.high
                self.ctx.log(
                    f"做多[BB下轨+RSI超卖] @ {bar.close} "
                    f"RSI={rsi_val:.1f} 带宽={bandwidth:.4f} 环境={regime}"
                )

    def on_stop(self):
        trades = self.ctx.trades
        wins = sum(1 for t in trades if t.pnl > Decimal("0"))
        win_rate = wins / len(trades) * 100 if trades else 0
        self.ctx.log(
            f"策略停止 | 收益率: {self.ctx.return_pct:.2%} | "
            f"最大回撤: {self.ctx.max_drawdown:.2%} | "
            f"交易: {len(trades)}笔 胜率: {win_rate:.1f}%"
        )

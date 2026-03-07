"""激进型动量突破策略 — 多周期顺势做多（现货仅做多）

结合手动聚合的 5 分钟级别趋势方向和 15 分钟环境过滤，
在 1 分钟级别捕捉动量突破信号。仅在 GREEN 环境 + 5m 趋势看多时做多。

适用场景：超跌反弹、短线趋势启动。在偏空大环境中空仓等待。

策略特点：
- 三层过滤：15m 环境（GREEN）+ 5m 趋势（BULLISH）+ 1m 信号
- ATR 动态止损/止盈：根据波动率自动调整出场位置，盈亏比 2.5:1
- 金字塔加仓：趋势确认后允许顺势加仓（最多 1 次）
- 连续亏损降仓/停止：3 次降仓，5 次当日停止
- 趋势翻转出场：5m 转空时主动平仓

注意事项：
- 现货做多限制：仅在 GREEN + BULLISH 时开仓。偏空市场全部空仓。
- 5m/15m 数据聚合：手动将 1m K 线聚合，非严格时间对齐。
- 移动止损在策略内模拟，非交易所止损单。
- 阳线确认：要求入场 K 线为阳线（close > open）。

系统自动注入以下对象到策略运行环境（无需 import）：
- Strategy, Bar, Position, OrderSide, OrderType, Fill, OrderStatus
- ta: 内置技术指标模块
- Decimal, math, statistics
"""

from decimal import Decimal


class MomentumBreakoutStrategy(Strategy):  # noqa: F821
    """激进型多周期动量突破策略

    做多条件：GREEN环境 + 5m看多 + 1m EMA金叉 + MACD动量增强 + 放量 + 阳线
    平仓条件：ATR止损 / 保本止损 / 追踪止损 / ATR止盈 / 趋势翻转 / 环境恶化
    加仓条件：盈利 >= 1.5 ATR + MACD动量持续增强

    参数:
        ema_fast (int): 1m 快速 EMA 周期，默认 9
        ema_slow (int): 1m 慢速 EMA 周期，默认 21
        ema_trend (int): 1m 趋势 EMA 周期，默认 50
        atr_period (int): ATR 周期，默认 14
        volume_ma_period (int): 成交量均线周期，默认 20
        htf_ema_fast (int): 5m 快速 EMA 周期，默认 9
        htf_ema_slow (int): 5m 慢速 EMA 周期，默认 21
        ema_regime_period (int): 15m 环境 EMA 周期，默认 50
        position_size_pct (float): 每笔仓位占总资金比例，默认 0.04
        max_daily_trades (int): 日内最大交易次数，默认 15
        pyramid_max (int): 最大加仓次数，默认 1（最多加仓 1 次）
        stop_loss_atr_mult (float): 止损 ATR 倍数，默认 1.5
        take_profit_atr_mult (float): 止盈 ATR 倍数，默认 3.5
        trailing_stop_atr_mult (float): 追踪止损 ATR 倍数，默认 1.0
        breakeven_trigger_atr (float): 保本触发 ATR 倍数，默认 1.0
        min_volume_multiplier (float): 突破最小成交量倍数，默认 1.5
        min_atr_threshold (float): 最低波动率门槛 (USDT)，默认 0.5
        daily_loss_limit (float): 日内止损上限占总资金比，默认 0.008
        loss_scale_threshold (int): 连续亏损多少次后降仓，默认 3
        loss_stop_threshold (int): 连续亏损多少次后当日停止，默认 5
        support_level (float): 强支撑位（跌破则 RED），默认 1900
    """

    def on_init(self):
        # 1m 指标参数
        self.ema_fast = self.ctx.params.get("ema_fast", 9)
        self.ema_slow = self.ctx.params.get("ema_slow", 21)
        self.ema_trend = self.ctx.params.get("ema_trend", 50)
        self.atr_period = self.ctx.params.get("atr_period", 14)
        self.vol_ma_period = self.ctx.params.get("volume_ma_period", 20)

        # 5m 趋势参数
        self.htf_ema_fast = self.ctx.params.get("htf_ema_fast", 9)
        self.htf_ema_slow = self.ctx.params.get("htf_ema_slow", 21)

        # 15m 环境参数
        self.ema_regime_period = self.ctx.params.get("ema_regime_period", 50)
        self.support_level = Decimal(str(self.ctx.params.get("support_level", 1900)))

        # 仓位管理
        self.position_size_pct = Decimal(str(self.ctx.params.get("position_size_pct", 0.04)))
        self.max_daily_trades = self.ctx.params.get("max_daily_trades", 15)
        self.pyramid_max = self.ctx.params.get("pyramid_max", 1)

        # ATR 出场倍数
        self.sl_atr_mult = Decimal(str(self.ctx.params.get("stop_loss_atr_mult", 1.5)))
        self.tp_atr_mult = Decimal(str(self.ctx.params.get("take_profit_atr_mult", 3.5)))
        self.trail_atr_mult = Decimal(str(self.ctx.params.get("trailing_stop_atr_mult", 1.0)))
        self.breakeven_atr = Decimal(str(self.ctx.params.get("breakeven_trigger_atr", 1.0)))

        # 过滤器
        self.min_vol_mult = Decimal(str(self.ctx.params.get("min_volume_multiplier", 1.5)))
        self.min_atr = Decimal(str(self.ctx.params.get("min_atr_threshold", 0.5)))

        # 风控
        self.daily_loss_limit = Decimal(str(self.ctx.params.get("daily_loss_limit", 0.008)))
        self.loss_scale_threshold = self.ctx.params.get("loss_scale_threshold", 3)
        self.loss_stop_threshold = self.ctx.params.get("loss_stop_threshold", 5)

        # 运行状态
        self.htf_closes = []
        self.regime_closes = []
        self.bar_count = 0
        self.daily_trades = 0
        self.last_trade_day = None
        self.entry_price = Decimal("0")
        self.trailing_stop = Decimal("0")
        self.pyramid_count = 0
        self.prev_macd_hist = None
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

    def get_5m_bias(self):
        """从聚合的 5m 收盘价计算趋势方向。"""
        if len(self.htf_closes) < self.htf_ema_slow:
            return "NEUTRAL"

        fast = ta.ema(self.htf_closes, self.htf_ema_fast)  # noqa: F821
        slow = ta.ema(self.htf_closes, self.htf_ema_slow)  # noqa: F821

        if fast is None or slow is None:
            return "NEUTRAL"
        if fast > slow:
            return "BULLISH"
        if fast < slow:
            return "BEARISH"
        return "NEUTRAL"

    def position_scale(self):
        """连续亏损后降仓。"""
        if self.consecutive_losses >= self.loss_scale_threshold:
            return Decimal("0.5")
        return Decimal("1")

    def on_bar(self, bar):
        self.bar_count = self.bar_count + 1

        # 每 5 根 1m K 线聚合一根 5m 收盘价
        if self.bar_count % 5 == 0:
            self.htf_closes.append(bar.close)
            if len(self.htf_closes) > 200:
                self.htf_closes.pop(0)

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
        if self.consecutive_losses >= self.loss_stop_threshold:
            return

        # 数据准备
        data_need = max(self.ema_trend, self.atr_period + 1, 34, self.vol_ma_period) + 5
        closes = self.ctx.get_closes(data_need)
        highs = self.ctx.get_highs(self.atr_period + 2)
        lows = self.ctx.get_lows(self.atr_period + 2)
        volumes = self.ctx.get_volumes(self.vol_ma_period + 1)

        if len(closes) < data_need - 5:
            return

        # 1m 指标
        ema_f = ta.ema(closes, self.ema_fast)  # noqa: F821
        ema_s = ta.ema(closes, self.ema_slow)  # noqa: F821
        ema_t = ta.ema(closes, self.ema_trend)  # noqa: F821
        atr_val = ta.atr(highs, lows, closes[-len(highs):], self.atr_period)  # noqa: F821
        vol_ma = ta.sma(volumes, self.vol_ma_period)  # noqa: F821
        macd_result = ta.macd(closes)  # noqa: F821

        if None in (ema_f, ema_s, ema_t, atr_val, vol_ma) or macd_result is None:
            return

        histogram = macd_result[2]

        # 保存上一根 MACD 柱状值并更新
        prev_hist = self.prev_macd_hist
        self.prev_macd_hist = histogram

        # ATR 过滤：波动率过低时不交易
        if atr_val < self.min_atr:
            return

        # 环境和趋势评估
        regime = self.get_regime(bar.close)
        htf_bias = self.get_5m_bias()
        pos = self.ctx.get_position(bar.symbol)

        # ============ 持仓管理 ============
        if pos:
            entry_price = pos.avg_entry_price
            if entry_price <= Decimal("0"):
                return

            pnl = bar.close - entry_price
            pnl_pct = pnl / entry_price
            exit_reason = None

            # 0. 环境恶化 → RED 立即平仓（最高优先级）
            if regime == "RED":
                exit_reason = "环境RED清仓"

            # 1. ATR 止损
            if exit_reason is None:
                stop_price = entry_price - self.sl_atr_mult * atr_val
                if bar.close <= stop_price:
                    exit_reason = f"ATR止损 止损位={stop_price:.2f}"

            # 2. 5m 趋势翻转出场
            if exit_reason is None and htf_bias != "BULLISH":
                if pnl > Decimal("0"):
                    exit_reason = f"趋势翻转止盈 5m={htf_bias} PnL={pnl_pct:.4%}"
                else:
                    exit_reason = f"趋势翻转平仓 5m={htf_bias} PnL={pnl_pct:.4%}"

            # 3. 保本止损：盈利达 breakeven_atr 倍 ATR 后，止损移至成本价 + $0.5
            if exit_reason is None and pnl >= self.breakeven_atr * atr_val:
                breakeven_price = entry_price + Decimal("0.5")
                self.trailing_stop = max(self.trailing_stop, breakeven_price)

            # 4. 追踪止损（ATR 动态）
            if exit_reason is None:
                new_trail = bar.close - self.trail_atr_mult * atr_val
                self.trailing_stop = max(self.trailing_stop, new_trail)
                if self.trailing_stop > Decimal("0") and bar.close <= self.trailing_stop:
                    exit_reason = f"追踪止损 trail={self.trailing_stop:.2f}"

            # 5. ATR 止盈
            if exit_reason is None:
                tp_price = entry_price + self.tp_atr_mult * atr_val
                if bar.close >= tp_price:
                    exit_reason = f"ATR止盈 目标={tp_price:.2f}"

            if exit_reason:
                self.ctx.close_position(bar.symbol)
                self.ctx.log(f"平仓[{exit_reason}] @ {bar.close} PnL={pnl_pct:.4%}")
                self.daily_trades = self.daily_trades + 1
                self.pyramid_count = 0
                self.trailing_stop = Decimal("0")
                self.entry_price = Decimal("0")
                if pnl < Decimal("0"):
                    self.consecutive_losses = self.consecutive_losses + 1
                else:
                    self.consecutive_losses = 0
                return

            # 6. 加仓逻辑：盈利 >= 1.5 ATR + MACD 动量持续增强
            if (
                self.pyramid_count < self.pyramid_max
                and pnl >= Decimal("1.5") * atr_val
                and prev_hist is not None
                and histogram > prev_hist
                and histogram > Decimal("0")
                and htf_bias == "BULLISH"
                and regime == "GREEN"
            ):
                scale = self.position_scale()
                add_amount = self.ctx.equity * self.position_size_pct * scale / bar.close
                if add_amount > Decimal("0"):
                    self.ctx.buy(bar.symbol, add_amount)
                    self.pyramid_count = self.pyramid_count + 1
                    self.ctx.log(
                        f"加仓[{self.pyramid_count}] @ {bar.close} "
                        f"PnL={pnl:.2f} ATR={atr_val:.2f}"
                    )
            return

        # ============ 入场逻辑（仅做多）============
        if self.daily_trades >= self.max_daily_trades:
            return

        # 三层过滤：仅 GREEN 环境 + 5m BULLISH 时开仓
        if regime != "GREEN":
            return
        if htf_bias != "BULLISH":
            return

        # 阳线确认
        if bar.close <= bar.open:
            return

        # 做多信号：EMA金叉 + 趋势均线上方 + MACD正且增强 + 放量
        macd_momentum = (
            prev_hist is not None
            and histogram > Decimal("0")
            and histogram > prev_hist
        )
        if (
            ema_f > ema_s
            and bar.close > ema_t
            and macd_momentum
            and vol_ma > Decimal("0")
            and bar.volume > vol_ma * self.min_vol_mult
        ):
            scale = self.position_scale()
            amount = self.ctx.equity * self.position_size_pct * scale / bar.close
            if amount > Decimal("0"):
                self.ctx.buy(bar.symbol, amount)
                self.entry_price = bar.close
                self.trailing_stop = Decimal("0")
                self.pyramid_count = 0
                self.ctx.log(
                    f"做多[EMA金叉+MACD动量] @ {bar.close} "
                    f"ATR={atr_val:.2f} 5m={htf_bias} 环境={regime}"
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

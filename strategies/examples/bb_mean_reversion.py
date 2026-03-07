"""保守型均值回归策略 — Bollinger Band Scalping

在震荡行情中，利用布林带上下轨作为超买超卖区域，配合 RSI 过滤假信号，
执行高胜率的均值回归交易。

适用场景：横盘震荡、区间盘整（如 ETH/USDT $1,900–$2,150 区间）。

注意事项：
- 现货市场仅支持做多。做空信号（BB上轨+RSI超买）转为平仓信号。
- 止损/止盈/移动止损均在 on_bar 中逐K线检查，非实时订单。
- 1m 级别最大延迟 1 分钟，对于 0.2%–0.3% 级别的止损可接受。

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
- statistics: 统计函数模块

策略参数通过 self.ctx.params.get(key, default) 获取。
"""

from decimal import Decimal


class BBMeanReversionStrategy(Strategy):  # noqa: F821
    """保守型布林带均值回归策略

    做多条件：价格触及 BB 下轨 + RSI 超卖 + 放量确认
    平仓条件：止损 / 止盈 / 追踪止损 / 均值回归 / RSI 超买 / 时间止损

    参数:
        bb_period (int): 布林带周期，默认 20
        bb_std (float): 布林带标准差倍数，默认 2.0
        rsi_period (int): RSI 周期，默认 14
        rsi_oversold (int): RSI 超卖阈值，默认 30
        rsi_overbought (int): RSI 超买阈值，默认 70
        volume_ma_period (int): 成交量均线周期，默认 20
        position_size_pct (float): 每笔仓位占总资金比例，默认 0.02
        take_profit_pct (float): 止盈百分比，默认 0.003
        stop_loss_pct (float): 止损百分比，默认 0.002
        trailing_stop_pct (float): 追踪止损百分比，默认 0.0015
        max_daily_trades (int): 日内最大交易次数，默认 10
        cooldown_bars (int): 交易冷却K线数，默认 1
        min_volume_multiplier (float): 最小成交量倍数，默认 1.2
        min_bb_bandwidth (float): 最小带宽（排除极窄盘整），默认 0.005
        time_exit_bars (int): 持仓超时K线数（未盈利则平仓），默认 5
        daily_loss_limit (float): 日内止损上限占总资金比，默认 0.003
    """

    def on_init(self):
        # 指标参数
        self.bb_period = self.ctx.params.get("bb_period", 20)
        self.bb_std = Decimal(str(self.ctx.params.get("bb_std", 2.0)))
        self.rsi_period = self.ctx.params.get("rsi_period", 14)
        self.rsi_oversold = Decimal(str(self.ctx.params.get("rsi_oversold", 30)))
        self.rsi_overbought = Decimal(str(self.ctx.params.get("rsi_overbought", 70)))
        self.vol_ma_period = self.ctx.params.get("volume_ma_period", 20)

        # 仓位管理
        self.position_size_pct = Decimal(str(self.ctx.params.get("position_size_pct", 0.02)))
        self.max_daily_trades = self.ctx.params.get("max_daily_trades", 10)

        # 出场参数
        self.take_profit_pct = Decimal(str(self.ctx.params.get("take_profit_pct", 0.003)))
        self.stop_loss_pct = Decimal(str(self.ctx.params.get("stop_loss_pct", 0.002)))
        self.trailing_stop_pct = Decimal(str(self.ctx.params.get("trailing_stop_pct", 0.0015)))
        self.time_exit_bars = self.ctx.params.get("time_exit_bars", 5)
        self.mean_reversion_threshold = Decimal(
            str(self.ctx.params.get("mean_reversion_threshold", 0.001))
        )

        # 过滤器
        self.min_vol_mult = Decimal(str(self.ctx.params.get("min_volume_multiplier", 1.2)))
        self.min_bb_bandwidth = Decimal(str(self.ctx.params.get("min_bb_bandwidth", 0.005)))
        self.cooldown_bars = self.ctx.params.get("cooldown_bars", 1)

        # 日内止损
        self.daily_loss_limit = Decimal(str(self.ctx.params.get("daily_loss_limit", 0.003)))

        # 运行状态（沙箱不允许 _ 前缀属性）
        self.daily_trades = 0
        self.last_trade_day = None
        self.bars_since_trade = 999
        self.entry_bar = 0
        self.highest_since_entry = Decimal("0")
        self.bar_count = 0
        self.daily_start_equity = Decimal("0")

    def on_bar(self, bar):
        self.bar_count = self.bar_count + 1
        self.bars_since_trade = self.bars_since_trade + 1

        # 日切重置
        today = bar.time.date()
        if today != self.last_trade_day:
            self.daily_trades = 0
            self.last_trade_day = today
            self.daily_start_equity = self.ctx.equity

        # 日内止损检查
        if self.daily_start_equity > Decimal("0"):
            daily_pnl = (self.ctx.equity - self.daily_start_equity) / self.daily_start_equity
            if daily_pnl <= -self.daily_loss_limit:
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

            # 1. 固定止损
            if pnl_pct <= -self.stop_loss_pct:
                exit_reason = f"止损 PnL={pnl_pct:.4%}"

            # 2. 固定止盈
            elif pnl_pct >= self.take_profit_pct:
                exit_reason = f"止盈 PnL={pnl_pct:.4%}"

            # 3. 追踪止损（仅在盈利时生效）
            elif pnl_pct > Decimal("0") and self.highest_since_entry > Decimal("0"):
                trail_stop = self.highest_since_entry * (Decimal("1") - self.trailing_stop_pct)
                if bar.close <= trail_stop:
                    exit_reason = f"追踪止损 最高={self.highest_since_entry:.2f}"

            # 4. 均值回归：价格回到 BB 中轨附近
            if exit_reason is None and middle > Decimal("0"):
                if abs(bar.close - middle) / middle < self.mean_reversion_threshold:
                    exit_reason = f"回归中轨 {middle:.2f}"

            # 5. RSI 超买退出（替代做空信号）
            if exit_reason is None and rsi_val >= self.rsi_overbought:
                exit_reason = f"RSI超买={rsi_val:.1f}"

            # 6. 时间止损：持仓超时且未盈利
            if exit_reason is None and bars_held >= self.time_exit_bars:
                if pnl_pct < Decimal("0.001"):
                    exit_reason = f"超时{bars_held}根 PnL={pnl_pct:.4%}"

            if exit_reason:
                self.ctx.close_position(bar.symbol)
                self.ctx.log(f"平仓[{exit_reason}] @ {bar.close}")
                self.daily_trades = self.daily_trades + 1
                self.bars_since_trade = 0
                self.highest_since_entry = Decimal("0")
            return

        # ============ 入场逻辑（仅做多）============
        if self.daily_trades >= self.max_daily_trades:
            return
        if self.bars_since_trade < self.cooldown_bars:
            return

        # 带宽过滤：排除极度缩量横盘
        if middle > Decimal("0"):
            bandwidth = (upper - lower) / middle
            if bandwidth < self.min_bb_bandwidth:
                return

        # 做多信号：BB 下轨 + RSI 超卖 + 放量
        if (
            bar.close <= lower
            and rsi_val <= self.rsi_oversold
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
                    f"RSI={rsi_val:.1f} 带宽={bandwidth:.4f}"
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

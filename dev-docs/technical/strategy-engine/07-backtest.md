# 回测引擎

> **关联文档**: [进程管理](./06-process.md), [策略上下文](./04-context.md)

## 1. 回测流程

```python
def run_backtest(strategy: Strategy, context: BacktestContext, config: dict):
    """执行回测"""

    # 加载历史数据
    klines = load_klines(
        exchange=config["exchange"],
        symbol=config["symbol"],
        timeframe=config["timeframe"],
        start=config["start_time"],
        end=config["end_time"]
    )

    total = len(klines)
    trades = []
    equity_curve = []

    for i, bar in enumerate(klines):
        # 更新当前 bar
        context.current_bar = bar
        context.bar_index = i

        # 调用策略
        try:
            signal.alarm(30)  # 30秒超时
            strategy.on_bar(bar)
            signal.alarm(0)
        except TimeoutError:
            context.log("策略执行超时", level="error")
            break

        # 模拟撮合
        filled_orders = context.match_orders(bar)
        for order in filled_orders:
            strategy.on_order(order)
            if order.status == "filled":
                trade = create_trade(order)
                trades.append(trade)
                strategy.on_trade(trade)

        # 记录权益
        equity_curve.append({
            "time": bar.time,
            "equity": context.equity,
            "cash": context.cash,
            "position_value": context.position * bar.close
        })

        # 报告进度
        if i % 100 == 0:
            progress = (i + 1) / total * 100
            report_progress(progress)

    # 生成报告
    return generate_report(trades, equity_curve, config)
```

## 2. 撮合模拟

```python
class BacktestContext(StrategyContext):
    """回测上下文"""

    def __init__(self, config: dict):
        self.initial_capital = Decimal(str(config["initial_capital"]))
        self.commission_rate = Decimal(str(config.get("commission_rate", "0.001")))
        self.slippage = Decimal(str(config.get("slippage", "0")))

        self._cash = self.initial_capital
        self._position = Decimal("0")
        self._pending_orders: List[Order] = []

    def match_orders(self, bar: Bar) -> List[Order]:
        """撮合挂单"""
        filled = []

        for order in self._pending_orders[:]:
            if order.type == "market":
                # 市价单：以开盘价 +/- 滑点成交
                fill_price = bar.open * (1 + self.slippage if order.side == "buy" else 1 - self.slippage)
                self._fill_order(order, fill_price)
                filled.append(order)

            elif order.type == "limit":
                # 限价单：检查价格是否触及
                if order.side == "buy" and bar.low <= order.price:
                    self._fill_order(order, order.price)
                    filled.append(order)
                elif order.side == "sell" and bar.high >= order.price:
                    self._fill_order(order, order.price)
                    filled.append(order)

        # 移除已成交订单
        for order in filled:
            self._pending_orders.remove(order)

        return filled

    def _fill_order(self, order: Order, price: Decimal):
        """执行成交"""
        value = price * order.amount
        commission = value * self.commission_rate

        if order.side == "buy":
            self._cash -= (value + commission)
            self._position += order.amount
        else:
            self._cash += (value - commission)
            self._position -= order.amount

        order.status = "filled"
        order.avg_price = price
        order.filled = order.amount
```

## 3. 报告生成

```python
def generate_report(trades: List, equity_curve: List, config: dict) -> dict:
    """生成回测报告"""

    if not trades:
        return {"error": "无交易记录"}

    initial = config["initial_capital"]
    final = equity_curve[-1]["equity"]
    days = (equity_curve[-1]["time"] - equity_curve[0]["time"]).days

    # 收益计算
    total_return = (final - initial) / initial
    annual_return = (1 + total_return) ** (365 / max(days, 1)) - 1

    # 回撤计算
    peak = initial
    max_drawdown = 0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        drawdown = (peak - point["equity"]) / peak
        max_drawdown = max(max_drawdown, drawdown)

    # 交易统计
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) if trades else 0

    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
    profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # 风险调整收益
    returns = calculate_daily_returns(equity_curve)
    sharpe = calculate_sharpe(returns)
    sortino = calculate_sortino(returns)

    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "max_drawdown": float(max_drawdown),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": float(annual_return / max_drawdown) if max_drawdown > 0 else 0,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_trades": len(trades),
        "avg_holding_period": calculate_avg_holding(trades),
        "equity_curve": equity_curve,
        "trades": trades
    }
```

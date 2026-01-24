# 策略模板

> **关联文档**: [生命周期](./02-lifecycle.md), [策略上下文](./04-context.md)

## 1. 基类定义

```python
from abc import ABC, abstractmethod
from typing import Any
from decimal import Decimal

class Strategy(ABC):
    """策略基类，所有用户策略必须继承此类"""

    # 策略元信息（用户必须定义）
    name: str = ""
    version: str = "1.0.0"
    description: str = ""

    def __init__(self, context: "StrategyContext"):
        self.ctx = context

    def on_init(self) -> None:
        """策略初始化，可选实现"""
        pass

    def on_start(self) -> None:
        """策略启动，可选实现"""
        pass

    @abstractmethod
    def on_bar(self, bar: "Bar") -> None:
        """K 线回调，必须实现"""
        pass

    def on_tick(self, tick: "Tick") -> None:
        """Tick 回调，可选实现"""
        pass

    def on_order(self, order: "Order") -> None:
        """订单状态回调，可选实现"""
        pass

    def on_trade(self, trade: "Trade") -> None:
        """成交回调，可选实现"""
        pass

    def on_stop(self) -> None:
        """策略停止，可选实现"""
        pass

    def on_error(self, error: Exception) -> None:
        """异常处理，可选实现"""
        pass
```

## 2. 示例策略（双均线）

```python
from squant import Strategy, Bar

class DualMA(Strategy):
    """双均线交叉策略"""

    name = "DualMA"
    version = "1.0.0"
    description = "基于双均线交叉的趋势跟踪策略"

    # 策略参数（通过 params_schema 定义类型和默认值）
    fast_period: int = 10
    slow_period: int = 30

    def on_init(self):
        # 预加载历史数据计算初始均线
        self.fast_ma = None
        self.slow_ma = None

    def on_bar(self, bar: Bar):
        # 获取历史收盘价
        closes = self.ctx.get_history("close", self.slow_period + 1)
        if len(closes) < self.slow_period:
            return  # 数据不足

        # 计算均线
        fast_ma = self.ctx.indicator("SMA", closes, self.fast_period)
        slow_ma = self.ctx.indicator("SMA", closes, self.slow_period)

        prev_fast = self.fast_ma
        prev_slow = self.slow_ma
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma

        if prev_fast is None:
            return  # 首次计算，跳过

        # 交叉判断
        position = self.ctx.position

        # 金叉买入
        if prev_fast <= prev_slow and fast_ma > slow_ma:
            if position <= 0:
                self.ctx.buy(amount=self.ctx.calculate_amount(0.95))
                self.ctx.log(f"金叉买入: fast={fast_ma:.2f}, slow={slow_ma:.2f}")

        # 死叉卖出
        elif prev_fast >= prev_slow and fast_ma < slow_ma:
            if position > 0:
                self.ctx.sell(amount=position)
                self.ctx.log(f"死叉卖出: fast={fast_ma:.2f}, slow={slow_ma:.2f}")

    def on_order(self, order):
        self.ctx.log(f"订单更新: {order.id} -> {order.status}")
```

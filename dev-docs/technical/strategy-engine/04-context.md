# 策略上下文

> **关联文档**: [策略模板](./03-template.md)

## 1. 接口定义

```python
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, List

class StrategyContext(ABC):
    """策略上下文接口，提供数据和交易能力"""

    # ========== 数据获取 ==========

    @abstractmethod
    def get_history(self, field: str, count: int) -> List[Decimal]:
        """获取历史数据

        Args:
            field: 字段名 (open, high, low, close, volume)
            count: 数量
        Returns:
            历史数据列表，最新的在最后
        """
        pass

    @abstractmethod
    def get_bar(self, index: int = 0) -> "Bar":
        """获取 K 线

        Args:
            index: 0=当前, -1=上一根, ...
        """
        pass

    @abstractmethod
    def indicator(self, name: str, data: List, *args, **kwargs) -> Decimal:
        """计算技术指标

        Args:
            name: 指标名称 (SMA, EMA, RSI, MACD, ...)
            data: 输入数据
        """
        pass

    # ========== 交易操作 ==========

    @abstractmethod
    def buy(
        self,
        amount: Decimal,
        price: Optional[Decimal] = None,
        order_type: str = "market"
    ) -> str:
        """买入

        Args:
            amount: 数量
            price: 价格（限价单）
            order_type: market | limit
        Returns:
            订单 ID
        """
        pass

    @abstractmethod
    def sell(
        self,
        amount: Decimal,
        price: Optional[Decimal] = None,
        order_type: str = "market"
    ) -> str:
        """卖出"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        pass

    @abstractmethod
    def cancel_all_orders(self) -> int:
        """取消所有挂单，返回取消数量"""
        pass

    @abstractmethod
    def close_position(self) -> Optional[str]:
        """平仓，返回订单 ID"""
        pass

    # ========== 信息查询 ==========

    @property
    @abstractmethod
    def position(self) -> Decimal:
        """当前持仓数量"""
        pass

    @property
    @abstractmethod
    def cash(self) -> Decimal:
        """可用资金"""
        pass

    @property
    @abstractmethod
    def equity(self) -> Decimal:
        """总权益 = 现金 + 持仓价值"""
        pass

    @property
    @abstractmethod
    def current_price(self) -> Decimal:
        """当前价格"""
        pass

    @abstractmethod
    def calculate_amount(self, ratio: float) -> Decimal:
        """计算可买数量

        Args:
            ratio: 资金使用比例 (0-1)
        """
        pass

    # ========== 日志通知 ==========

    @abstractmethod
    def log(self, message: str, level: str = "info") -> None:
        """记录日志"""
        pass

    @abstractmethod
    def notify(self, message: str) -> None:
        """发送通知"""
        pass

    # ========== 参数获取 ==========

    @abstractmethod
    def get_param(self, name: str, default: any = None) -> any:
        """获取策略参数"""
        pass
```

## 2. 上下文实现（回测 vs 实盘）

| 方法 | 回测实现 | 实盘实现 |
|------|----------|----------|
| `get_history()` | 从预加载的历史数据切片 | 从 DB/缓存获取 |
| `buy/sell()` | 模拟撮合，更新虚拟账户 | 调用交易所 API |
| `position` | 虚拟持仓 | 从交易所同步 |
| `cash` | 虚拟资金 | 从交易所同步 |
| `current_price` | 当前 bar 的 close | 实时价格 |
| `log()` | 写入回测日志 | 写入系统日志 |
| `notify()` | 无操作或记录 | 发送 Telegram 等 |

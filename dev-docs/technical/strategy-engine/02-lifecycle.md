# 策略生命周期

> **关联文档**: [引擎架构](./01-architecture.md)

## 1. 生命周期方法

| 方法 | 触发时机 | 用途 | 是否必须 |
|------|----------|------|----------|
| `on_init()` | 策略加载后 | 初始化变量、加载历史数据 | 否 |
| `on_start()` | 策略启动时 | 运行前准备、订阅数据 | 否 |
| `on_bar(bar)` | 每根 K 线完成 | **主要交易逻辑** | **是** |
| `on_tick(tick)` | 每个 Tick | 高频策略逻辑 | 否 |
| `on_order(order)` | 订单状态变化 | 订单管理逻辑 | 否 |
| `on_trade(trade)` | 成交发生 | 成交后处理 | 否 |
| `on_stop()` | 策略停止时 | 清理资源、保存状态 | 否 |
| `on_error(error)` | 异常发生 | 错误处理 | 否 |

## 2. 状态机

```
                    ┌──────────┐
                    │  CREATED │
                    └────┬─────┘
                         │ start()
                         ▼
                    ┌──────────┐
          ┌────────│ STARTING │
          │        └────┬─────┘
          │             │ on_init() + on_start()
          │             ▼
          │        ┌──────────┐
          │   ┌───▶│ RUNNING  │◀───┐
          │   │    └────┬─────┘    │
          │   │         │          │
          │   │    on_bar/tick     │ 恢复
          │   │         │          │
          │   │         ▼          │
          │   │    ┌──────────┐    │
          │   └────│ PAUSED   │────┘
          │        └────┬─────┘
          │             │ stop()
          │             ▼
          │        ┌──────────┐
          └───────▶│ STOPPING │
                   └────┬─────┘
                        │ on_stop()
                        ▼
                   ┌──────────┐
                   │ STOPPED  │
                   └──────────┘

异常路径：
任意状态 ──on_error()──▶ ERROR ──▶ STOPPED
```

## 3. 状态定义

```python
from enum import Enum

class StrategyState(Enum):
    CREATED = "created"      # 已创建，未启动
    STARTING = "starting"    # 启动中
    RUNNING = "running"      # 运行中
    PAUSED = "paused"        # 已暂停
    STOPPING = "stopping"    # 停止中
    STOPPED = "stopped"      # 已停止
    ERROR = "error"          # 异常
```

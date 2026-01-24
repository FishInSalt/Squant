# 交易模块 API

> **关联文档**: [API 规范](./01-conventions.md)

## POST /api/v1/trading/backtest

启动回测。

**请求体**：

```json
{
    "strategy_id": "uuid",
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "start_time": "2024-01-01T00:00:00Z",
    "end_time": "2024-12-31T23:59:59Z",
    "initial_capital": 10000,
    "commission_rate": 0.001,
    "params": {
        "fast_period": 10,
        "slow_period": 30
    }
}
```

**响应**：

```json
{
    "code": 0,
    "data": {
        "run_id": "uuid",
        "status": "pending"
    }
}
```

---

## GET /api/v1/trading/backtest/{run_id}

获取回测状态/结果。

**响应（进行中）**：

```json
{
    "code": 0,
    "data": {
        "run_id": "uuid",
        "status": "running",
        "progress": 45.5,
        "current_date": "2024-06-15"
    }
}
```

**响应（完成）**：

```json
{
    "code": 0,
    "data": {
        "run_id": "uuid",
        "status": "completed",
        "result": {
            "total_return": 0.2534,
            "annual_return": 0.2534,
            "sharpe_ratio": 1.85,
            "max_drawdown": -0.1234,
            "win_rate": 0.62,
            "profit_factor": 2.1,
            "total_trades": 156,
            "equity_curve": [
                {"time": "2024-01-01", "equity": 10000},
                {"time": "2024-01-02", "equity": 10150}
            ],
            "trades": [
                {
                    "entry_time": "2024-01-15T10:00:00Z",
                    "exit_time": "2024-01-16T14:00:00Z",
                    "side": "buy",
                    "entry_price": "42000",
                    "exit_price": "43500",
                    "amount": "0.1",
                    "pnl": "150",
                    "pnl_pct": "3.57"
                }
            ]
        }
    }
}
```

---

## POST /api/v1/trading/paper

启动模拟运行。

**请求体**：

```json
{
    "strategy_id": "uuid",
    "exchange": "binance",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "initial_capital": 10000,
    "params": {
        "fast_period": 10,
        "slow_period": 30
    }
}
```

---

## POST /api/v1/trading/live

启动实盘运行。

**请求体**：

```json
{
    "strategy_id": "uuid",
    "account_id": "uuid",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "params": {
        "fast_period": 10,
        "slow_period": 30
    },
    "risk_rules": ["uuid1", "uuid2"]
}
```

---

## POST /api/v1/trading/runs/{run_id}/stop

停止运行中的策略。

---

## POST /api/v1/trading/runs/{run_id}/emergency-close

紧急平仓。

---

## GET /api/v1/trading/runs

获取运行中/历史策略列表。

**Query 参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mode | string | 否 | backtest, paper, live |
| status | string | 否 | running, stopped, completed, error |
| page | int | 否 | 页码 |

---

## GET /api/v1/trading/runs/{run_id}

获取策略运行详情。

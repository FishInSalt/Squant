# API 接口设计

> **文档版本**: v1.0
> **最后更新**: 2025-01-24

## 文档索引

| 文档 | 描述 |
|------|------|
| [01-conventions.md](./01-conventions.md) | API 规范与约定 |
| [02-market.md](./02-market.md) | 行情模块 API |
| [03-strategy.md](./03-strategy.md) | 策略模块 API |
| [04-trading.md](./04-trading.md) | 交易模块 API |
| [05-order.md](./05-order.md) | 订单模块 API |
| [06-risk.md](./06-risk.md) | 风控模块 API |
| [07-account.md](./07-account.md) | 账户模块 API |
| [08-system.md](./08-system.md) | 系统模块 API |
| [09-websocket.md](./09-websocket.md) | WebSocket API |

## API 概览

| 模块 | 基础路径 | 说明 |
|------|----------|------|
| 行情 | `/api/v1/market` | 行情数据、自选管理 |
| 策略 | `/api/v1/strategies` | 策略上传、管理 |
| 交易 | `/api/v1/trading` | 回测、模拟、实盘 |
| 订单 | `/api/v1/orders` | 订单查询、取消 |
| 风控 | `/api/v1/risk` | 风控规则管理 |
| 账户 | `/api/v1/accounts` | 交易所账户管理 |
| 系统 | `/api/v1/system` | 系统状态、数据管理 |

## 自动生成的文档

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

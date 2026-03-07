# 策略引擎设计

> **文档版本**: v1.0
> **最后更新**: 2025-01-24

## 文档索引

| 文档 | 描述 |
|------|------|
| [01-architecture.md](./01-architecture.md) | 引擎架构概览 |
| [02-lifecycle.md](./02-lifecycle.md) | 策略生命周期与状态机 |
| [03-template.md](./03-template.md) | 策略基类与示例 |
| [04-context.md](./04-context.md) | 策略上下文 API |
| [05-sandbox.md](./05-sandbox.md) | 沙箱安全机制 |
| [06-process-manager.md](./06-process-manager.md) | 进程管理器 |
| [07-backtest.md](./07-backtest.md) | 回测引擎与报告生成 |
| [08-indicators.md](./08-indicators.md) | 技术指标库 |

## 核心概念

| 概念 | 说明 |
|------|------|
| Strategy | 策略基类，用户继承实现交易逻辑 |
| Context | 策略上下文，提供数据和交易能力 |
| Sandbox | 沙箱环境，限制策略代码的能力 |
| ProcessManager | 进程管理器，管理策略进程生命周期 |
| BacktestEngine | 回测引擎，历史数据回放和撮合模拟 |

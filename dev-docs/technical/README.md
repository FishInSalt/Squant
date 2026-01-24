# Squant 技术文档

> **文档版本**: v1.1
> **创建日期**: 2025-01-24
> **维护者**: 后端开发

## 文档索引

### 总览

| 模块 | 目录 | 描述 |
|------|------|------|
| 技术概述 | [overview/](./overview/) | 技术栈选择与理由 |
| 系统架构 | [architecture/](./architecture/) | 系统架构设计 |
| 数据模型 | [data-model/](./data-model/) | 数据库表结构设计 |
| API 设计 | [api/](./api/) | REST + WebSocket 接口规格 |
| 策略引擎 | [strategy-engine/](./strategy-engine/) | 策略引擎设计 |
| 部署方案 | [deployment/](./deployment/) | Docker 部署配置 |

### 详细文档

#### 技术概述 (overview/)

- [技术选型](./overview/01-tech-stack.md) - 技术栈选择与理由

#### 系统架构 (architecture/)

- [架构概览](./architecture/01-overview.md) - 系统架构图和设计原则
- [模块划分](./architecture/02-modules.md) - 模块依赖关系
- [目录结构](./architecture/03-directory.md) - 项目目录规范
- [进程间通信](./architecture/04-ipc.md) - Redis Pub/Sub 设计
- [核心流程](./architecture/05-flows.md) - 策略启动、订单执行、回测流程
- [错误处理](./architecture/06-error-handling.md) - 错误码和重试策略
- [安全设计](./architecture/07-security.md) - API Key 加密、策略沙箱
- [扩展性设计](./architecture/08-extensibility.md) - 交易所适配器、通知渠道

#### 数据模型 (data-model/)

- [ER 图](./data-model/01-er-diagram.md) - 实体关系图
- [核心表结构](./data-model/02-core-tables.md) - 账户、策略、订单等表
- [TimescaleDB](./data-model/03-timescaledb.md) - 时序数据表设计
- [索引设计](./data-model/04-indexes.md) - 索引策略与迁移
- [Redis 缓存](./data-model/05-redis.md) - 缓存 Key 设计

#### API 设计 (api/)

- [API 规范](./api/01-conventions.md) - 请求/响应格式、错误码
- [行情模块](./api/02-market.md) - 行情、K 线、自选接口
- [策略模块](./api/03-strategy.md) - 策略 CRUD 接口
- [交易模块](./api/04-trading.md) - 回测、模拟、实盘接口
- [订单模块](./api/05-order.md) - 订单查询、取消接口
- [风控模块](./api/06-risk.md) - 风控规则、熔断接口
- [账户模块](./api/07-account.md) - 交易所账户管理
- [系统模块](./api/08-system.md) - 系统状态、数据下载
- [WebSocket](./api/09-websocket.md) - 实时推送接口

#### 策略引擎 (strategy-engine/)

- [引擎架构](./strategy-engine/01-architecture.md) - 整体架构图
- [策略生命周期](./strategy-engine/02-lifecycle.md) - 状态机设计
- [策略模板](./strategy-engine/03-template.md) - 基类和示例策略
- [策略上下文](./strategy-engine/04-context.md) - Context 接口设计
- [沙箱安全](./strategy-engine/05-sandbox.md) - 代码限制与资源限制
- [进程管理](./strategy-engine/06-process.md) - ProcessManager 设计
- [回测引擎](./strategy-engine/07-backtest.md) - 回测流程与撮合
- [技术指标](./strategy-engine/08-indicators.md) - 支持的指标列表

#### 部署方案 (deployment/)

- [Docker 配置](./deployment/01-docker.md) - Docker Compose 编排
- [环境变量](./deployment/02-environment.md) - 配置项说明
- [数据持久化](./deployment/03-persistence.md) - Volume 和目录结构
- [备份策略](./deployment/04-backup.md) - 备份与恢复脚本
- [监控与日志](./deployment/05-monitoring.md) - 日志配置与健康检查
- [本地开发](./deployment/06-development.md) - 开发环境搭建

## 关联文档

- [产品需求文档](../requirements/prd/README.md)
- [验收标准](../requirements/acceptance-criteria/README.md)
- [用户故事](../requirements/user-stories/README.md)

## 技术栈概览

```
┌─────────────────────────────────────────────────────────────┐
│                         前端                                │
│     Vue 3 + TypeScript + Naive UI + TradingView Charts     │
├─────────────────────────────────────────────────────────────┤
│                         后端                                │
│              Python 3.12 + FastAPI + SQLAlchemy            │
├─────────────────────────────────────────────────────────────┤
│                        数据层                               │
│           PostgreSQL + TimescaleDB + Redis                 │
├─────────────────────────────────────────────────────────────┤
│                        基础设施                             │
│                 Docker Compose + Caddy                      │
└─────────────────────────────────────────────────────────────┘
```

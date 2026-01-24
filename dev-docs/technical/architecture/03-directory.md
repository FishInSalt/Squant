# 项目目录结构

> **关联文档**: [模块划分](./02-modules.md)

## 完整目录结构

```
squant/
├── pyproject.toml              # 项目配置
├── alembic.ini                 # 数据库迁移配置
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # 后端镜像
├── .env.example                # 环境变量模板
│
├── alembic/                    # 数据库迁移脚本
│   └── versions/
│
├── src/
│   └── squant/
│       ├── __init__.py
│       ├── main.py             # FastAPI 入口
│       ├── config.py           # 配置管理
│       │
│       ├── api/                # Presentation Layer
│       │   ├── __init__.py
│       │   ├── deps.py         # 依赖注入
│       │   ├── router.py       # 路由聚合
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── market.py
│       │       ├── strategy.py
│       │       ├── trading.py
│       │       ├── order.py
│       │       ├── risk.py
│       │       ├── account.py
│       │       └── system.py
│       │
│       ├── websocket/          # WebSocket 处理
│       │   ├── __init__.py
│       │   ├── manager.py      # 连接管理
│       │   └── handlers.py     # 消息处理
│       │
│       ├── services/           # Service Layer
│       │   ├── __init__.py
│       │   ├── market.py
│       │   ├── strategy.py
│       │   ├── trading.py
│       │   ├── order.py
│       │   ├── risk.py
│       │   ├── account.py
│       │   └── system.py
│       │
│       ├── engine/             # 策略引擎
│       │   ├── __init__.py
│       │   ├── manager.py      # 进程管理器
│       │   ├── executor.py     # 策略执行器
│       │   ├── backtest.py     # 回测引擎
│       │   ├── context.py      # 策略上下文
│       │   └── sandbox.py      # 沙箱安全
│       │
│       ├── models/             # 数据模型
│       │   ├── __init__.py
│       │   ├── base.py         # SQLAlchemy Base
│       │   ├── market.py
│       │   ├── strategy.py
│       │   ├── order.py
│       │   ├── risk.py
│       │   └── account.py
│       │
│       ├── schemas/            # Pydantic Schemas
│       │   ├── __init__.py
│       │   ├── market.py
│       │   ├── strategy.py
│       │   ├── trading.py
│       │   ├── order.py
│       │   ├── risk.py
│       │   └── account.py
│       │
│       ├── infra/              # Infrastructure Layer
│       │   ├── __init__.py
│       │   ├── database.py     # 数据库连接
│       │   ├── redis.py        # Redis 连接
│       │   ├── exchange/       # 交易所适配
│       │   │   ├── __init__.py
│       │   │   ├── base.py     # 抽象基类
│       │   │   ├── binance.py
│       │   │   └── okx.py
│       │   └── notification/   # 通知渠道
│       │       ├── __init__.py
│       │       ├── base.py
│       │       └── telegram.py
│       │
│       ├── scheduler/          # 定时任务
│       │   ├── __init__.py
│       │   └── jobs.py
│       │
│       └── utils/              # 工具函数
│           ├── __init__.py
│           ├── crypto.py       # 加密工具
│           ├── logger.py       # 日志配置
│           └── indicators.py   # 技术指标
│
├── strategies/                 # 用户策略目录
│   └── examples/
│       └── dual_ma.py          # 示例策略
│
├── tests/                      # 测试
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
└── frontend/                   # 前端项目
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.ts
        ├── App.vue
        ├── router/
        ├── stores/
        ├── views/
        ├── components/
        └── api/
```

## 关键文件说明

| 文件/目录 | 说明 |
|----------|------|
| `src/squant/main.py` | FastAPI 应用入口 |
| `src/squant/config.py` | Pydantic Settings 配置 |
| `src/squant/api/` | REST API 路由定义 |
| `src/squant/services/` | 核心业务逻辑 |
| `src/squant/engine/` | 策略引擎实现 |
| `src/squant/models/` | SQLAlchemy 模型 |
| `src/squant/schemas/` | Pydantic 数据模型 |
| `src/squant/infra/` | 基础设施实现 |
| `strategies/` | 用户策略文件存放 |
| `tests/` | 测试代码 |

# Squant 项目进度

**更新时间**: 2026-01-24 23:45
**当前分支**: `oc/dev`
**当前 Sprint**: Sprint 2（准备开始）

---

## ✅ 已完成 Sprint

### Sprint 0 - 基础搭建（✅ 已完成）

**目标**: 搭建项目基础架构和开发环境

| 任务 | 状态 | 提交 |
|------|------|------|
| FastAPI + SQLAlchemy 2.0 + Vue 3 + TypeScript 架构搭建 | ✅ | - |
| PostgreSQL + Redis + Docker Compose 配置 | ✅ | - |
| 数据库模型（User, Strategy, Order, StrategyExecution） | ✅ | - |
| 修复 8 个关键问题（安全、配置、依赖） | ✅ | - |

**交付物**:
- ✅ 项目基础代码结构
- ✅ 开发环境配置文档
- ✅ 本地部署成功

**Git 提交**:
- `316da3f` fix: 移除 .env 文件从 Git 跟踪（包含敏感密码）
- `39eb879` fix: 将核心依赖从固定版本改为范围版本
- `4049f78` fix: 移除 settings.local.json 从 Git 跟踪
- `dc6407a` fix: 修复安全问题 - 移除 .env 文件追踪

---

### Sprint 1 - 市场数据与账户配置（✅ 已完成）

**目标**: 实现行情数据展示和交易所账户配置

**完成时间**: 2026-01-24

| 需求 | 状态 | 验收标准 | 提交 |
|------|------|----------|------|
| FR-02: 行情看板 | ✅ 完成 | AC-02 全部通过 | - |
| FR-09: 交易所账户配置 | ✅ 完成 | AC-09 全部通过 | - |

#### 已实现功能

##### FR-02: 行情看板
- ✅ 热门币种实时价格展示（15个币种）
- ✅ 单个币种价格查询
- ✅ K线数据获取（支持多种时间周期：1m, 5m, 15m, 1h, 1d等）
- ✅ 自选币种管理（添加、删除、查看、更新）
- ✅ 市场概览API（热门币种 + 自选列表）

##### FR-09: 交易所账户配置
- ✅ 交易所账户CRUD操作
- ✅ API Key 加密存储（Fernet 对称加密）
- ✅ Binance/OKX API连接验证
- ✅ 创建账户前验证凭证（不保存）
- ✅ 已有账户连接验证
- ✅ 数据库事务保护（try-except-rollback）

#### 技术改进
- ✅ 财务数据类型从 Float 改为 Numeric(20, 8)
- ✅ Enum 值从大写改为小写（如 DRAFT → draft）
- ✅ 移除 JWT 认证（个人研究用系统，不需要）
- ✅ 添加数据库迁移（4个迁移文件）
- ✅ 添加 mypy 配置（类型检查）
- ✅ 代码质量检查全部通过（ruff, mypy）

#### 新增文件（19个）
- `AGENTS.md` - Agent编码指南
- `PROGRESS.md` - 项目进度跟踪
- 4个数据库迁移文件
- `app/models/exchange_account.py` - 交易所账户模型
- `app/models/market_data.py` - 市场数据模型
- `app/api/v1/accounts.py` - 交易所账户API（8个端点）
- `app/api/v1/market.py` - 市场数据API（8个端点）
- `app/market/data_fetcher.py` - Binance数据获取器
- `app/market/exchange_validator.py` - 交易所验证器
- `app/schemas/exchange_account.py` - 账户数据验证
- `app/schemas/market.py` - 市场数据验证
- `app/utils/crypto.py` - 数据加密工具
- `mypy.ini` - 类型检查配置

#### 代码统计
- 新增代码: +1,903行
- 删除代码: -13行
- 净增代码: +1,890行

**Git 提交**:
- `75f4d2c` feat: Sprint 1完成 - 交易所账户配置和市场数据

**交付物**:
- ✅ 交易所账户配置功能（AC-09验收通过）
- ✅ 行情看板功能（AC-02验收通过）
- ✅ 交易所API集成验证

---

## 🎯 当前 Sprint

### Sprint 2 - 策略开发（⏳ 准备开始）

**目标**: 实现策略模板和策略库管理

**计划周期**: 2-3周

**开始时间**: 待定

| 需求 | 优先级 | 状态 | 验收标准 |
|------|--------|------|----------|
| FR-03: 自定义策略模板 | P0 | ⏳ 待开始 | AC-03 |
| FR-04: 策略库构建 | P0 | ⏳ 待开始 | AC-04 |

#### 待实现确认事项
在 Sprint 2 开始前需要确认：
1. **策略编程语言**: Python / JavaScript / 其他？
2. **策略接口方法**: 具体需要哪些回调方法？（on_bar, on_tick, on_order等）
3. **策略文件格式**: 单文件还是多文件？是否支持依赖包？
4. **策略文件大小限制**: 最大支持多少MB？
5. **模板示例复杂度**: 简单示例还是完整策略？

#### 阶段1：策略接口设计（2-3天）
- [ ] 确认策略编程语言
- [ ] 设计策略接口方法
- [ ] 编写策略模板代码
- [ ] 编写接口文档

#### 阶段2：策略校验器（3-4天）
- [ ] 实现语法检查
- [ ] 实现接口完整性检查
- [ ] 实现安全性检查
- [ ] 编写校验器测试

#### 阶段3：策略库API（3-4天）
- [ ] 创建API路由
- [ ] 实现文件上传
- [ ] 实现策略CRUD
- [ ] 实现模板下载
- [ ] 编写API测试

#### 阶段4：前端开发（3-4天）
- [ ] 创建策略库页面
- [ ] 实现文件上传组件
- [ ] 实现策略列表展示
- [ ] 实现策略详情查看
- [ ] 实现策略删除功能

#### 阶段5：示例策略（1-2天）
- [ ] 开发简单移动平均策略
- [ ] 编写策略说明文档
- [ ] 测试策略运行

#### 阶段6：验收测试（2-3天）
- [ ] 根据AC-03进行验收测试
- [ ] 根据AC-04进行验收测试
- [ ] 修复发现的Bug
- [ ] 完善文档

**交付物**:
- ⏳ 策略模板文件（可下载）
- ⏳ 策略接口文档
- ⏳ 策略校验器
- ⏳ 策略管理API（6个端点）
- ⏳ 策略库前端页面
- ⏳ 示例策略（至少1个）

---

## 📋 待办 Sprint

### Sprint 3 - 策略运行（⏳ 待开始）

**目标**: 实现回测、模拟、实盘三种运行模式

**计划周期**: 3-4周

| 需求 | 优先级 | 状态 |
|------|--------|------|
| FR-05: 策略运行模式 | P0 | ⏳ 待开始 |

**交付物**:
- ⏳ 回测功能（AC-05验收通过）
- ⏳ 模拟运行功能（AC-05验收通过）
- ⏳ 实盘运行功能（AC-05验收通过）

---

### Sprint 4 - 监控控制（⏳ 待开始）

**目标**: 实现多策略并发、实时控制、运行监控

**计划周期**: 2-3周

| 需求 | 优先级 | 状态 |
|------|--------|------|
| FR-06: 多策略并发 | P1 | ⏳ 待开始 |
| FR-07: 策略实时控制 | P1 | ⏳ 待开始 |
| FR-08: 策略运行监控 | P2 | ⏳ 待开始 |

**交付物**:
- ⏳ 多策略并发功能（AC-06验收通过）
- ⏳ 策略实时控制功能（AC-07验收通过）
- ⏳ 策略运行监控功能（AC-08验收通过）

---

### Sprint 5 - 优化完善（⏳ 待开始）

**目标**: 完善部署流程，优化性能和用户体验

**计划周期**: 2-3周

| 需求 | 优先级 | 状态 |
|------|--------|------|
| FR-01: 系统运行方式（完善部署） | P1 | ⏳ 待开始 |

**交付物**:
- ⏳ 完整的部署文档
- ⏳ 性能测试报告
- ⏳ 用户使用手册

---

## 📊 总体进度

| Sprint | 状态 | 进度 |
|--------|------|------|
| Sprint 0 - 基础搭建 | ✅ 完成 | 100% |
| Sprint 1 - 核心数据 | ✅ 完成 | 100% |
| Sprint 2 - 策略开发 | ⏳ 准备中 | 0% |
| Sprint 3 - 策略运行 | ⏳ 待开始 | 0% |
| Sprint 4 - 监控控制 | ⏳ 待开始 | 0% |
| Sprint 5 - 优化完善 | ⏳ 待开始 | 0% |
| **总体进度** | - | **40%** |

---

## 🔄 依赖关系图

```
Sprint 0（基础搭建）✅
    └─ FR-01 系统运行方式 ✅
            ↓
Sprint 1（核心数据）✅
    ├─ FR-02 行情看板 ✅ ────┐
    └─ FR-09 交易所账户配置 ✅ ─┤
                               ↓
Sprint 2（策略开发）⏳
    ├─ FR-03 自定义策略模板 ⏳ ─┤
    └─ FR-04 策略库构建 ⏳ ─────┘
                               ↓
Sprint 3（策略运行）⏳
    └─ FR-05 策略运行模式 ⏳ ────┘
                               ↓
Sprint 4（监控控制）⏳
    ├─ FR-06 多策略并发 ⏳ ──────┤
    ├─ FR-07 策略实时控制 ⏳ ────┤
    └─ FR-08 策略运行监控 ⏳ ────┘
                               ↓
Sprint 5（优化完善）⏳
    └─ FR-01 系统运行方式（完善部署）⏳
```

---

## 📝 Git 状态

| 分支 | 状态 | 提交数 |
|------|------|--------|
| `oc/dev` | ✅ 工作区干净 | 6个提交 |

### 最近提交
```
75f4d2c feat: Sprint 1完成 - 交易所账户配置和市场数据
dc6407a fix: 修复安全问题 - 移除 .env 文件追踪
316da3f fix: 移除 .env 文件从 Git 跟踪（包含敏感密码）
39eb879 fix: 将核心依赖从固定版本改为范围版本
4049f78 fix: 移除 settings.local.json 从 Git 跟踪
```

### 状态
```
On branch oc/dev
Your branch is up to date with 'origin/oc/dev'.
Your branch is ahead of 'origin/oc/dev' by 1 commit.
nothing to commit, working tree clean
```

---

## 🚀 快速启动

### 环境准备
```bash
# 启动基础服务
docker-compose up -d postgres redis

# 应用数据库迁移
cd src/backend
alembic upgrade head

# 启动后端
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端（另开终端）
cd src/frontend
npm run dev
```

### 服务地址
| 服务 | 地址 | 说明 |
|------|------|------|
| 后端API | http://localhost:8000 | FastAPI |
| API文档 | http://localhost:8000/docs | Swagger UI |
| 前端 | http://localhost:5173 | Vue 3 |
| PostgreSQL | localhost:5432 | 数据库 |
| Redis | localhost:6379 | 缓存 |

### 已实现的API端点

#### 交易所账户API（8个端点）
- `POST /api/v1/accounts` - 创建账户
- `GET /api/v1/accounts` - 获取账户列表
- `GET /api/v1/accounts/{id}` - 获取单个账户
- `PUT /api/v1/accounts/{id}` - 更新账户
- `DELETE /api/v1/accounts/{id}` - 删除账户
- `POST /api/v1/accounts/{id}/validate` - 验证账户
- `POST /api/v1/accounts/validate` - 验证新凭证
- `GET /health` - 健康检查

#### 市场数据API（8个端点）
- `GET /api/v1/market/tickers` - 热门币种
- `GET /api/v1/market/ticker/{symbol}` - 单个币种
- `GET /api/v1/market/candles/{symbol}` - K线数据
- `GET /api/v1/market/watchlist` - 自选列表
- `POST /api/v1/market/watchlist` - 添加自选
- `PUT /api/v1/market/watchlist/{id}` - 更新自选
- `DELETE /api/v1/market/watchlist/{id}` - 删除自选
- `GET /api/v1/market/overview` - 市场概览

---

## 📌 重要提示

### 环境变量配置
创建 `src/backend/.env` 文件，配置以下变量：
```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/squant

# 加密密钥（必填，用于加密API Key）
ENCRYPTION_KEY=your-32-byte-base64-encoded-key-here

# 调试模式
DEBUG=True
```

### 验证标准参考
- [AC-02: 查看加密货币行情](../dev-docs/requirements/验收标准.md#ac-02)
- [AC-09: 配置交易所账户](../dev-docs/requirements/验收标准.md#ac-09)

---

## 📅 里程碑

| 里程碑 | 时间点 | 状态 | 验收标准 |
|--------|--------|------|----------|
| M1: MVP功能冻结 | Sprint 2结束 | ⏳ 待完成 | FR-02、FR-03、FR-04、FR-09完成 |
| M2: 策略运行可用 | Sprint 3结束 | ⏳ 待完成 | FR-05完成，三种运行模式可用 |
| M3: 系统功能完整 | Sprint 4结束 | ⏳ 待完成 | 所有P0和P1需求完成 |
| M4: 产品发布 | Sprint 5结束 | ⏳ 待完成 | 所有需求完成，部署文档完善 |

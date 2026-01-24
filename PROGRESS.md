# Squant 项目进度

**更新时间**: 2026-01-24
**当前分支**: `oc/dev`

---

## ✅ 当前进度

### Sprint 0 - 基础搭建（已完成）
- FastAPI + SQLAlchemy 2.0 + Vue 3 + TypeScript 架构搭建
- PostgreSQL + Redis + Docker Compose 配置
- 数据库模型（User, Strategy, Order, StrategyExecution）
- 修复 8 个关键问题（安全、配置、依赖）

### Git 状态
- **未推送**: 4 个提交（安全加固修复）
- **未提交修改**: `src/backend/app/core/config.py`

---

## 🎯 接下来要做

### Sprint 1 - 市场数据与账户配置
- [ ] Binance/OKX 交易所数据接口
- [ ] K 线数据获取与存储
- [ ] 实时价格订阅（WebSocket）
- [ ] 账户 API Key 加密存储
- [ ] JWT 认证与授权
- [ ] 监控与日志系统

---

## 🚀 快速启动

```bash
docker-compose up -d
cd src/backend && alembic upgrade head
python -m uvicorn app.main:app --reload
cd src/frontend && npm run dev
```

**服务**: API(8000) | Frontend(5173) | Postgres(5432) | Redis(6379)
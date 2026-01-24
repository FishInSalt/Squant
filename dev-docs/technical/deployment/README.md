# 部署方案

> **文档版本**: v1.0
> **最后更新**: 2025-01-24

## 文档索引

| 文档 | 描述 |
|------|------|
| [01-docker.md](./01-docker.md) | Docker Compose 配置 |
| [02-environment.md](./02-environment.md) | 环境变量配置 |
| [03-persistence.md](./03-persistence.md) | 数据持久化 |
| [04-backup.md](./04-backup.md) | 备份与恢复 |
| [05-monitoring.md](./05-monitoring.md) | 监控与日志 |
| [06-development.md](./06-development.md) | 本地开发环境 |

## 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Compose                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │  Caddy  │  │ Backend │  │Frontend │  │  Redis  │        │
│  │ (Proxy) │  │(FastAPI)│  │ (Nginx) │  │ (Cache) │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
│                    │                                         │
│              ┌─────┴─────┐                                   │
│              │ PostgreSQL │                                  │
│              │+TimescaleDB│                                  │
│              └───────────┘                                   │
└─────────────────────────────────────────────────────────────┘
```

## 快速启动

```bash
# 生产环境
docker compose up -d

# 开发环境
./scripts/dev.sh all
```

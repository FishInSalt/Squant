# 环境变量

> **关联文档**: [Docker 配置](./01-docker.md)

## 1. 环境变量模板

```bash
# .env.example

# ============ 应用配置 ============
APP_NAME=Squant
APP_ENV=production  # development | staging | production
DEBUG=false
SECRET_KEY=your-secret-key-at-least-32-characters-long
API_PREFIX=/api/v1

# ============ 数据库配置 ============
DB_USER=squant
DB_PASSWORD=your-secure-database-password
DB_NAME=squant
DB_HOST=postgres
DB_PORT=5432
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# ============ Redis 配置 ============
REDIS_PASSWORD=your-secure-redis-password
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}

# ============ 交易所 API ============
# Binance
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=false

# OKX
OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=

# ============ 安全配置 ============
# API Key 加密密钥 (32 字节 base64 编码)
ENCRYPTION_KEY=your-32-byte-encryption-key-base64

# JWT 配置
JWT_SECRET_KEY=${SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# ============ 日志配置 ============
LOG_LEVEL=INFO
LOG_FORMAT=json  # json | text
LOG_FILE=/app/logs/squant.log

# ============ 策略引擎配置 ============
STRATEGY_MAX_PROCESSES=5
STRATEGY_MEMORY_LIMIT_MB=512
STRATEGY_CPU_LIMIT_SECONDS=60
STRATEGY_SANDBOX_ENABLED=true

# ============ 风控配置 ============
RISK_MAX_POSITION_RATIO=0.3
RISK_MAX_DAILY_LOSS_RATIO=0.05
RISK_MAX_ORDERS_PER_MINUTE=10

# ============ Caddy/HTTPS 配置 ============
ACME_EMAIL=admin@example.com

# ============ 监控配置 ============
METRICS_ENABLED=true
METRICS_PORT=9090
```

## 2. 环境变量加载顺序

```
1. 系统环境变量
2. .env 文件
3. .env.local 文件 (git ignored)
4. Docker Compose environment 配置
```

## 3. 敏感信息管理

```python
# squant/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, field_validator
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "Squant"
    app_env: str = "production"
    debug: bool = False
    secret_key: SecretStr

    # 数据库
    database_url: SecretStr

    # Redis
    redis_url: SecretStr

    # 加密密钥
    encryption_key: SecretStr

    # 交易所 API (可选)
    binance_api_key: SecretStr | None = None
    binance_api_secret: SecretStr | None = None

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

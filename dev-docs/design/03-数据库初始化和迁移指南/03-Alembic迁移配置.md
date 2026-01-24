## 4. Alembic迁移配置

### 4.1 初始化Alembic

```bash
# 在项目根目录执行
alembic init alembic
```

### 4.2 配置alembic.ini

```ini
# alembic/alembic.ini

[alembic]
script_location = alembic
file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s
timezone = UTC

# 数据库连接URL (从环境变量读取)
# sqlalchemy.url = postgresql+asyncpg://user:password@localhost:5432/squant

[post_write_hooks]
hooks = black
black.type = console_scripts
black.entrypoint = black
black.options = -l 79 REVISION_SCRIPT_FILENAME
```

### 4.3 配置env.py

```python
# alembic/env.py

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 导入模型
from models import Base
from models.user import User
from models.account import Account
from models.watchlist import Watchlist
from models.strategy import Strategy
from models.strategy_version import StrategyVersion
from models.execution import StrategyExecution
from models.order import Order
from models.position import Position
from models.strategy_log import StrategyLog
from models.backtest_result import BacktestResult
from models.alert import Alert
from models.kline import Kline

# Alembic Config对象
config = context.config

# 解释Python日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 添加模型的MetaData用于自动生成迁移
target_metadata = Base.metadata


# 从环境变量读取数据库URL
import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://squant:squant_password@localhost:5432/squant")
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """离线运行迁移(生成SQL脚本)"""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """执行迁移"""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步运行迁移"""

    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线运行迁移"""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## 5. 创建迁移脚本

### 5.1 生成初始迁移

```bash
# 自动生成迁移脚本
alembic revision --autogenerate -m "Initial migration"

# 输出示例:
# Creating /path/to/alembic/versions/20240124_100000_initial_migration.py ...
```

### 5.2 手动创建迁移

```bash
# 手动创建迁移脚本(当自动生成不准确时)
alembic revision -m "Add backtest result fields"
```

---

## 6. 执行迁移

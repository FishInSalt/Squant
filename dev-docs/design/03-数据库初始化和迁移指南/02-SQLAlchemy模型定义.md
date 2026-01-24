## 3. 数据库Schema定义 (SQLAlchemy)

### 3.1 基础模型定义

```python
# models/base.py

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有模型的基类"""

    pass


class TimestampMixin:
    """时间戳混入类"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )


class UUIDMixin:
    """UUID主键混入类"""

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False
    )
```

---

### 3.2 用户模型

```python
# models/user.py

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class User(Base, TimestampMixin, UUIDMixin):
    """用户表"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 关系
    strategies: Mapped[list["Strategy"]] = relationship(
        "Strategy",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    accounts: Mapped[list["Account"]] = relationship(
        "Account",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    watchlist: Mapped[list["Watchlist"]] = relationship(
        "Watchlist",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"
```

---

### 3.3 交易所账户模型

```python
# models/account.py

from sqlalchemy import String, LargeBinary, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class Account(Base, TimestampMixin, UUIDMixin):
    """交易所账户表"""

    __tablename__ = "accounts"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    exchange: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    account_name: Mapped[str] = mapped_column(String(100), nullable=True)
    api_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    api_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    passphrase_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="accounts")
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="account",
        cascade="all, delete-orphan"
    )
    positions: Mapped[list["Position"]] = relationship(
        "Position",
        back_populates="account",
        cascade="all, delete-orphan"
    )
    executions: Mapped[list["StrategyExecution"]] = relationship(
        "StrategyExecution",
        back_populates="account"
    )

    def __repr__(self) -> str:
        return f"<Account(id={self.id}, exchange={self.exchange}, account_name={self.account_name})>"
```

---

### 3.4 自选币种模型

```python
# models/watchlist.py

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class Watchlist(Base, TimestampMixin, UUIDMixin):
    """自选币种表"""

    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "exchange", name="uq_watchlist_user_symbol_exchange"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="watchlist")

    def __repr__(self) -> str:
        return f"<Watchlist(id={self.id}, symbol={self.symbol}, exchange={self.exchange})>"
```

---

### 3.5 策略模型

```python
# models/strategy.py

from sqlalchemy import String, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin, UUIDMixin


class Strategy(Base, TimestampMixin, UUIDMixin):
    """策略表"""

    __tablename__ = "strategies"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="python", nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=True)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="strategies")
    versions: Mapped[list["StrategyVersion"]] = relationship(
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan"
    )
    executions: Mapped[list["StrategyExecution"]] = relationship(
        "StrategyExecution",
        back_populates="strategy",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Strategy(id={self.id}, name={self.name}, version={self.version})>"
```

---

### 3.6 策略版本模型

```python
# models/strategy_version.py

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, UniqueConstraint

from .base import Base, TimestampMixin, UUIDMixin


class StrategyVersion(Base, TimestampMixin, UUIDMixin):
    """策略版本表"""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关系
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="versions")

    def __repr__(self) -> str:
        return f"<StrategyVersion(id={self.id}, version={self.version})>"
```

---

### 3.7 策略执行记录模型

```python
# models/execution.py

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin, UUIDMixin


class StrategyExecution(Base, TimestampMixin, UUIDMixin):
    """策略执行记录表"""

    __tablename__ = "strategy_executions"

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),  # ✅ 策略删除,执行记录保留
        nullable=False,
        index=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    run_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # backtest, paper, live
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # running, stopped, error
    config: Mapped[dict] = mapped_column(JSONB, nullable=True)
    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # 关系
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="executions")
    account: Mapped["Account"] = relationship("Account", back_populates="executions")
    orders: Mapped[list["Order"]] = relationship(
        "Order",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    positions: Mapped[list["Position"]] = relationship(
        "Position",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    logs: Mapped[list["StrategyLog"]] = relationship(
        "StrategyLog",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    backtest_result: Mapped["BacktestResult" | None] = relationship(
        "BacktestResult",
        back_populates="execution",
        uselist=False,
        cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert",
        back_populates="execution",
        cascade="all, delete-orphan"
    )

    @property
    def runtime(self) -> float | None:
        """计算运行时长(秒)"""
        if not self.start_time:
            return None
        end = self.end_time or datetime.now(self.start_time.tzinfo)
        return (end - self.start_time).total_seconds()

    def __repr__(self) -> str:
        return f"<StrategyExecution(id={self.id}, run_mode={self.run_mode}, status={self.status})>"
```

---

### 3.8 订单模型

```python
# models/order.py

from datetime import datetime
from sqlalchemy import String, Numeric, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    """订单表"""
    
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint('exchange', 'exchange_order_id', name='uq_orders_exchange_order_id'),
    )
    
    # 内部主键（UUID，无业务含义）
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )
    
    # 交易所订单ID（业务ID，带唯一约束）
    exchange_order_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    
    execution_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategy_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    account_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),  # 统一使用SET NULL,避免删除账户但保留执行记录的数据一致性问题
        nullable=False,
        index=True
    )
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # buy, sell
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)  # market, limit, stop_limit
    price: Mapped[str | None] = mapped_column(Numeric(20, 8), nullable=True)
    quantity: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    filled_quantity: Mapped[str] = mapped_column(Numeric(20, 8), default="0", nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # new, partial_filled, filled, canceled, rejected
    is_simulation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # 关系
    execution: Mapped["StrategyExecution"] = relationship("StrategyExecution", back_populates="orders")
    account: Mapped["Account"] = relationship("Account", back_populates="orders")
    
    @property
    def remaining_quantity(self) -> str:
        """剩余数量"""
        return str(float(self.quantity) - float(self.filled_quantity))
    
    def __repr__(self) -> str:
        return f"<Order(id={self.id}, exchange_order_id={self.exchange_order_id}, symbol={self.symbol}, side={self.side}, status={self.status})>"
```

---

### 3.9 持仓模型

```python
# models/position.py

from sqlalchemy import String, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base import Base, TimestampMixin, UUIDMixin


class Position(Base, TimestampMixin, UUIDMixin):
    """持仓表"""

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "execution_id", "symbol", "is_simulation",
            name="uq_position_account_execution_symbol_simulation"
        ),
    )

    account_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),  # 统一使用SET NULL,避免数据不一致
        nullable=False,
        index=True
    )
    execution_id: Mapped[PG_UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategy_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # long, short
    quantity: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    entry_price: Mapped[str | None] = mapped_column(Numeric(20, 8), nullable=True)
    current_price: Mapped[str | None] = mapped_column(Numeric(20, 8), nullable=True)
    unrealized_pnl: Mapped[str] = mapped_column(Numeric(20, 8), default="0", nullable=False)
    is_simulation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 关系
    account: Mapped["Account"] = relationship("Account", back_populates="positions")
    execution: Mapped["StrategyExecution" | None] = relationship("StrategyExecution", back_populates="positions")

    @property
    def pnl_percent(self) -> str | None:
        """盈亏百分比"""
        if not self.entry_price or float(self.entry_price) == 0:
            return None
        if self.side == "long":
            return str((float(self.current_price) - float(self.entry_price)) / float(self.entry_price) * 100)
        else:
            return str((float(self.entry_price) - float(self.current_price)) / float(self.entry_price) * 100)

    def __repr__(self) -> str:
        return f"<Position(id={self.id}, symbol={self.symbol}, side={self.side}, quantity={self.quantity})>"
```

---

### 3.10 策略日志模型

```python
# models/strategy_log.py

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from .base import Base, TimestampMixin, UUIDMixin


class StrategyLog(Base, TimestampMixin, UUIDMixin):
    """策略日志表"""

    __tablename__ = "strategy_logs"

    execution_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategy_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # debug, info, warning, error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # 关系
    execution: Mapped["StrategyExecution"] = relationship("StrategyExecution", back_populates="logs")

    def __repr__(self) -> str:
        return f"<StrategyLog(id={self.id}, level={self.level}, message={self.message[:50]}...)>"
```

---

### 3.11 回测结果模型

```python
# models/backtest_result.py

from datetime import date
from sqlalchemy import String, Numeric, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base import Base, TimestampMixin, UUIDMixin


class BacktestResult(Base, TimestampMixin, UUIDMixin):
    """回测结果表"""

    __tablename__ = "backtest_results"

    execution_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategy_executions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    strategy_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),  # ✅ 策略删除,回测结果保留
        nullable=False,
        index=True
    )
    strategy_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),  # ✅ 策略删除,回测结果保留
        nullable=False,
        index=True
    )
    total_return: Mapped[str | None] = mapped_column(Numeric(10, 4), nullable=True)
    annual_return: Mapped[str | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown: Mapped[str | None] = mapped_column(Numeric(10, 4), nullable=True)
    sharpe_ratio: Mapped[str | None] = mapped_column(Numeric(10, 4), nullable=True)
    win_rate: Mapped[str | None] = mapped_column(Numeric(5, 4), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profit_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loss_trades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)

    # 关系
    execution: Mapped["StrategyExecution"] = relationship("StrategyExecution", back_populates="backtest_result")
    strategy: Mapped["Strategy"] = relationship("Strategy")

    @property
    def avg_win(self) -> str | None:
        """平均盈利"""
        if not self.profit_trades or self.profit_trades == 0:
            return None
        # 需要从交易记录中计算
        return None

    @property
    def avg_loss(self) -> str | None:
        """平均亏损"""
        if not self.loss_trades or self.loss_trades == 0:
            return None
        # 需要从交易记录中计算
        return None

    def __repr__(self) -> str:
        return f"<BacktestResult(id={self.id}, total_return={self.total_return})>"
```

---

### 3.12 告警模型

```python
# models/alert.py

from sqlalchemy import String, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base import Base, TimestampMixin, UUIDMixin


class Alert(Base, TimestampMixin, UUIDMixin):
    """告警表"""

    __tablename__ = "alerts"

    execution_id: Mapped[PG_UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategy_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # error, warning, info
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high, critical
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # 关系
    execution: Mapped["StrategyExecution" | None] = relationship("StrategyExecution", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert(id={self.id}, type={self.type}, severity={self.severity}, title={self.title})>"
```

---

### 3.13 K线数据模型

```python
# models/kline.py

from datetime import datetime
from sqlalchemy import String, Numeric, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import BIGINT

from .base import Base, TimestampMixin


class Kline(Base, TimestampMixin):
    """K线数据表 (时序数据)"""

    __tablename__ = "klines"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    interval: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # 1m, 5m, 1h, etc.
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    high_price: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    low_price: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    close_price: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[str] = mapped_column(Numeric(20, 8), nullable=False)
    quote_volume: Mapped[str | None] = mapped_column(Numeric(20, 8), nullable=True)
    trades_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 注意: 这是一个复合唯一约束
    __table_args__ = (
        UniqueConstraint(
            'exchange', 'symbol', 'interval', 'open_time',
            name='uq_klines_exchange_symbol_interval_time'
        ),
    )

    def __repr__(self) -> str:
        return f"<Kline(exchange={self.exchange}, symbol={self.symbol}, interval={self.interval}, open_time={self.open_time})>"
```

---

## 4. Alembic迁移配置

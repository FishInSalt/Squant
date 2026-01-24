from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class ExecutionMode(str, enum.Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class ExecutionStatus(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StrategyExecution(Base):
    __tablename__ = "strategy_executions"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"))
    user_id = Column(Integer, nullable=False)
    mode = Column(Enum(ExecutionMode), default=ExecutionMode.BACKTEST)
    status = Column(Enum(ExecutionStatus), default=ExecutionStatus.RUNNING)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    profit = Column(Integer, default=0)
    trades_count = Column(Integer, default=0)
    error_message = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

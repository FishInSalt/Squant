"""Risk management models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin
from .enums import RiskRuleType

if TYPE_CHECKING:
    from .strategy import StrategyRun


class RiskRule(Base, UUIDMixin, TimestampMixin):
    """Risk control rule definition."""

    __tablename__ = "risk_rules"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[RiskRuleType] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    triggers: Mapped[list["RiskTrigger"]] = relationship(back_populates="rule", lazy="selectin")

    def __repr__(self) -> str:
        return f"<RiskRule(id={self.id}, name={self.name}, type={self.type})>"


class RiskTrigger(Base, UUIDMixin):
    """Risk rule trigger record."""

    __tablename__ = "risk_triggers"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("risk_rules.id", ondelete="CASCADE"),
        nullable=True,  # Nullable to support in-memory risk checks without DB rules
    )
    run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Relationships
    rule: Mapped["RiskRule | None"] = relationship(back_populates="triggers")
    run: Mapped["StrategyRun | None"] = relationship()

    __table_args__ = (
        Index("idx_risk_triggers_time", "time"),
        Index("idx_risk_triggers_rule_id", "rule_id"),
        Index("idx_risk_triggers_run_id", "run_id"),
    )

    def __repr__(self) -> str:
        return f"<RiskTrigger(id={self.id}, rule_id={self.rule_id}, type={self.trigger_type})>"


class CircuitBreakerEvent(Base, UUIDMixin):
    """Circuit breaker event record.

    Tracks when the circuit breaker is triggered, including manual
    and automatic triggers.
    """

    __tablename__ = "circuit_breaker_events"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)  # manual / auto
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False)  # api / rule:xxx
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sessions_stopped: Mapped[int] = mapped_column(nullable=False, default=0)
    positions_closed: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (Index("idx_circuit_breaker_events_time", "time"),)

    def __repr__(self) -> str:
        return f"<CircuitBreakerEvent(id={self.id}, time={self.time}, type={self.trigger_type})>"

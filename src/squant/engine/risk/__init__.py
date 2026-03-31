"""Risk management module for live trading.

Provides risk controls and validation for order execution.
"""

from squant.engine.risk.manager import RiskManager
from squant.engine.risk.models import (
    RiskAction,
    RiskCheckResult,
    RiskConfig,
    RiskRule,
    RiskRuleType,
    RiskState,
)

# Mapping from legacy risk state keys to current unified keys.
# Old sessions persisted in DB may use the left-side names.
_RISK_STATE_KEY_RENAMES = {
    "daily_loss_limit_pct": "daily_loss_limit",
    "total_loss_limit_pct": "total_loss_limit",
    "max_position_size_pct": "max_position_size",
    "max_order_size_pct": "max_order_size",
    "circuit_breaker_triggered": "circuit_breaker_active",
    "max_drawdown_pct": "max_drawdown",
}


def normalize_risk_state_keys(risk_state: dict | None) -> dict | None:
    """Rename legacy risk state keys to unified names.

    Used when reading risk_state from DB (old sessions may have old key names).
    """
    if not risk_state:
        return risk_state
    result = {}
    for key, value in risk_state.items():
        new_key = _RISK_STATE_KEY_RENAMES.get(key, key)
        if new_key not in result:
            result[new_key] = value
    return result


__all__ = [
    "RiskAction",
    "RiskCheckResult",
    "RiskConfig",
    "RiskManager",
    "RiskRule",
    "RiskRuleType",
    "RiskState",
    "normalize_risk_state_keys",
]

"""Order state synchronization utilities for live trading.

Handles synchronization between exchange order state and local tracking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from squant.models.enums import OrderSide, OrderStatus, OrderType

if TYPE_CHECKING:
    from squant.infra.exchange.types import OrderResponse

logger = logging.getLogger(__name__)


@dataclass
class OrderStateChange:
    """Represents a change in order state.

    Used to track state transitions for logging and event handling.
    """

    order_id: str
    old_status: OrderStatus
    new_status: OrderStatus
    old_filled: Decimal
    new_filled: Decimal
    fill_delta: Decimal
    timestamp: datetime

    @property
    def has_new_fill(self) -> bool:
        """Check if there was a new fill."""
        return self.fill_delta > 0

    @property
    def is_status_change(self) -> bool:
        """Check if status changed."""
        return self.old_status != self.new_status


class OrderStateTracker:
    """Tracks order state and detects changes.

    Used to compare order states between polls or updates
    and detect meaningful changes (new fills, status transitions).
    """

    def __init__(self) -> None:
        """Initialize order state tracker."""
        self._states: dict[str, dict] = {}  # order_id -> last known state

    def update_state(self, order_id: str, response: OrderResponse) -> OrderStateChange | None:
        """Update tracked state and return change if any.

        Args:
            order_id: Internal order ID.
            response: Order response from exchange.

        Returns:
            OrderStateChange if there was a meaningful change, None otherwise.
        """
        old_state = self._states.get(order_id)

        new_state = {
            "status": response.status,
            "filled": response.filled,
            "avg_price": response.avg_price,
            "fee": response.fee,
            "timestamp": datetime.now(UTC),
        }

        self._states[order_id] = new_state

        if old_state is None:
            # First time tracking this order
            return None

        # Check for changes
        old_status = old_state["status"]
        old_filled = old_state["filled"]
        fill_delta = response.filled - old_filled

        if old_status != response.status or fill_delta > 0:
            return OrderStateChange(
                order_id=order_id,
                old_status=old_status,
                new_status=response.status,
                old_filled=old_filled,
                new_filled=response.filled,
                fill_delta=fill_delta,
                timestamp=datetime.now(UTC),
            )

        return None

    def remove_order(self, order_id: str) -> None:
        """Remove order from tracking.

        Args:
            order_id: Order ID to remove.
        """
        self._states.pop(order_id, None)

    def get_tracked_orders(self) -> list[str]:
        """Get list of tracked order IDs.

        Returns:
            List of order IDs being tracked.
        """
        return list(self._states.keys())

    def clear(self) -> None:
        """Clear all tracked state."""
        self._states.clear()


class OrderReconciler:
    """Reconciles local order state with exchange state.

    Handles discrepancies between local tracking and exchange reality.
    """

    def __init__(self) -> None:
        """Initialize order reconciler."""
        self._reconciliation_log: list[dict] = []

    def reconcile(
        self,
        local_orders: dict[str, dict],
        exchange_orders: list[OrderResponse],
    ) -> list[dict]:
        """Reconcile local orders with exchange orders.

        Args:
            local_orders: Dict of local order tracking (internal_id -> state).
            exchange_orders: List of open orders from exchange.

        Returns:
            List of discrepancies found.
        """
        discrepancies: list[dict] = []

        # Build exchange order lookup by client_order_id (internal_id)
        exchange_by_client_id: dict[str, OrderResponse] = {}
        for order in exchange_orders:
            if order.client_order_id:
                exchange_by_client_id[order.client_order_id] = order

        # Check local orders against exchange
        for internal_id, local_state in local_orders.items():
            if internal_id in exchange_by_client_id:
                # Order exists on exchange - check state matches
                exchange_order = exchange_by_client_id[internal_id]
                if self._has_discrepancy(local_state, exchange_order):
                    discrepancies.append(
                        {
                            "type": "state_mismatch",
                            "order_id": internal_id,
                            "local_status": local_state.get("status"),
                            "exchange_status": exchange_order.status,
                            "local_filled": local_state.get("filled"),
                            "exchange_filled": exchange_order.filled,
                        }
                    )
            else:
                # Order not in open orders - might be filled/cancelled
                if not self._is_terminal_status(local_state.get("status")):
                    discrepancies.append(
                        {
                            "type": "missing_on_exchange",
                            "order_id": internal_id,
                            "local_status": local_state.get("status"),
                        }
                    )

        # Check exchange orders that we don't track
        for client_id, order in exchange_by_client_id.items():
            if client_id not in local_orders:
                discrepancies.append(
                    {
                        "type": "untracked_exchange_order",
                        "order_id": order.order_id,
                        "client_order_id": client_id,
                        "status": order.status,
                    }
                )

        if discrepancies:
            self._reconciliation_log.append(
                {
                    "timestamp": datetime.now(UTC),
                    "discrepancies": discrepancies,
                }
            )
            logger.warning(f"Found {len(discrepancies)} order discrepancies")

        return discrepancies

    def _has_discrepancy(self, local_state: dict, exchange_order: OrderResponse) -> bool:
        """Check if there's a discrepancy between local and exchange state.

        Args:
            local_state: Local order state dict.
            exchange_order: Order from exchange.

        Returns:
            True if discrepancy exists.
        """
        local_status = local_state.get("status")
        local_filled = local_state.get("filled", Decimal("0"))

        # Status mismatch (excluding terminal states that might race)
        if local_status != exchange_order.status:
            # Allow submitted -> partial/filled transition lag
            if not (
                local_status == OrderStatus.SUBMITTED
                and exchange_order.status in (OrderStatus.PARTIAL, OrderStatus.FILLED)
            ):
                return True

        # Filled amount mismatch (significant difference)
        return abs(local_filled - exchange_order.filled) > Decimal("0.00001")

    def _is_terminal_status(self, status: OrderStatus | None) -> bool:
        """Check if status is a terminal state.

        Args:
            status: Order status.

        Returns:
            True if terminal (filled, cancelled, rejected).
        """
        if status is None:
            return False
        return status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )

    def get_reconciliation_log(self) -> list[dict]:
        """Get reconciliation history.

        Returns:
            List of reconciliation events.
        """
        return self._reconciliation_log.copy()


def parse_ws_order_update(data: dict) -> dict:
    """Parse WebSocket order update from OKX format.

    Args:
        data: Raw WebSocket order data from OKX.

    Returns:
        Parsed order update dict.
    """
    # OKX order state mapping
    state_map = {
        "live": OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIAL,
        "filled": OrderStatus.FILLED,
        "canceled": OrderStatus.CANCELLED,
        "mmp_canceled": OrderStatus.CANCELLED,
    }

    side_map = {
        "buy": OrderSide.BUY,
        "sell": OrderSide.SELL,
    }

    type_map = {
        "market": OrderType.MARKET,
        "limit": OrderType.LIMIT,
    }

    return {
        "order_id": data.get("ordId"),
        "client_order_id": data.get("clOrdId"),
        "symbol": _from_okx_symbol(data.get("instId", "")),
        "side": side_map.get(data.get("side", ""), OrderSide.BUY),
        "type": type_map.get(data.get("ordType", ""), OrderType.LIMIT),
        "status": state_map.get(data.get("state", ""), OrderStatus.PENDING),
        "amount": Decimal(data.get("sz", "0")),
        "filled": Decimal(data.get("accFillSz", "0")),
        "price": Decimal(data.get("px", "0")) if data.get("px") else None,
        "avg_price": Decimal(data.get("avgPx", "0")) if data.get("avgPx") else None,
        "fee": Decimal(data.get("fee", "0")) if data.get("fee") else Decimal("0"),
        "fee_currency": data.get("feeCcy"),
        "timestamp": datetime.now(UTC),
    }


def _from_okx_symbol(symbol: str) -> str:
    """Convert OKX symbol to standard format.

    Args:
        symbol: OKX symbol (e.g., "BTC-USDT").

    Returns:
        Standard symbol (e.g., "BTC/USDT").
    """
    return symbol.replace("-", "/")

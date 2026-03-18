"""Order service for order management."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from squant.infra.exchange.base import ExchangeAdapter
from squant.infra.exchange.exceptions import (
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
)
from squant.infra.exchange.exceptions import (
    OrderNotFoundError as ExchangeOrderNotFound,
)
from squant.infra.exchange.types import (
    CancelOrderRequest,
    OrderRequest,
)
from squant.infra.exchange.types import (
    OrderResponse as ExchangeOrderResponse,
)
from squant.infra.repository import BaseRepository
from squant.models.enums import OrderSide, OrderStatus, OrderType
from squant.models.order import Order, Trade

if TYPE_CHECKING:
    from squant.models.exchange import ExchangeAccount

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    """Order not found in database."""

    def __init__(self, order_id: str | UUID):
        self.order_id = str(order_id)
        super().__init__(f"Order not found: {order_id}")


class OrderValidationError(Exception):
    """Order validation failed."""

    pass


class OrderRepository(BaseRepository[Order]):
    """Repository for Order model with specialized queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_exchange_oid(self, exchange: str, exchange_oid: str) -> Order | None:
        """Get order by exchange order ID."""
        stmt = select(Order).where(
            Order.exchange == exchange,
            Order.exchange_oid == exchange_oid,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_account(
        self,
        account_id: str | UUID,
        *,
        status: OrderStatus | list[OrderStatus] | None = None,
        symbol: str | None = None,
        side: OrderSide | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """List orders for an account with filters."""
        stmt = select(Order).where(Order.account_id == str(account_id))

        if status is not None:
            if isinstance(status, list):
                stmt = stmt.where(Order.status.in_(status))
            else:
                stmt = stmt.where(Order.status == status)

        if symbol is not None:
            stmt = stmt.where(Order.symbol == symbol)

        if side is not None:
            stmt = stmt.where(Order.side == side)

        if start_time is not None:
            stmt = stmt.where(Order.created_at >= start_time)

        if end_time is not None:
            stmt = stmt.where(Order.created_at <= end_time)

        stmt = stmt.order_by(Order.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_orders(
        self,
        account_id: str | UUID,
        symbol: str | None = None,
    ) -> list[Order]:
        """List open (non-terminal) orders for an account."""
        open_statuses = [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
        return await self.list_by_account(
            account_id,
            status=open_statuses,
            symbol=symbol,
            limit=1000,  # Reasonable limit for open orders
        )

    async def count_by_account(
        self,
        account_id: str | UUID,
        status: OrderStatus | list[OrderStatus] | None = None,
        symbol: str | None = None,
        side: OrderSide | None = None,
    ) -> int:
        """Count orders for an account."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Order).where(Order.account_id == str(account_id))

        if status is not None:
            if isinstance(status, list):
                stmt = stmt.where(Order.status.in_(status))
            else:
                stmt = stmt.where(Order.status == status)

        if symbol is not None:
            stmt = stmt.where(Order.symbol == symbol)

        if side is not None:
            stmt = stmt.where(Order.side == side)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_all(
        self,
        *,
        account_id: str | UUID | None = None,
        status: OrderStatus | list[OrderStatus] | None = None,
        symbol: str | None = None,
        side: OrderSide | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """List orders across all accounts with filters."""
        stmt = select(Order)

        if account_id is not None:
            stmt = stmt.where(Order.account_id == str(account_id))

        if status is not None:
            if isinstance(status, list):
                stmt = stmt.where(Order.status.in_(status))
            else:
                stmt = stmt.where(Order.status == status)

        if symbol is not None:
            stmt = stmt.where(Order.symbol == symbol)

        if side is not None:
            stmt = stmt.where(Order.side == side)

        if start_time is not None:
            stmt = stmt.where(Order.created_at >= start_time)

        if end_time is not None:
            stmt = stmt.where(Order.created_at <= end_time)

        stmt = stmt.order_by(Order.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(
        self,
        account_id: str | UUID | None = None,
        status: OrderStatus | list[OrderStatus] | None = None,
        symbol: str | None = None,
        side: OrderSide | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """Count orders across all accounts."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Order)

        if account_id is not None:
            stmt = stmt.where(Order.account_id == str(account_id))

        if status is not None:
            if isinstance(status, list):
                stmt = stmt.where(Order.status.in_(status))
            else:
                stmt = stmt.where(Order.status == status)

        if symbol is not None:
            stmt = stmt.where(Order.symbol == symbol)

        if side is not None:
            stmt = stmt.where(Order.side == side)

        if start_time is not None:
            stmt = stmt.where(Order.created_at >= start_time)

        if end_time is not None:
            stmt = stmt.where(Order.created_at <= end_time)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_all_open(
        self,
        symbol: str | None = None,
    ) -> list[Order]:
        """List open (non-terminal) orders across all accounts."""
        open_statuses = [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
        return await self.list_all(
            status=open_statuses,
            symbol=symbol,
            limit=1000,
        )

    async def get_all_stats_by_status(self) -> dict[OrderStatus, int]:
        """Get order counts grouped by status across all accounts.

        Returns:
            Dict mapping OrderStatus to count.
        """
        from sqlalchemy import func

        stmt = (
            select(Order.status, func.count())
            .group_by(Order.status)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def list_by_run(
        self,
        run_id: str | UUID,
        *,
        status: OrderStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """List orders for a strategy run.

        Args:
            run_id: Strategy run ID.
            status: Optional status filter.
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            List of Order records ordered by created_at desc.
        """
        stmt = select(Order).where(Order.run_id == str(run_id))
        if status is not None:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_run(
        self,
        run_id: str | UUID,
        status: OrderStatus | None = None,
    ) -> int:
        """Count orders for a strategy run.

        Args:
            run_id: Strategy run ID.
            status: Optional status filter.

        Returns:
            Order count.
        """
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Order).where(Order.run_id == str(run_id))
        if status is not None:
            stmt = stmt.where(Order.status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_stats_by_status(
        self,
        account_id: str | UUID,
    ) -> dict[OrderStatus, int]:
        """Get order counts grouped by status in a single query.

        Args:
            account_id: Account ID to filter by.

        Returns:
            Dict mapping OrderStatus to count.
        """
        from sqlalchemy import func

        stmt = (
            select(Order.status, func.count())
            .where(Order.account_id == str(account_id))
            .group_by(Order.status)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}


class TradeRepository(BaseRepository[Trade]):
    """Repository for Trade model."""

    def __init__(self, session: AsyncSession):
        super().__init__(Trade, session)

    async def list_by_order(self, order_id: str | UUID) -> list[Trade]:
        """List all trades for an order."""
        stmt = select(Trade).where(Trade.order_id == str(order_id)).order_by(Trade.timestamp)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class OrderService:
    """Service for managing orders.

    This service handles the full order lifecycle:
    - Creating orders (persisting to DB + submitting to exchange)
    - Canceling orders
    - Syncing order status from exchange
    - Querying order history
    """

    def __init__(
        self,
        session: AsyncSession,
        exchange: ExchangeAdapter,
        account: "ExchangeAccount",
    ):
        """Initialize order service.

        Args:
            session: Database session for persistence.
            exchange: Exchange adapter for trading operations.
            account: Exchange account to use for orders.
        """
        self.session = session
        self.exchange = exchange
        self.account = account
        self.order_repo = OrderRepository(session)
        self.trade_repo = TradeRepository(session)

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal | None = None,
        client_order_id: str | None = None,
        run_id: str | UUID | None = None,
    ) -> Order:
        """Create and submit a new order.

        The order is first persisted to the database with PENDING status,
        then submitted to the exchange. The order record is updated with
        the exchange response.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT").
            side: Order side (BUY/SELL).
            order_type: Order type (MARKET/LIMIT).
            amount: Order amount in base currency.
            price: Limit price (required for limit orders).
            client_order_id: Client-specified order ID.
            run_id: Strategy run ID if order is from a strategy.

        Returns:
            The created Order record.

        Raises:
            OrderValidationError: If order parameters are invalid.
            ExchangeAPIError: If exchange rejects the order.
        """
        # Validate
        if order_type == OrderType.LIMIT and price is None:
            raise OrderValidationError("Limit orders require a price")

        if amount <= 0:
            raise OrderValidationError("Amount must be positive")

        # Create order record with PENDING status
        order = await self.order_repo.create(
            account_id=str(self.account.id),
            run_id=str(run_id) if run_id else None,
            exchange=self.account.exchange,
            symbol=symbol,
            side=side,
            type=order_type,
            amount=amount,
            price=price,
            status=OrderStatus.PENDING,
        )

        try:
            # Submit to exchange
            request = OrderRequest(
                symbol=symbol,
                side=side,
                type=order_type,
                amount=amount,
                price=price,
                client_order_id=client_order_id,
            )
            response = await self.exchange.place_order(request)

            # Update order with exchange response
            try:
                order = await self._update_order_from_response(order, response)
            except Exception as db_err:
                # DB update failed but exchange order exists — attempt to cancel
                # to prevent zombie orders (ORD-1)
                logger.error(
                    f"Failed to update order {order.id} after exchange submission "
                    f"(exchange_oid={response.order_id}): {db_err}"
                )
                try:
                    await self.exchange.cancel_order(
                        CancelOrderRequest(
                            symbol=symbol,
                            order_id=response.order_id,
                        )
                    )
                    logger.info(f"Compensating cancel sent for zombie order {response.order_id}")
                except Exception as cancel_err:
                    logger.critical(
                        f"ZOMBIE ORDER: exchange_oid={response.order_id}, "
                        f"symbol={symbol}, side={side.value}, amount={amount}. "
                        f"DB update failed: {db_err}. Cancel also failed: {cancel_err}"
                    )
                raise db_err

        except Exception as e:
            # Mark order as rejected on exchange/DB error
            try:
                order = await self.order_repo.update(
                    order.id,
                    status=OrderStatus.REJECTED,
                    reject_reason=str(e),
                )
            except Exception:
                logger.error(f"Failed to mark order {order.id} as rejected: {e}")
            raise

        return order

    async def cancel_order(
        self,
        order_id: str | UUID,
    ) -> Order:
        """Cancel an existing order.

        Args:
            order_id: Database order ID.

        Returns:
            The updated Order record.

        Raises:
            OrderNotFoundError: If order not found in database.
            ExchangeAPIError: If exchange rejects the cancellation.
        """
        order = await self.order_repo.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)

        # Check if order can be cancelled
        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            raise OrderValidationError(f"Cannot cancel order with status: {order.status}")

        if not order.exchange_oid:
            # Order was never submitted to exchange, just mark as cancelled
            order = await self.order_repo.update(
                order.id,
                status=OrderStatus.CANCELLED,
            )
            return order

        # Cancel on exchange
        request = CancelOrderRequest(
            symbol=order.symbol,
            order_id=order.exchange_oid,
        )
        response = await self.exchange.cancel_order(request)

        # Update order with response
        order = await self._update_order_from_response(order, response)
        return order

    async def get_order(self, order_id: str | UUID) -> Order:
        """Get order by database ID.

        Args:
            order_id: Database order ID.

        Returns:
            The Order record.

        Raises:
            OrderNotFoundError: If order not found.
        """
        order = await self.order_repo.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order

    async def get_order_by_exchange_oid(self, exchange_oid: str) -> Order:
        """Get order by exchange order ID.

        Args:
            exchange_oid: Exchange order ID.

        Returns:
            The Order record.

        Raises:
            OrderNotFoundError: If order not found.
        """
        order = await self.order_repo.get_by_exchange_oid(self.account.exchange, exchange_oid)
        if order is None:
            raise OrderNotFoundError(exchange_oid)
        return order

    async def sync_order(self, order_id: str | UUID) -> Order:
        """Sync order status from exchange.

        Fetches the latest order status from the exchange and updates
        the database record.

        Args:
            order_id: Database order ID.

        Returns:
            The updated Order record.

        Raises:
            OrderNotFoundError: If order not found in database.
            ExchangeAPIError: If exchange request fails.
        """
        order = await self.order_repo.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)

        if not order.exchange_oid:
            # No exchange order ID, nothing to sync
            return order

        try:
            response = await self.exchange.get_order(order.symbol, order.exchange_oid)
            order = await self._update_order_from_response(order, response)
        except ExchangeOrderNotFound:
            # Order not found on exchange, mark as rejected if still pending
            if order.status == OrderStatus.PENDING:
                order = await self.order_repo.update(
                    order.id,
                    status=OrderStatus.REJECTED,
                    reject_reason="Order not found on exchange",
                )

        return order

    async def sync_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Sync all open orders from exchange.

        Fetches all open orders from the exchange and updates the
        corresponding database records.

        Args:
            symbol: Optional symbol filter.

        Returns:
            List of updated Order records.

        Raises:
            ExchangeAuthenticationError: If authentication fails.
            ExchangeConnectionError: If connection fails after retries.
        """
        # Get open orders from exchange
        exchange_orders = await self.exchange.get_open_orders(symbol)

        # Build lookup map by exchange order ID
        exchange_order_map = {o.order_id: o for o in exchange_orders}

        # Get local open orders
        local_orders = await self.order_repo.list_open_orders(self.account.id, symbol=symbol)

        updated_orders = []
        sync_failures = []

        for local_order in local_orders:
            if local_order.exchange_oid and local_order.exchange_oid in exchange_order_map:
                # Update from exchange data
                response = exchange_order_map[local_order.exchange_oid]
                local_order = await self._update_order_from_response(local_order, response)
                del exchange_order_map[local_order.exchange_oid]
            elif local_order.exchange_oid:
                # Order not in exchange open orders - fetch full status
                try:
                    local_order = await self.sync_order(local_order.id)
                except ExchangeAuthenticationError:
                    # Authentication errors should not be silently swallowed
                    raise
                except (ExchangeConnectionError, ExchangeRateLimitError) as e:
                    # Transient errors - log and continue with other orders
                    logger.warning(
                        f"Failed to sync order {local_order.id} (transient error): {e}. "
                        "Will retry on next sync."
                    )
                    sync_failures.append((local_order.id, str(e)))
                except ExchangeOrderNotFound:
                    # Order was likely filled or cancelled - mark as synced
                    logger.info(
                        f"Order {local_order.id} not found on exchange - "
                        "may have been filled or cancelled externally."
                    )
                except Exception as e:
                    # Unexpected errors - log with full context
                    logger.error(
                        f"Unexpected error syncing order {local_order.id}: {e}",
                        exc_info=True,
                    )
                    sync_failures.append((local_order.id, str(e)))
            updated_orders.append(local_order)

        # Log summary if there were failures
        if sync_failures:
            logger.warning(
                f"Order sync completed with {len(sync_failures)} failures: "
                f"{[f'{oid}' for oid, _ in sync_failures]}"
            )

        return updated_orders

    async def list_orders(
        self,
        *,
        status: OrderStatus | list[OrderStatus] | None = None,
        symbol: str | None = None,
        side: OrderSide | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """List orders with filters.

        Args:
            status: Filter by status (single or list).
            symbol: Filter by trading pair.
            side: Filter by side (BUY/SELL).
            start_time: Filter orders created after this time.
            end_time: Filter orders created before this time.
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            List of Order records.
        """
        return await self.order_repo.list_by_account(
            self.account.id,
            status=status,
            symbol=symbol,
            side=side,
            start_time=start_time,
            end_time=end_time,
            offset=offset,
            limit=limit,
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Get all open orders.

        Args:
            symbol: Optional symbol filter.

        Returns:
            List of open Order records.
        """
        return await self.order_repo.list_open_orders(self.account.id, symbol=symbol)

    async def count_orders(
        self,
        status: OrderStatus | list[OrderStatus] | None = None,
        symbol: str | None = None,
        side: OrderSide | None = None,
    ) -> int:
        """Count orders with optional filters.

        Args:
            status: Filter by status.
            symbol: Filter by trading pair.
            side: Filter by order side.

        Returns:
            Order count.
        """
        return await self.order_repo.count_by_account(
            self.account.id, status=status, symbol=symbol, side=side
        )

    async def get_order_stats(self) -> dict[str, int]:
        """Get order statistics by status in a single query.

        Returns:
            Dict with keys: total, pending, submitted, partial, filled, cancelled, rejected.
        """
        stats = await self.order_repo.get_stats_by_status(self.account.id)

        # Build response with all status counts
        result = {
            "total": sum(stats.values()),
            "pending": stats.get(OrderStatus.PENDING, 0),
            "submitted": stats.get(OrderStatus.SUBMITTED, 0),
            "partial": stats.get(OrderStatus.PARTIAL, 0),
            "filled": stats.get(OrderStatus.FILLED, 0),
            "cancelled": stats.get(OrderStatus.CANCELLED, 0),
            "rejected": stats.get(OrderStatus.REJECTED, 0),
        }
        return result

    async def _update_order_from_response(
        self,
        order: Order,
        response: ExchangeOrderResponse,
    ) -> Order:
        """Update order record from exchange response.

        Args:
            order: Order to update.
            response: Exchange response.

        Returns:
            Updated Order.

        Raises:
            OrderNotFoundError: If order no longer exists in database.
        """
        update_data: dict = {
            "exchange_oid": response.order_id,
            "status": response.status,
            "filled": response.filled,
        }

        if response.avg_price is not None:
            update_data["avg_price"] = response.avg_price

        # Only update price if response has one and order doesn't
        if response.price is not None and order.price is None:
            update_data["price"] = response.price

        updated = await self.order_repo.update(order.id, **update_data)
        if updated is None:
            # Order was deleted between exchange call and database update
            raise OrderNotFoundError(order.id)
        return updated

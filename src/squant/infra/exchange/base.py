"""Abstract base class for exchange adapters."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from .types import (
    AccountBalance,
    Balance,
    CancelOrderRequest,
    Candlestick,
    OrderRequest,
    OrderResponse,
    Ticker,
    TimeFrame,
)


class ExchangeAdapter(ABC):
    """Abstract base class for exchange adapters.

    All exchange implementations must inherit from this class and implement
    the abstract methods for consistent API across different exchanges.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Exchange name (e.g., 'okx', 'binance')."""
        ...

    @property
    @abstractmethod
    def is_testnet(self) -> bool:
        """Whether connected to testnet/sandbox."""
        ...

    # Connection management

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange.

        Raises:
            ExchangeConnectionError: If connection fails.
            ExchangeAuthenticationError: If authentication fails.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connection and cleanup resources."""
        ...

    async def __aenter__(self) -> "ExchangeAdapter":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object
    ) -> None:
        """Async context manager exit."""
        await self.close()

    # Account methods

    @abstractmethod
    async def get_balance(self) -> AccountBalance:
        """Get account balance for all currencies.

        Returns:
            AccountBalance with all currency balances.

        Raises:
            ExchangeAuthenticationError: If not authenticated.
            ExchangeAPIError: If API request fails.
        """
        ...

    async def get_balance_currency(self, currency: str) -> Balance | None:
        """Get balance for a specific currency.

        Args:
            currency: Currency symbol (e.g., 'BTC', 'USDT').

        Returns:
            Balance for the currency, or None if not found.
        """
        account = await self.get_balance()
        return account.get_balance(currency)

    # Market data methods

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker for a trading pair.

        Args:
            symbol: Trading pair in standard format (e.g., 'BTC/USDT').

        Returns:
            Ticker data for the symbol.

        Raises:
            ExchangeAPIError: If API request fails.
        """
        ...

    @abstractmethod
    async def get_tickers(self, symbols: Sequence[str] | None = None) -> list[Ticker]:
        """Get tickers for multiple trading pairs.

        Args:
            symbols: List of trading pairs. If None, returns all available tickers.

        Returns:
            List of Ticker data.

        Raises:
            ExchangeAPIError: If API request fails.
        """
        ...

    @abstractmethod
    async def get_candlesticks(
        self,
        symbol: str,
        timeframe: TimeFrame,
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Candlestick]:
        """Get OHLCV candlestick data.

        Args:
            symbol: Trading pair in standard format (e.g., 'BTC/USDT').
            timeframe: Candlestick time frame.
            limit: Maximum number of candles to return (default 100).
            start_time: Start timestamp in milliseconds (optional).
            end_time: End timestamp in milliseconds (optional).

        Returns:
            List of Candlestick data, sorted by timestamp ascending.

        Raises:
            ExchangeAPIError: If API request fails.
        """
        ...

    # Order methods

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order.

        Args:
            request: Order placement request.

        Returns:
            Order response with order details.

        Raises:
            InvalidOrderError: If order parameters are invalid.
            ExchangeAPIError: If API request fails.
        """
        ...

    @abstractmethod
    async def cancel_order(self, request: CancelOrderRequest) -> OrderResponse:
        """Cancel an existing order.

        Args:
            request: Cancel order request with order ID.

        Returns:
            Updated order response.

        Raises:
            OrderNotFoundError: If order doesn't exist.
            ExchangeAPIError: If API request fails.
        """
        ...

    @abstractmethod
    async def get_order(self, symbol: str, order_id: str) -> OrderResponse:
        """Get order details by ID.

        Args:
            symbol: Trading pair in standard format.
            order_id: Exchange order ID.

        Returns:
            Order response with order details.

        Raises:
            OrderNotFoundError: If order doesn't exist.
            ExchangeAPIError: If API request fails.
        """
        ...

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        """Get all open (unfilled) orders.

        Args:
            symbol: Trading pair to filter by (optional).
                   If None, returns all open orders.

        Returns:
            List of open orders.

        Raises:
            ExchangeAPIError: If API request fails.
        """
        ...

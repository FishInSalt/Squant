"""Exchange adapter exceptions."""


class ExchangeError(Exception):
    """Base exception for all exchange-related errors."""

    def __init__(self, message: str, exchange: str | None = None) -> None:
        self.message = message
        self.exchange = exchange
        super().__init__(message)


class ExchangeConnectionError(ExchangeError):
    """Failed to connect to exchange."""

    pass


class ExchangeAuthenticationError(ExchangeError):
    """Authentication failed (invalid API key, secret, or passphrase)."""

    pass


class ExchangeRateLimitError(ExchangeError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        exchange: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, exchange)
        self.retry_after = retry_after


class ExchangeAPIError(ExchangeError):
    """Exchange API returned an error."""

    def __init__(
        self,
        message: str,
        exchange: str | None = None,
        code: str | None = None,
        response_data: dict | None = None,
    ) -> None:
        super().__init__(message, exchange)
        self.code = code
        self.response_data = response_data


class OrderNotFoundError(ExchangeError):
    """Order not found on exchange."""

    def __init__(
        self,
        message: str,
        exchange: str | None = None,
        order_id: str | None = None,
    ) -> None:
        super().__init__(message, exchange)
        self.order_id = order_id


class InvalidOrderError(ExchangeError):
    """Invalid order parameters."""

    def __init__(
        self,
        message: str,
        exchange: str | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message, exchange)
        self.field = field

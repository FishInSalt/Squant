"""Unit tests for exchange exceptions."""

from __future__ import annotations

import pytest

from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)


class TestExchangeError:
    """Tests for ExchangeError base exception."""

    def test_create_with_message(self):
        """Test creating error with message only."""
        error = ExchangeError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.exchange is None

    def test_create_with_exchange(self):
        """Test creating error with exchange name."""
        error = ExchangeError("Connection failed", exchange="okx")

        assert error.message == "Connection failed"
        assert error.exchange == "okx"

    def test_is_exception(self):
        """Test ExchangeError is an Exception."""
        error = ExchangeError("Test error")

        assert isinstance(error, Exception)

    def test_can_be_raised(self):
        """Test error can be raised and caught."""
        with pytest.raises(ExchangeError) as exc_info:
            raise ExchangeError("Test error", exchange="binance")

        assert exc_info.value.exchange == "binance"


class TestExchangeConnectionError:
    """Tests for ExchangeConnectionError."""

    def test_create_connection_error(self):
        """Test creating connection error."""
        error = ExchangeConnectionError("Failed to connect", exchange="okx")

        assert error.message == "Failed to connect"
        assert error.exchange == "okx"

    def test_inherits_from_exchange_error(self):
        """Test inherits from ExchangeError."""
        error = ExchangeConnectionError("Connection timeout")

        assert isinstance(error, ExchangeError)
        assert isinstance(error, Exception)

    def test_can_be_caught_as_exchange_error(self):
        """Test can be caught as ExchangeError."""
        with pytest.raises(ExchangeError):
            raise ExchangeConnectionError("Network error")


class TestExchangeAuthenticationError:
    """Tests for ExchangeAuthenticationError."""

    def test_create_auth_error(self):
        """Test creating authentication error."""
        error = ExchangeAuthenticationError("Invalid API key", exchange="binance")

        assert error.message == "Invalid API key"
        assert error.exchange == "binance"

    def test_inherits_from_exchange_error(self):
        """Test inherits from ExchangeError."""
        error = ExchangeAuthenticationError("Auth failed")

        assert isinstance(error, ExchangeError)

    def test_can_be_caught_as_exchange_error(self):
        """Test can be caught as ExchangeError."""
        with pytest.raises(ExchangeError):
            raise ExchangeAuthenticationError("Invalid signature")


class TestExchangeRateLimitError:
    """Tests for ExchangeRateLimitError."""

    def test_create_rate_limit_error(self):
        """Test creating rate limit error."""
        error = ExchangeRateLimitError("Rate limit exceeded", exchange="okx")

        assert error.message == "Rate limit exceeded"
        assert error.exchange == "okx"
        assert error.retry_after is None

    def test_create_with_retry_after(self):
        """Test creating error with retry_after."""
        error = ExchangeRateLimitError(
            "Too many requests",
            exchange="binance",
            retry_after=30.0,
        )

        assert error.retry_after == 30.0

    def test_inherits_from_exchange_error(self):
        """Test inherits from ExchangeError."""
        error = ExchangeRateLimitError("Rate limited")

        assert isinstance(error, ExchangeError)

    def test_can_access_retry_after(self):
        """Test can access retry_after attribute."""
        with pytest.raises(ExchangeRateLimitError) as exc_info:
            raise ExchangeRateLimitError("Wait", retry_after=60.0)

        assert exc_info.value.retry_after == 60.0


class TestExchangeAPIError:
    """Tests for ExchangeAPIError."""

    def test_create_api_error(self):
        """Test creating API error."""
        error = ExchangeAPIError("API request failed", exchange="okx")

        assert error.message == "API request failed"
        assert error.exchange == "okx"
        assert error.code is None
        assert error.response_data is None

    def test_create_with_code(self):
        """Test creating error with code."""
        error = ExchangeAPIError(
            "Insufficient balance",
            exchange="binance",
            code="10001",
        )

        assert error.code == "10001"

    def test_create_with_response_data(self):
        """Test creating error with response data."""
        response = {"error": "Insufficient balance", "code": "10001"}
        error = ExchangeAPIError(
            "API error",
            exchange="okx",
            response_data=response,
        )

        assert error.response_data == response

    def test_inherits_from_exchange_error(self):
        """Test inherits from ExchangeError."""
        error = ExchangeAPIError("API error")

        assert isinstance(error, ExchangeError)

    def test_full_api_error(self):
        """Test creating full API error with all fields."""
        response = {"msg": "Invalid order", "code": "51008"}
        error = ExchangeAPIError(
            "Invalid order parameters",
            exchange="okx",
            code="51008",
            response_data=response,
        )

        assert error.message == "Invalid order parameters"
        assert error.exchange == "okx"
        assert error.code == "51008"
        assert error.response_data == response


class TestOrderNotFoundError:
    """Tests for OrderNotFoundError."""

    def test_create_order_not_found(self):
        """Test creating order not found error."""
        error = OrderNotFoundError("Order does not exist", exchange="okx")

        assert error.message == "Order does not exist"
        assert error.exchange == "okx"
        assert error.order_id is None

    def test_create_with_order_id(self):
        """Test creating error with order ID."""
        error = OrderNotFoundError(
            "Order not found",
            exchange="binance",
            order_id="12345",
        )

        assert error.order_id == "12345"

    def test_inherits_from_exchange_error(self):
        """Test inherits from ExchangeError."""
        error = OrderNotFoundError("Not found")

        assert isinstance(error, ExchangeError)

    def test_can_access_order_id(self):
        """Test can access order_id attribute."""
        with pytest.raises(OrderNotFoundError) as exc_info:
            raise OrderNotFoundError("Order missing", order_id="abc123")

        assert exc_info.value.order_id == "abc123"


class TestInvalidOrderError:
    """Tests for InvalidOrderError."""

    def test_create_invalid_order_error(self):
        """Test creating invalid order error."""
        error = InvalidOrderError("Invalid order parameters", exchange="okx")

        assert error.message == "Invalid order parameters"
        assert error.exchange == "okx"
        assert error.field is None

    def test_create_with_field(self):
        """Test creating error with field."""
        error = InvalidOrderError(
            "Amount too small",
            exchange="binance",
            field="amount",
        )

        assert error.field == "amount"

    def test_inherits_from_exchange_error(self):
        """Test inherits from ExchangeError."""
        error = InvalidOrderError("Invalid order")

        assert isinstance(error, ExchangeError)

    def test_can_access_field(self):
        """Test can access field attribute."""
        with pytest.raises(InvalidOrderError) as exc_info:
            raise InvalidOrderError("Invalid price", field="price")

        assert exc_info.value.field == "price"


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_all_errors_inherit_from_base(self):
        """Test all errors inherit from ExchangeError."""
        errors = [
            ExchangeConnectionError("test"),
            ExchangeAuthenticationError("test"),
            ExchangeRateLimitError("test"),
            ExchangeAPIError("test"),
            OrderNotFoundError("test"),
            InvalidOrderError("test"),
        ]

        for error in errors:
            assert isinstance(error, ExchangeError)
            assert isinstance(error, Exception)

    def test_catch_all_with_base_class(self):
        """Test catching all errors with base class."""
        exceptions_to_test = [
            ExchangeConnectionError,
            ExchangeAuthenticationError,
            ExchangeRateLimitError,
            ExchangeAPIError,
            OrderNotFoundError,
            InvalidOrderError,
        ]

        for exc_class in exceptions_to_test:
            try:
                raise exc_class("Test error")
            except ExchangeError as e:
                assert e.message == "Test error"

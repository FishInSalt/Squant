"""Unit tests for API utilities."""

import pytest
from fastapi import HTTPException

from squant.api.utils import ApiResponse, PaginatedData, handle_exchange_error, paginate_params
from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    InvalidOrderError,
    OrderNotFoundError,
)


class TestApiResponse:
    """Tests for ApiResponse model."""

    def test_default_values(self) -> None:
        """Test default values for ApiResponse."""
        response = ApiResponse(data={"test": "value"})

        assert response.code == 0
        assert response.message == "success"
        assert response.data == {"test": "value"}

    def test_custom_values(self) -> None:
        """Test custom values for ApiResponse."""
        response = ApiResponse(code=1, message="custom", data=[1, 2, 3])

        assert response.code == 1
        assert response.message == "custom"
        assert response.data == [1, 2, 3]

    def test_with_none_data(self) -> None:
        """Test ApiResponse with None data."""
        response = ApiResponse(data=None)

        assert response.code == 0
        assert response.message == "success"
        assert response.data is None


class TestPaginatedData:
    """Tests for PaginatedData model."""

    def test_creation(self) -> None:
        """Test PaginatedData creation."""
        items = [{"id": 1}, {"id": 2}]
        paginated = PaginatedData(items=items, total=100, page=1, page_size=20)

        assert paginated.items == items
        assert paginated.total == 100
        assert paginated.page == 1
        assert paginated.page_size == 20

    def test_empty_items(self) -> None:
        """Test PaginatedData with empty items."""
        paginated = PaginatedData(items=[], total=0, page=1, page_size=20)

        assert paginated.items == []
        assert paginated.total == 0

    def test_last_page(self) -> None:
        """Test PaginatedData for last page."""
        items = [{"id": 91}]
        paginated = PaginatedData(items=items, total=91, page=5, page_size=20)

        assert len(paginated.items) == 1
        assert paginated.total == 91
        assert paginated.page == 5


class TestHandleExchangeError:
    """Tests for handle_exchange_error function."""

    def test_authentication_error(self) -> None:
        """Test handling of ExchangeAuthenticationError."""
        error = ExchangeAuthenticationError("Invalid API key")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid API key"

    def test_rate_limit_error(self) -> None:
        """Test handling of ExchangeRateLimitError."""
        error = ExchangeRateLimitError("Rate limit exceeded", retry_after=60)

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limit exceeded"
        assert exc_info.value.headers == {"Retry-After": "60"}

    def test_rate_limit_error_no_retry_after(self) -> None:
        """Test handling of ExchangeRateLimitError without retry_after."""
        error = ExchangeRateLimitError("Rate limit exceeded")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers == {"Retry-After": "1"}

    def test_order_not_found_error(self) -> None:
        """Test handling of OrderNotFoundError."""
        error = OrderNotFoundError("Order not found: 12345")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Order not found: 12345"

    def test_invalid_order_error(self) -> None:
        """Test handling of InvalidOrderError."""
        error = InvalidOrderError("Invalid order amount")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid order amount"

    def test_connection_error(self) -> None:
        """Test handling of ExchangeConnectionError."""
        error = ExchangeConnectionError("Connection timeout")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Connection timeout"

    def test_api_error(self) -> None:
        """Test handling of ExchangeAPIError."""
        error = ExchangeAPIError("API error occurred")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "API error occurred"

    def test_unknown_error(self) -> None:
        """Test handling of unknown exception."""
        error = ValueError("Unknown error")

        with pytest.raises(HTTPException) as exc_info:
            handle_exchange_error(error)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal server error"


class TestPaginateParams:
    """Tests for paginate_params function."""

    def test_first_page(self) -> None:
        """Test pagination for first page."""
        offset, limit = paginate_params(page=1, page_size=20)

        assert offset == 0
        assert limit == 20

    def test_second_page(self) -> None:
        """Test pagination for second page."""
        offset, limit = paginate_params(page=2, page_size=20)

        assert offset == 20
        assert limit == 20

    def test_custom_page_size(self) -> None:
        """Test pagination with custom page size."""
        offset, limit = paginate_params(page=3, page_size=50)

        assert offset == 100
        assert limit == 50

    def test_large_page_number(self) -> None:
        """Test pagination with large page number."""
        offset, limit = paginate_params(page=100, page_size=10)

        assert offset == 990
        assert limit == 10

    def test_page_size_one(self) -> None:
        """Test pagination with page size of 1."""
        offset, limit = paginate_params(page=5, page_size=1)

        assert offset == 4
        assert limit == 1

"""Binance HTTP client with authentication, signing, and rate limiting."""

import asyncio
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
    OrderNotFoundError,
)


class BinanceClient:
    """HTTP client for Binance exchange API.

    Handles authentication (HMAC-SHA256 signing), testnet support,
    and simple token bucket rate limiting.
    """

    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"

    # Rate limit: default 100ms between requests
    DEFAULT_RATE_LIMIT_INTERVAL = 0.1

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        rate_limit_interval: float = DEFAULT_RATE_LIMIT_INTERVAL,
    ) -> None:
        """Initialize Binance client.

        Args:
            api_key: Binance API key.
            api_secret: Binance API secret.
            testnet: Whether to use testnet (spot testnet).
            rate_limit_interval: Minimum seconds between requests.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.rate_limit_interval = rate_limit_interval

        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Get base URL based on testnet setting."""
        return self.TESTNET_URL if self.testnet else self.BASE_URL

    async def connect(self) -> None:
        """Initialize HTTP client."""
        if self._client is not None:
            return

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
                "X-MBX-APIKEY": self.api_key,
            },
        )

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC-SHA256 signature for request.

        Args:
            query_string: Query string to sign.

        Returns:
            Hex-encoded signature.
        """
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting by waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.rate_limit_interval:
                await asyncio.sleep(self.rate_limit_interval - elapsed)
            self._last_request_time = time.monotonic()

    def _parse_response(self, response: httpx.Response) -> dict[str, Any] | list[Any]:
        """Parse and validate API response.

        Args:
            response: HTTP response object.

        Returns:
            Parsed response data (dict for most endpoints, list for tickers/klines).

        Raises:
            ExchangeRateLimitError: If rate limited.
            ExchangeAuthenticationError: If authentication failed.
            ExchangeAPIError: If API returned an error.
        """
        # Check HTTP status first
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise ExchangeRateLimitError(
                message="Rate limit exceeded",
                exchange="binance",
                retry_after=float(retry_after),
            )

        if response.status_code == 418:
            raise ExchangeRateLimitError(
                message="IP banned due to rate limit violations",
                exchange="binance",
                retry_after=300.0,
            )

        try:
            parsed = response.json()
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to parse response: {e}",
                exchange="binance",
                response_data={"text": response.text[:500]},
            ) from e

        # Binance returns arrays for some endpoints (e.g., tickers, klines)
        if isinstance(parsed, list):
            return parsed

        data: dict[str, Any] = parsed

        # Binance error format: {"code": -1000, "msg": "..."}
        if "code" in data and data["code"] != 200:
            code = data.get("code", 0)
            msg = data.get("msg", "Unknown error")

            # Authentication errors
            if code in (-2014, -2015, -1022):
                raise ExchangeAuthenticationError(
                    message=f"Authentication failed: {msg}",
                    exchange="binance",
                )

            # Order not found
            if code == -2013:
                raise OrderNotFoundError(
                    message=msg,
                    exchange="binance",
                )

            # Rate limit (code -1015)
            if code == -1015:
                raise ExchangeRateLimitError(
                    message=msg,
                    exchange="binance",
                    retry_after=60.0,
                )

            raise ExchangeAPIError(
                message=msg,
                exchange="binance",
                code=str(code),
                response_data=data,
            )

        return data

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make an API request.

        Args:
            method: HTTP method (GET, POST, DELETE).
            path: API endpoint path (e.g., '/api/v3/account').
            params: Query parameters.
            body: JSON body for POST requests.
            authenticated: Whether to include authentication.

        Returns:
            Parsed response data (dict for most endpoints, list for tickers/klines).

        Raises:
            ExchangeConnectionError: If connection fails.
            ExchangeAuthenticationError: If authentication fails.
            ExchangeRateLimitError: If rate limited.
            ExchangeAPIError: If API returns an error.
        """
        if self._client is None:
            raise ExchangeConnectionError(
                message="Client not connected. Call connect() first.",
                exchange="binance",
            )

        # Apply rate limiting
        await self._apply_rate_limit()

        # Build query parameters
        query_params = dict(params) if params else {}

        if authenticated:
            # Add timestamp
            query_params["timestamp"] = self._get_timestamp()

            # Build query string and sign it
            query_string = urlencode(query_params)
            signature = self._generate_signature(query_string)
            query_params["signature"] = signature

        try:
            if method.upper() == "GET":
                response = await self._client.get(path, params=query_params)
            elif method.upper() == "POST":
                # For POST, params go in query string, body in request body
                response = await self._client.post(
                    path,
                    params=query_params,
                    json=body,
                )
            elif method.upper() == "DELETE":
                response = await self._client.delete(path, params=query_params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except httpx.ConnectError as e:
            raise ExchangeConnectionError(
                message=f"Connection failed: {e}",
                exchange="binance",
            ) from e
        except httpx.TimeoutException as e:
            raise ExchangeConnectionError(
                message=f"Request timeout: {e}",
                exchange="binance",
            ) from e

        return self._parse_response(response)

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request.

        Args:
            path: API endpoint path.
            params: Query parameters.
            authenticated: Whether to include authentication.

        Returns:
            Parsed response data (dict for most endpoints, list for tickers/klines).
        """
        return await self.request("GET", path, params=params, authenticated=authenticated)

    async def post(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a POST request.

        Args:
            path: API endpoint path.
            params: Query parameters.
            body: JSON body.
            authenticated: Whether to include authentication.

        Returns:
            Parsed response data (dict for most endpoints, list for batch operations).
        """
        return await self.request("POST", path, params=params, body=body, authenticated=authenticated)

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a DELETE request.

        Args:
            path: API endpoint path.
            params: Query parameters.
            authenticated: Whether to include authentication.

        Returns:
            Parsed response data (dict for most endpoints).
        """
        return await self.request("DELETE", path, params=params, authenticated=authenticated)

"""OKX HTTP client with authentication, signing, and rate limiting."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from squant.infra.exchange.exceptions import (
    ExchangeAPIError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRateLimitError,
)
from squant.infra.exchange.retry import RetryConfig, with_retry


class OKXClient:
    """HTTP client for OKX exchange API.

    Handles authentication (HMAC-SHA256 signing), testnet support,
    and simple token bucket rate limiting.
    """

    BASE_URL = "https://www.okx.com"
    TESTNET_URL = "https://www.okx.com"  # OKX uses same URL with header for testnet

    # Rate limit: default 100ms between requests
    DEFAULT_RATE_LIMIT_INTERVAL = 0.1

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        testnet: bool = False,
        rate_limit_interval: float = DEFAULT_RATE_LIMIT_INTERVAL,
        retry_config: RetryConfig | None = None,
    ) -> None:
        """Initialize OKX client.

        Args:
            api_key: OKX API key.
            api_secret: OKX API secret.
            passphrase: OKX API passphrase.
            testnet: Whether to use testnet (simulated trading).
            rate_limit_interval: Minimum seconds between requests.
            retry_config: Configuration for automatic retry on transient errors.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet
        self.rate_limit_interval = rate_limit_interval
        self.retry_config = retry_config or RetryConfig()

        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Get base URL (same for testnet, differentiated by header)."""
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
            },
        )

    async def close(self) -> None:
        """Close HTTP client and cleanup resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _generate_signature(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = "",
    ) -> str:
        """Generate HMAC-SHA256 signature for request.

        Args:
            timestamp: ISO 8601 timestamp.
            method: HTTP method (GET, POST, etc.).
            request_path: Request path including query string.
            body: Request body for POST requests.

        Returns:
            Base64-encoded signature.
        """
        # Signature = Base64(HMAC-SHA256(timestamp + method + requestPath + body))
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _get_timestamp(self) -> str:
        """Get ISO 8601 timestamp for request signing."""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _build_auth_headers(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = "",
    ) -> dict[str, str]:
        """Build authentication headers.

        Args:
            timestamp: ISO 8601 timestamp.
            method: HTTP method.
            request_path: Request path including query string.
            body: Request body for POST requests.

        Returns:
            Dict of authentication headers.
        """
        signature = self._generate_signature(timestamp, method, request_path, body)

        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        }

        # Add testnet header for simulated trading
        if self.testnet:
            headers["x-simulated-trading"] = "1"

        return headers

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting by waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.rate_limit_interval:
                await asyncio.sleep(self.rate_limit_interval - elapsed)
            self._last_request_time = time.monotonic()

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse and validate API response.

        Args:
            response: HTTP response object.

        Returns:
            Parsed response data.

        Raises:
            ExchangeRateLimitError: If rate limited.
            ExchangeAuthenticationError: If authentication failed.
            ExchangeAPIError: If API returned an error.
        """
        try:
            data = response.json()
        except Exception as e:
            raise ExchangeAPIError(
                message=f"Failed to parse response: {e}",
                exchange="okx",
                response_data={"text": response.text[:500]},
            ) from e

        # OKX response format: {"code": "0", "msg": "", "data": [...]}
        code = data.get("code", "")
        msg = data.get("msg", "")

        # Success
        if code == "0":
            return data

        # For order operations, OKX returns code "1" (partial) or "2" (all failed)
        # with error details in data[0].sCode/sMsg - let adapter handle these
        if code in ("1", "2") and data.get("data"):
            return data

        # Rate limit error
        if code == "50011":
            raise ExchangeRateLimitError(
                message=f"Rate limit exceeded: {msg}",
                exchange="okx",
                retry_after=1.0,
            )

        # Authentication errors
        if code in ("50100", "50101", "50102", "50103", "50104", "50105"):
            raise ExchangeAuthenticationError(
                message=f"Authentication failed: {msg}",
                exchange="okx",
            )

        # Order not found errors
        if code in ("51603",) or "does not exist" in msg.lower():
            from squant.infra.exchange.exceptions import OrderNotFoundError

            raise OrderNotFoundError(
                message=msg or "Order not found",
                exchange="okx",
            )

        # General API error
        raise ExchangeAPIError(
            message=msg or f"API error: {code}",
            exchange="okx",
            code=code,
            response_data=data,
        )

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """Make an API request with automatic retry on transient errors.

        Args:
            method: HTTP method (GET, POST).
            path: API endpoint path (e.g., '/api/v5/account/balance').
            params: Query parameters for GET requests.
            body: JSON body for POST requests.
            authenticated: Whether to include authentication headers.

        Returns:
            Parsed response data.

        Raises:
            ExchangeConnectionError: If connection fails after retries.
            ExchangeAuthenticationError: If authentication fails (not retried).
            ExchangeRateLimitError: If rate limited after retries.
            ExchangeAPIError: If API returns an error.
        """
        return await with_retry(
            self._execute_request,
            method,
            path,
            params,
            body,
            authenticated,
            config=self.retry_config,
            operation_name=f"OKX {method} {path}",
        )

    async def _execute_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """Execute a single API request (called by retry logic).

        Args:
            method: HTTP method (GET, POST).
            path: API endpoint path.
            params: Query parameters for GET requests.
            body: JSON body for POST requests.
            authenticated: Whether to include authentication headers.

        Returns:
            Parsed response data.
        """
        if self._client is None:
            raise ExchangeConnectionError(
                message="Client not connected. Call connect() first.",
                exchange="okx",
            )

        # Apply rate limiting
        await self._apply_rate_limit()

        # Build request path with query string for signature
        # Important: query string order must match exactly between signature and request
        request_path = path
        query_string = ""
        if params:
            # Filter out None values and sort for consistent ordering
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                query_string = "&".join(f"{k}={v}" for k, v in sorted(filtered_params.items()))
                request_path = f"{path}?{query_string}"

        # Prepare body
        body_str = ""
        if body:
            body_str = json.dumps(body)

        # Build headers
        headers = {}
        if authenticated:
            timestamp = self._get_timestamp()
            headers = self._build_auth_headers(timestamp, method, request_path, body_str)

        try:
            if method.upper() == "GET":
                # Use the exact same path with query string that we signed
                response = await self._client.get(request_path, headers=headers)
            elif method.upper() == "POST":
                # Use content=body_str to ensure exact JSON matches what we signed
                response = await self._client.post(path, content=body_str, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except httpx.ConnectError as e:
            raise ExchangeConnectionError(
                message=f"Connection failed: {e}",
                exchange="okx",
            ) from e
        except httpx.TimeoutException as e:
            raise ExchangeConnectionError(
                message=f"Request timeout: {e}",
                exchange="okx",
            ) from e

        return self._parse_response(response)

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """Make a GET request.

        Args:
            path: API endpoint path.
            params: Query parameters.
            authenticated: Whether to include authentication headers.

        Returns:
            Parsed response data.
        """
        return await self.request("GET", path, params=params, authenticated=authenticated)

    async def post(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            path: API endpoint path.
            body: JSON body.
            authenticated: Whether to include authentication headers.

        Returns:
            Parsed response data.
        """
        return await self.request("POST", path, body=body, authenticated=authenticated)

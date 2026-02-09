"""Type definitions for CCXT integration."""

from dataclasses import dataclass


@dataclass
class ExchangeCredentials:
    """Exchange API credentials.

    Attributes:
        api_key: API key for the exchange.
        api_secret: API secret for the exchange.
        passphrase: API passphrase (required for OKX).
        sandbox: Whether to use sandbox/testnet mode.
    """

    api_key: str
    api_secret: str
    passphrase: str | None = None
    sandbox: bool = False


# Mapping of standard timeframes to CCXT timeframes
TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
}

# Supported exchanges
SUPPORTED_EXCHANGES = frozenset({"okx", "binance", "bybit"})

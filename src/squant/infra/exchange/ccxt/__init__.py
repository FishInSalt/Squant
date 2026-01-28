"""CCXT integration for multi-exchange support.

This package provides a unified interface for real-time data streaming
from multiple cryptocurrency exchanges using the CCXT library.

Supported exchanges:
- OKX
- Binance
- Bybit

Example:
    from squant.infra.exchange.ccxt import CCXTStreamProvider, ExchangeCredentials

    credentials = ExchangeCredentials(
        api_key="your-api-key",
        api_secret="your-api-secret",
        passphrase="your-passphrase",  # OKX only
    )

    provider = CCXTStreamProvider("okx", credentials)
    await provider.connect()
    await provider.watch_ticker("BTC/USDT")
"""

from squant.infra.exchange.ccxt.provider import CCXTStreamProvider
from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.ccxt.transformer import CCXTDataTransformer
from squant.infra.exchange.ccxt.types import (
    SUPPORTED_EXCHANGES,
    TIMEFRAME_MAP,
    ExchangeCredentials,
)

__all__ = [
    "CCXTStreamProvider",
    "CCXTRestAdapter",
    "CCXTDataTransformer",
    "ExchangeCredentials",
    "SUPPORTED_EXCHANGES",
    "TIMEFRAME_MAP",
]

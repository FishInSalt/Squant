"""Shared credential-building utilities for exchange adapters."""

from squant.infra.exchange.ccxt import ExchangeCredentials


def build_exchange_credentials(exchange_id: str, settings) -> ExchangeCredentials | None:
    """Build ExchangeCredentials from global settings for the given exchange.

    Args:
        exchange_id: Exchange identifier (okx, binance, bybit).
        settings: Application settings object (from get_settings()).

    Returns:
        ExchangeCredentials or None if credentials are not configured.
    """
    # TODO: sandbox flag should come from the trading session's exchange account,
    # not from global config. Defaulting to False (production) for now.
    if exchange_id == "okx":
        if settings.okx_api_key and settings.okx_api_secret:
            return ExchangeCredentials(
                api_key=settings.okx_api_key.get_secret_value(),
                api_secret=settings.okx_api_secret.get_secret_value(),
                passphrase=settings.okx_passphrase.get_secret_value()
                if settings.okx_passphrase
                else None,
                sandbox=False,
            )
    elif exchange_id == "binance":
        if settings.binance_api_key and settings.binance_api_secret:
            return ExchangeCredentials(
                api_key=settings.binance_api_key.get_secret_value(),
                api_secret=settings.binance_api_secret.get_secret_value(),
                sandbox=False,
            )
    elif exchange_id == "bybit" and settings.bybit_api_key and settings.bybit_api_secret:
        return ExchangeCredentials(
            api_key=settings.bybit_api_key.get_secret_value(),
            api_secret=settings.bybit_api_secret.get_secret_value(),
            sandbox=False,
        )
    return None

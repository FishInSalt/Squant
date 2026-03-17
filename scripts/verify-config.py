"""Verify environment configuration for live trading E2E.

Checks all required settings are present and valid before running
live trading verification tests. Exits with code 1 if any check fails.

Usage:
    uv run python scripts/verify-config.py
"""

import sys

from pydantic import SecretStr


def secret_str_value(s: SecretStr | None) -> str | None:
    """Safely extract the value from a SecretStr | None field."""
    if s is None:
        return None
    return s.get_secret_value()


def mask(value: str | None) -> str:
    """Mask a secret value for display, showing only first/last 2 chars."""
    if not value:
        return "(empty)"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    # -------------------------------------------------------------------------
    # Load settings — catch startup failures early
    # -------------------------------------------------------------------------
    try:
        from squant.config import get_settings

        get_settings.cache_clear()
        settings = get_settings()
    except Exception as e:
        print(f"FAIL: Cannot load settings: {e}")
        print("\nEnsure .env file exists and required variables are set.")
        return 1

    # -------------------------------------------------------------------------
    # 1. DEFAULT_EXCHANGE
    # -------------------------------------------------------------------------
    exchange_name = settings.exchange.default_exchange
    is_okx = exchange_name == "okx"
    results.append(
        (
            "DEFAULT_EXCHANGE is set",
            bool(exchange_name),
            f"value={exchange_name!r}" + ("" if is_okx else " (WARNING: expected 'okx')"),
        )
    )

    # -------------------------------------------------------------------------
    # 2. OKX API credentials
    # -------------------------------------------------------------------------
    okx_key = secret_str_value(settings.okx.api_key)
    okx_secret = secret_str_value(settings.okx.api_secret)
    okx_pass = secret_str_value(settings.okx.passphrase)

    results.append(
        (
            "OKX_API_KEY is set",
            bool(okx_key),
            mask(okx_key),
        )
    )
    results.append(
        (
            "OKX_API_SECRET is set",
            bool(okx_secret),
            mask(okx_secret),
        )
    )
    results.append(
        (
            "OKX_PASSPHRASE is set",
            bool(okx_pass),
            mask(okx_pass),
        )
    )

    # Testnet mode (informational, not a pass/fail)
    results.append(
        (
            "OKX_TESTNET mode",
            True,  # always passes — informational
            f"testnet={'enabled' if settings.okx.testnet else 'disabled'}",
        )
    )

    # -------------------------------------------------------------------------
    # 3. SECRET_KEY (min 32 chars)
    # -------------------------------------------------------------------------
    secret_key_val = secret_str_value(settings.security.secret_key)
    sk_len = len(secret_key_val) if secret_key_val else 0
    results.append(
        (
            "SECRET_KEY is set (min 32 chars)",
            bool(secret_key_val) and sk_len >= 32,
            f"length={sk_len}" if secret_key_val else "(not set)",
        )
    )

    # -------------------------------------------------------------------------
    # 4. ENCRYPTION_KEY
    # -------------------------------------------------------------------------
    enc_key_val = secret_str_value(settings.security.encryption_key)
    results.append(
        (
            "ENCRYPTION_KEY is set",
            bool(enc_key_val),
            mask(enc_key_val),
        )
    )

    # -------------------------------------------------------------------------
    # 5. LIVE_AUTO_RECOVERY
    # -------------------------------------------------------------------------
    live_auto_recovery = settings.live.auto_recovery
    results.append(
        (
            "LIVE_AUTO_RECOVERY is True",
            live_auto_recovery is True,
            f"value={live_auto_recovery}",
        )
    )

    # -------------------------------------------------------------------------
    # 6. DATABASE_URL
    # -------------------------------------------------------------------------
    db_url_val = secret_str_value(settings.database.url)
    results.append(
        (
            "DATABASE_URL is set",
            bool(db_url_val),
            mask(db_url_val) if db_url_val else "(not set)",
        )
    )

    # -------------------------------------------------------------------------
    # 7. REDIS_URL
    # -------------------------------------------------------------------------
    redis_url_val = secret_str_value(settings.redis.url)
    results.append(
        (
            "REDIS_URL is set",
            bool(redis_url_val),
            mask(redis_url_val) if redis_url_val else "(not set)",
        )
    )

    # -------------------------------------------------------------------------
    # Print results
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("  Live Trading Configuration Verification")
    print("=" * 70)
    print()

    failed = 0
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"  [{status}] {name}")
        if detail:
            print(f"         {detail}")

    print()
    print("-" * 70)

    if failed:
        print(f"  {failed} check(s) FAILED. Fix the issues above before proceeding.")
        print("  Ensure .env has all required variables for live trading.")
    else:
        print("  All checks passed. Configuration is ready for live trading E2E.")

    print("-" * 70)
    print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

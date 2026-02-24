"""Application configuration using Pydantic Settings.

Configuration is organized into nested groups for better maintainability.
All settings are loaded from environment variables (via .env file).
"""

from functools import cached_property, lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# =============================================================================
# Nested Configuration Classes
# =============================================================================


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DATABASE_",
        extra="ignore",
    )

    url: SecretStr = Field(description="PostgreSQL connection string (must use asyncpg driver)")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        if not url.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        if "asyncpg" not in url:
            raise ValueError("DATABASE_URL must use asyncpg driver (postgresql+asyncpg://...)")
        return v


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REDIS_",
        extra="ignore",
    )

    url: SecretStr = Field(description="Redis connection string")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        if not url.startswith("redis://"):
            raise ValueError("REDIS_URL must start with redis://")
        return v


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LOG_",
        extra="ignore",
    )

    level: str = Field(
        default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )
    format: str = Field(default="text", description="Log format: json or text")
    file: str | None = Field(default=None, description="Log file path (optional)")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        valid_formats = ["json", "text"]
        if v.lower() not in valid_formats:
            raise ValueError(f"LOG_FORMAT must be one of {valid_formats}")
        return v.lower()


class SecuritySettings(BaseSettings):
    """Security and authentication settings.

    Note: Uses empty env_prefix for backward compatibility with existing
    environment variables (SECRET_KEY, ENCRYPTION_KEY, etc.).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",  # Empty for backward compatibility
        extra="ignore",
    )

    secret_key: SecretStr = Field(description="Application secret key (min 32 chars)")
    encryption_key: SecretStr = Field(description="Key for encrypting stored API keys")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=30, ge=1, description="JWT token expiry in minutes"
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v


class OKXSettings(BaseSettings):
    """OKX exchange API settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OKX_",
        extra="ignore",
    )

    api_key: SecretStr | None = Field(default=None, description="OKX API key")
    api_secret: SecretStr | None = Field(default=None, description="OKX API secret")
    passphrase: SecretStr | None = Field(default=None, description="OKX API passphrase")
    testnet: bool = Field(default=False, description="Use OKX testnet/sandbox")


class BinanceSettings(BaseSettings):
    """Binance exchange API settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BINANCE_",
        extra="ignore",
    )

    api_key: SecretStr | None = Field(default=None, description="Binance API key")
    api_secret: SecretStr | None = Field(default=None, description="Binance API secret")
    testnet: bool = Field(default=False, description="Use Binance testnet")


class BybitSettings(BaseSettings):
    """Bybit exchange API settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BYBIT_",
        extra="ignore",
    )

    api_key: SecretStr | None = Field(default=None, description="Bybit API key")
    api_secret: SecretStr | None = Field(default=None, description="Bybit API secret")
    testnet: bool = Field(default=False, description="Use Bybit testnet")


class ExchangeStreamSettings(BaseSettings):
    """Exchange streaming configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )

    default_exchange: str = Field(
        default="okx", description="Default exchange: okx, binance, bybit"
    )
    use_ccxt_provider: bool = Field(
        default=True, description="Use CCXT for WebSocket (False = native OKX)"
    )

    @field_validator("default_exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        valid_exchanges = ["okx", "binance", "bybit"]
        if v.lower() not in valid_exchanges:
            raise ValueError(f"DEFAULT_EXCHANGE must be one of {valid_exchanges}")
        return v.lower()


class StrategySettings(BaseSettings):
    """Strategy engine settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STRATEGY_",
        extra="ignore",
    )

    max_processes: int = Field(
        default=5, ge=1, le=20, description="Max concurrent strategy processes"
    )
    memory_limit_mb: int = Field(default=2048, ge=64, description="Memory limit per strategy (MB)")
    cpu_limit_seconds: int = Field(
        default=60, ge=1, description="CPU time limit per execution (seconds)"
    )
    sandbox_enabled: bool = Field(default=True, description="Enable RestrictedPython sandbox")


class RiskSettings(BaseSettings):
    """Risk control settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RISK_",
        extra="ignore",
    )

    max_position_ratio: float = Field(
        default=0.3, ge=0.01, le=1.0, description="Max position as ratio of portfolio"
    )
    max_daily_loss_ratio: float = Field(
        default=0.05, ge=0.01, le=0.5, description="Max daily loss as ratio of portfolio"
    )
    max_orders_per_minute: int = Field(
        default=10, ge=1, description="Rate limit: orders per minute"
    )


class PaperTradingSettings(BaseSettings):
    """Paper trading engine settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PAPER_",
        extra="ignore",
    )

    max_equity_curve_size: int = Field(
        default=10000, ge=100, description="Max equity curve data points"
    )
    max_completed_orders: int = Field(
        default=1000, ge=100, description="Max completed orders to keep"
    )
    max_fills: int = Field(default=5000, ge=100, description="Max order fills to keep")
    max_trades: int = Field(default=1000, ge=100, description="Max trades to keep")
    max_logs: int = Field(default=1000, ge=100, description="Max strategy logs to keep")
    health_check_interval_seconds: int = Field(
        default=60, ge=10, description="Health check interval (seconds)"
    )
    session_timeout_seconds: int = Field(
        default=300, ge=60, description="Session timeout for stale detection"
    )
    persist_interval_seconds: int = Field(
        default=60, ge=10, description="Auto-persist interval (seconds)"
    )
    max_sessions: int = Field(
        default=20, ge=1, le=100, description="Max concurrent paper trading sessions"
    )
    warmup_bars: int = Field(
        default=200, ge=0, le=5000, description="Bars to replay for strategy warmup on resume"
    )
    auto_recovery: bool = Field(
        default=True, description="Auto-recover orphaned sessions on startup"
    )


class CircuitBreakerSettings(BaseSettings):
    """Circuit breaker settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CIRCUIT_BREAKER_",
        extra="ignore",
    )

    cooldown_minutes: int = Field(
        default=60, ge=1, description="Cooldown period after trigger (minutes)"
    )
    auto_enabled: bool = Field(
        default=False, description="Enable automatic circuit breaker triggers"
    )


# =============================================================================
# Main Settings Class
# =============================================================================


class Settings(BaseSettings):
    """Main application settings.

    Configuration is loaded from environment variables and .env file.
    Nested settings are organized by domain for better maintainability.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application Settings
    # -------------------------------------------------------------------------
    app_name: str = Field(default="Squant", description="Application name")
    app_env: str = Field(
        default="production", description="Environment: development, test, staging, production"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    api_prefix: str = Field(default="/api/v1", description="API route prefix")
    allowed_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:5175", "http://localhost:3000"],
        description="CORS allowed origins",
    )

    # Rate limiting configuration (applied at API layer)
    rate_limit_enabled: bool = Field(default=False, description="Enable API rate limiting")
    rate_limit_per_minute: int = Field(
        default=60, ge=1, description="Max requests per minute per client"
    )
    rate_limit_burst: int = Field(default=10, ge=1, description="Max burst requests allowed")

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        valid_envs = ["development", "test", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"APP_ENV must be one of {valid_envs}")
        return v.lower()

    # -------------------------------------------------------------------------
    # Nested Settings (loaded with their own env_prefix)
    # Using cached_property to avoid re-reading .env and re-validating on each access
    # -------------------------------------------------------------------------

    @cached_property
    def database(self) -> DatabaseSettings:
        """Database settings."""
        return DatabaseSettings()

    @cached_property
    def redis(self) -> RedisSettings:
        """Redis settings."""
        return RedisSettings()

    @cached_property
    def logging(self) -> LoggingSettings:
        """Logging settings."""
        return LoggingSettings()

    @cached_property
    def security(self) -> SecuritySettings:
        """Security settings."""
        return SecuritySettings()

    @cached_property
    def okx(self) -> OKXSettings:
        """OKX exchange settings."""
        return OKXSettings()

    @cached_property
    def binance(self) -> BinanceSettings:
        """Binance exchange settings."""
        return BinanceSettings()

    @cached_property
    def bybit(self) -> BybitSettings:
        """Bybit exchange settings."""
        return BybitSettings()

    @cached_property
    def exchange(self) -> ExchangeStreamSettings:
        """Exchange streaming settings."""
        return ExchangeStreamSettings()

    @cached_property
    def strategy(self) -> StrategySettings:
        """Strategy engine settings."""
        return StrategySettings()

    @cached_property
    def risk(self) -> RiskSettings:
        """Risk control settings."""
        return RiskSettings()

    @cached_property
    def paper(self) -> PaperTradingSettings:
        """Paper trading settings."""
        return PaperTradingSettings()

    @cached_property
    def circuit_breaker(self) -> CircuitBreakerSettings:
        """Circuit breaker settings."""
        return CircuitBreakerSettings()

    # -------------------------------------------------------------------------
    # Backward Compatibility Aliases
    # -------------------------------------------------------------------------
    # These properties maintain compatibility with existing code that uses
    # flat attribute access (e.g., settings.log_level instead of settings.logging.level)

    @property
    def log_level(self) -> str:
        """Alias for logging.level (backward compatibility)."""
        return self.logging.level

    @property
    def log_format(self) -> str:
        """Alias for logging.format (backward compatibility)."""
        return self.logging.format

    @property
    def log_file(self) -> str | None:
        """Alias for logging.file (backward compatibility)."""
        return self.logging.file

    @property
    def database_url(self) -> SecretStr:
        """Alias for database.url (backward compatibility)."""
        return self.database.url

    @property
    def redis_url(self) -> SecretStr:
        """Alias for redis.url (backward compatibility)."""
        return self.redis.url

    @property
    def secret_key(self) -> SecretStr:
        """Alias for security.secret_key (backward compatibility)."""
        return self.security.secret_key

    @property
    def encryption_key(self) -> SecretStr:
        """Alias for security.encryption_key (backward compatibility)."""
        return self.security.encryption_key

    @property
    def jwt_algorithm(self) -> str:
        """Alias for security.jwt_algorithm (backward compatibility)."""
        return self.security.jwt_algorithm

    @property
    def jwt_access_token_expire_minutes(self) -> int:
        """Alias for security.jwt_access_token_expire_minutes (backward compatibility)."""
        return self.security.jwt_access_token_expire_minutes

    @property
    def default_exchange(self) -> str:
        """Alias for exchange.default_exchange (backward compatibility)."""
        return self.exchange.default_exchange

    @property
    def use_ccxt_provider(self) -> bool:
        """Alias for exchange.use_ccxt_provider (backward compatibility)."""
        return self.exchange.use_ccxt_provider

    # OKX aliases
    @property
    def okx_api_key(self) -> SecretStr | None:
        """Alias for okx.api_key (backward compatibility)."""
        return self.okx.api_key

    @property
    def okx_api_secret(self) -> SecretStr | None:
        """Alias for okx.api_secret (backward compatibility)."""
        return self.okx.api_secret

    @property
    def okx_passphrase(self) -> SecretStr | None:
        """Alias for okx.passphrase (backward compatibility)."""
        return self.okx.passphrase

    @property
    def okx_testnet(self) -> bool:
        """Alias for okx.testnet (backward compatibility)."""
        return self.okx.testnet

    # Binance aliases
    @property
    def binance_api_key(self) -> SecretStr | None:
        """Alias for binance.api_key (backward compatibility)."""
        return self.binance.api_key

    @property
    def binance_api_secret(self) -> SecretStr | None:
        """Alias for binance.api_secret (backward compatibility)."""
        return self.binance.api_secret

    @property
    def binance_testnet(self) -> bool:
        """Alias for binance.testnet (backward compatibility)."""
        return self.binance.testnet

    # Bybit aliases
    @property
    def bybit_api_key(self) -> SecretStr | None:
        """Alias for bybit.api_key (backward compatibility)."""
        return self.bybit.api_key

    @property
    def bybit_api_secret(self) -> SecretStr | None:
        """Alias for bybit.api_secret (backward compatibility)."""
        return self.bybit.api_secret

    @property
    def bybit_testnet(self) -> bool:
        """Alias for bybit.testnet (backward compatibility)."""
        return self.bybit.testnet

    # Strategy aliases
    @property
    def strategy_max_processes(self) -> int:
        """Alias for strategy.max_processes (backward compatibility)."""
        return self.strategy.max_processes

    @property
    def strategy_memory_limit_mb(self) -> int:
        """Alias for strategy.memory_limit_mb (backward compatibility)."""
        return self.strategy.memory_limit_mb

    @property
    def strategy_cpu_limit_seconds(self) -> int:
        """Alias for strategy.cpu_limit_seconds (backward compatibility)."""
        return self.strategy.cpu_limit_seconds

    @property
    def strategy_sandbox_enabled(self) -> bool:
        """Alias for strategy.sandbox_enabled (backward compatibility)."""
        return self.strategy.sandbox_enabled

    # Risk aliases
    @property
    def risk_max_position_ratio(self) -> float:
        """Alias for risk.max_position_ratio (backward compatibility)."""
        return self.risk.max_position_ratio

    @property
    def risk_max_daily_loss_ratio(self) -> float:
        """Alias for risk.max_daily_loss_ratio (backward compatibility)."""
        return self.risk.max_daily_loss_ratio

    @property
    def risk_max_orders_per_minute(self) -> int:
        """Alias for risk.max_orders_per_minute (backward compatibility)."""
        return self.risk.max_orders_per_minute

    # Paper trading aliases
    @property
    def paper_max_equity_curve_size(self) -> int:
        """Alias for paper.max_equity_curve_size (backward compatibility)."""
        return self.paper.max_equity_curve_size

    @property
    def paper_max_completed_orders(self) -> int:
        """Alias for paper.max_completed_orders (backward compatibility)."""
        return self.paper.max_completed_orders

    @property
    def paper_max_fills(self) -> int:
        """Alias for paper.max_fills (backward compatibility)."""
        return self.paper.max_fills

    @property
    def paper_max_trades(self) -> int:
        """Alias for paper.max_trades (backward compatibility)."""
        return self.paper.max_trades

    @property
    def paper_max_logs(self) -> int:
        """Alias for paper.max_logs (backward compatibility)."""
        return self.paper.max_logs

    @property
    def paper_health_check_interval_seconds(self) -> int:
        """Alias for paper.health_check_interval_seconds (backward compatibility)."""
        return self.paper.health_check_interval_seconds

    @property
    def paper_session_timeout_seconds(self) -> int:
        """Alias for paper.session_timeout_seconds (backward compatibility)."""
        return self.paper.session_timeout_seconds

    @property
    def paper_persist_interval_seconds(self) -> int:
        """Alias for paper.persist_interval_seconds (backward compatibility)."""
        return self.paper.persist_interval_seconds

    @property
    def paper_max_sessions(self) -> int:
        """Alias for paper.max_sessions (backward compatibility)."""
        return self.paper.max_sessions

    # Circuit breaker aliases
    @property
    def circuit_breaker_cooldown_minutes(self) -> int:
        """Alias for circuit_breaker.cooldown_minutes (backward compatibility)."""
        return self.circuit_breaker.cooldown_minutes

    @property
    def circuit_breaker_auto_enabled(self) -> bool:
        """Alias for circuit_breaker.auto_enabled (backward compatibility)."""
        return self.circuit_breaker.auto_enabled

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------

    @property
    def jwt_secret_key(self) -> str:
        """JWT secret key (defaults to SECRET_KEY)."""
        return self.security.secret_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Application settings loaded from environment.
    """
    return Settings()

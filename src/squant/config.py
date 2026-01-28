"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Squant"
    app_env: str = "production"
    debug: bool = False
    secret_key: SecretStr
    api_prefix: str = "/api/v1"

    # Database
    database_url: SecretStr

    # Redis
    redis_url: SecretStr

    # Security
    encryption_key: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str | None = None

    # Strategy Engine
    strategy_max_processes: int = 5
    strategy_memory_limit_mb: int = 512
    strategy_cpu_limit_seconds: int = 60
    strategy_sandbox_enabled: bool = True

    # Risk Control
    risk_max_position_ratio: float = 0.3
    risk_max_daily_loss_ratio: float = 0.05
    risk_max_orders_per_minute: int = 10

    # Exchange API (optional)
    binance_api_key: SecretStr | None = None
    binance_api_secret: SecretStr | None = None
    binance_testnet: bool = False

    okx_api_key: SecretStr | None = None
    okx_api_secret: SecretStr | None = None
    okx_passphrase: SecretStr | None = None
    okx_testnet: bool = False

    # Bybit Exchange API (optional)
    bybit_api_key: SecretStr | None = None
    bybit_api_secret: SecretStr | None = None
    bybit_testnet: bool = False

    # Exchange streaming configuration
    default_exchange: str = "okx"  # okx, binance, bybit
    use_ccxt_provider: bool = True  # False to use native OKX implementation

    # Paper Trading Memory Limits
    paper_max_equity_curve_size: int = 10000
    paper_max_completed_orders: int = 1000
    paper_max_fills: int = 5000
    paper_max_trades: int = 1000
    paper_max_logs: int = 1000

    # Paper Trading Health Check
    paper_health_check_interval_seconds: int = 60
    paper_session_timeout_seconds: int = 300  # 5 minutes inactivity = stale

    # Paper Trading Auto Persistence
    paper_persist_interval_seconds: int = 60  # Persist snapshots every minute

    # Circuit Breaker Settings
    circuit_breaker_cooldown_minutes: int = 60  # Default cooldown period
    circuit_breaker_auto_enabled: bool = False  # Auto-trigger disabled by default

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def jwt_secret_key(self) -> str:
        """JWT secret key defaults to SECRET_KEY."""
        return self.secret_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

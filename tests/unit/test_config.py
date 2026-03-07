"""Unit tests for squant.config module.

Tests cover:
- Validators on each nested settings class (valid and invalid inputs)
- Numeric boundary constraints (ge, le)
- Case normalization (uppercase levels, lowercase formats/envs)
- SecretStr masking
- get_settings() lru_cache singleton behavior
- Backward compatibility aliases on the main Settings class
"""

import pytest
from pydantic import SecretStr, ValidationError

from squant.config import (
    DatabaseSettings,
    ExchangeStreamSettings,
    LoggingSettings,
    PaperTradingSettings,
    RedisSettings,
    RiskSettings,
    SecuritySettings,
    Settings,
    StrategySettings,
    get_settings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimum env vars needed to construct Settings (which reads from env / .env)
_REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "SECRET_KEY": "a" * 32,
    "ENCRYPTION_KEY": "b" * 32,
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear the lru_cache on get_settings before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ===========================================================================
# DatabaseSettings
# ===========================================================================


class TestDatabaseSettings:
    """Tests for DatabaseSettings validator."""

    def test_valid_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
        s = DatabaseSettings()
        assert s.url.get_secret_value() == "postgresql+asyncpg://u:p@host:5432/db"

    def test_url_is_secret_str(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
        s = DatabaseSettings()
        assert isinstance(s.url, SecretStr)

    def test_rejects_non_postgresql(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "mysql+asyncpg://u:p@host:3306/db")
        with pytest.raises(ValidationError, match="PostgreSQL"):
            DatabaseSettings()

    def test_rejects_missing_asyncpg(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
        with pytest.raises(ValidationError, match="asyncpg"):
            DatabaseSettings()

    def test_str_representation_masks_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:secret@host:5432/db")
        s = DatabaseSettings()
        assert "secret" not in str(s.url)
        assert "**********" in str(s.url)


# ===========================================================================
# RedisSettings
# ===========================================================================


class TestRedisSettings:
    """Tests for RedisSettings validator."""

    def test_valid_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        s = RedisSettings()
        assert s.url.get_secret_value() == "redis://localhost:6379/0"

    def test_rejects_non_redis_scheme(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REDIS_URL", "http://localhost:6379/0")
        with pytest.raises(ValidationError, match="redis://"):
            RedisSettings()

    def test_rejects_empty_string(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REDIS_URL", "")
        with pytest.raises(ValidationError, match="redis://"):
            RedisSettings()


# ===========================================================================
# LoggingSettings
# ===========================================================================


class TestLoggingSettings:
    """Tests for LoggingSettings validators."""

    @pytest.mark.parametrize(
        "input_level,expected",
        [
            ("DEBUG", "DEBUG"),
            ("info", "INFO"),
            ("Warning", "WARNING"),
            ("error", "ERROR"),
            ("critical", "CRITICAL"),
        ],
    )
    def test_valid_levels_normalized_to_upper(
        self, monkeypatch: pytest.MonkeyPatch, input_level: str, expected: str
    ):
        monkeypatch.setenv("LOG_LEVEL", input_level)
        s = LoggingSettings()
        assert s.level == expected

    def test_invalid_level(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
        with pytest.raises(ValidationError, match="LOG_LEVEL"):
            LoggingSettings()

    @pytest.mark.parametrize(
        "input_format,expected",
        [("json", "json"), ("JSON", "json"), ("text", "text"), ("Text", "text")],
    )
    def test_valid_formats_normalized_to_lower(
        self, monkeypatch: pytest.MonkeyPatch, input_format: str, expected: str
    ):
        monkeypatch.setenv("LOG_FORMAT", input_format)
        s = LoggingSettings()
        assert s.format == expected

    def test_invalid_format(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LOG_FORMAT", "yaml")
        with pytest.raises(ValidationError, match="LOG_FORMAT"):
            LoggingSettings()

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch):
        """Without env vars, defaults should apply (INFO / text / None)."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_MAX_BYTES", raising=False)
        monkeypatch.delenv("LOG_BACKUP_COUNT", raising=False)
        s = LoggingSettings(_env_file=None)
        assert s.level == "INFO"
        assert s.format == "text"
        assert s.file is None
        assert s.max_bytes == 10 * 1024 * 1024
        assert s.backup_count == 5


# ===========================================================================
# SecuritySettings
# ===========================================================================


class TestSecuritySettings:
    """Tests for SecuritySettings validator."""

    def test_valid_secret_key(self, monkeypatch: pytest.MonkeyPatch):
        key = "x" * 32
        monkeypatch.setenv("SECRET_KEY", key)
        monkeypatch.setenv("ENCRYPTION_KEY", "y" * 32)
        s = SecuritySettings()
        assert s.secret_key.get_secret_value() == key

    def test_rejects_short_secret_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SECRET_KEY", "short")
        monkeypatch.setenv("ENCRYPTION_KEY", "y" * 32)
        with pytest.raises(ValidationError, match="at least 32"):
            SecuritySettings()

    def test_exactly_32_chars_accepted(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 32)
        s = SecuritySettings()
        assert len(s.secret_key.get_secret_value()) == 32

    def test_31_chars_rejected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SECRET_KEY", "a" * 31)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 32)
        with pytest.raises(ValidationError, match="at least 32"):
            SecuritySettings()

    def test_default_jwt_algorithm(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 32)
        s = SecuritySettings()
        assert s.jwt_algorithm == "HS256"

    def test_default_jwt_expire(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SECRET_KEY", "a" * 32)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 32)
        s = SecuritySettings()
        assert s.jwt_access_token_expire_minutes == 30


# ===========================================================================
# ExchangeStreamSettings
# ===========================================================================


class TestExchangeStreamSettings:
    """Tests for ExchangeStreamSettings validator."""

    @pytest.mark.parametrize(
        "input_val,expected",
        [("okx", "okx"), ("OKX", "okx"), ("Binance", "binance"), ("BYBIT", "bybit")],
    )
    def test_valid_exchanges_normalized_to_lower(
        self, monkeypatch: pytest.MonkeyPatch, input_val: str, expected: str
    ):
        monkeypatch.setenv("DEFAULT_EXCHANGE", input_val)
        s = ExchangeStreamSettings()
        assert s.default_exchange == expected

    def test_invalid_exchange(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEFAULT_EXCHANGE", "kraken")
        with pytest.raises(ValidationError, match="DEFAULT_EXCHANGE"):
            ExchangeStreamSettings()

    def test_default_values(self):
        s = ExchangeStreamSettings()
        assert s.default_exchange == "okx"
        assert s.use_ccxt_provider is True


# ===========================================================================
# StrategySettings -- numeric bounds
# ===========================================================================


class TestStrategySettings:
    """Tests for StrategySettings numeric bounds."""

    def test_defaults(self):
        s = StrategySettings()
        assert s.max_processes == 5
        assert s.memory_limit_mb == 2048
        assert s.cpu_limit_seconds == 60
        assert s.sandbox_enabled is True

    def test_max_processes_lower_bound(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_MAX_PROCESSES", "1")
        s = StrategySettings()
        assert s.max_processes == 1

    def test_max_processes_upper_bound(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_MAX_PROCESSES", "20")
        s = StrategySettings()
        assert s.max_processes == 20

    def test_max_processes_below_min(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_MAX_PROCESSES", "0")
        with pytest.raises(ValidationError):
            StrategySettings()

    def test_max_processes_above_max(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_MAX_PROCESSES", "21")
        with pytest.raises(ValidationError):
            StrategySettings()

    def test_memory_limit_at_minimum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_MEMORY_LIMIT_MB", "64")
        s = StrategySettings()
        assert s.memory_limit_mb == 64

    def test_memory_limit_below_minimum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_MEMORY_LIMIT_MB", "63")
        with pytest.raises(ValidationError):
            StrategySettings()

    def test_cpu_limit_at_minimum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_CPU_LIMIT_SECONDS", "1")
        s = StrategySettings()
        assert s.cpu_limit_seconds == 1

    def test_cpu_limit_below_minimum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_CPU_LIMIT_SECONDS", "0")
        with pytest.raises(ValidationError):
            StrategySettings()


# ===========================================================================
# RiskSettings -- numeric bounds
# ===========================================================================


class TestRiskSettings:
    """Tests for RiskSettings numeric bounds."""

    def test_defaults(self):
        s = RiskSettings()
        assert s.max_position_ratio == 0.3
        assert s.max_daily_loss_ratio == 0.05
        assert s.max_orders_per_minute == 10

    @pytest.mark.parametrize("val", ["0.01", "0.5", "1.0"])
    def test_valid_position_ratio(self, monkeypatch: pytest.MonkeyPatch, val: str):
        monkeypatch.setenv("RISK_MAX_POSITION_RATIO", val)
        s = RiskSettings()
        assert 0.01 <= s.max_position_ratio <= 1.0

    def test_position_ratio_below_min(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_MAX_POSITION_RATIO", "0.009")
        with pytest.raises(ValidationError):
            RiskSettings()

    def test_position_ratio_above_max(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_MAX_POSITION_RATIO", "1.01")
        with pytest.raises(ValidationError):
            RiskSettings()

    @pytest.mark.parametrize("val", ["0.01", "0.25", "0.5"])
    def test_valid_daily_loss_ratio(self, monkeypatch: pytest.MonkeyPatch, val: str):
        monkeypatch.setenv("RISK_MAX_DAILY_LOSS_RATIO", val)
        s = RiskSettings()
        assert 0.01 <= s.max_daily_loss_ratio <= 0.5

    def test_daily_loss_ratio_below_min(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_MAX_DAILY_LOSS_RATIO", "0.009")
        with pytest.raises(ValidationError):
            RiskSettings()

    def test_daily_loss_ratio_above_max(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_MAX_DAILY_LOSS_RATIO", "0.51")
        with pytest.raises(ValidationError):
            RiskSettings()

    def test_orders_per_minute_at_minimum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_MAX_ORDERS_PER_MINUTE", "1")
        s = RiskSettings()
        assert s.max_orders_per_minute == 1

    def test_orders_per_minute_below_minimum(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RISK_MAX_ORDERS_PER_MINUTE", "0")
        with pytest.raises(ValidationError):
            RiskSettings()


# ===========================================================================
# PaperTradingSettings -- numeric bounds
# ===========================================================================


class TestPaperTradingSettings:
    """Tests for PaperTradingSettings numeric bounds."""

    def test_defaults(self):
        s = PaperTradingSettings()
        assert s.max_equity_curve_size == 10000
        assert s.max_completed_orders == 1000
        assert s.max_fills == 5000
        assert s.max_trades == 1000
        assert s.max_logs == 1000
        assert s.health_check_interval_seconds == 60
        assert s.session_timeout_seconds == 300
        assert s.persist_interval_seconds == 60
        assert s.max_sessions == 20

    @pytest.mark.parametrize(
        "field,env_var,min_val",
        [
            ("max_equity_curve_size", "PAPER_MAX_EQUITY_CURVE_SIZE", 100),
            ("max_completed_orders", "PAPER_MAX_COMPLETED_ORDERS", 100),
            ("max_fills", "PAPER_MAX_FILLS", 100),
            ("max_trades", "PAPER_MAX_TRADES", 100),
            ("max_logs", "PAPER_MAX_LOGS", 100),
            ("health_check_interval_seconds", "PAPER_HEALTH_CHECK_INTERVAL_SECONDS", 10),
            ("session_timeout_seconds", "PAPER_SESSION_TIMEOUT_SECONDS", 60),
            ("persist_interval_seconds", "PAPER_PERSIST_INTERVAL_SECONDS", 10),
        ],
    )
    def test_at_minimum(
        self, monkeypatch: pytest.MonkeyPatch, field: str, env_var: str, min_val: int
    ):
        monkeypatch.setenv(env_var, str(min_val))
        s = PaperTradingSettings()
        assert getattr(s, field) == min_val

    @pytest.mark.parametrize(
        "env_var,below_min",
        [
            ("PAPER_MAX_EQUITY_CURVE_SIZE", "99"),
            ("PAPER_MAX_COMPLETED_ORDERS", "99"),
            ("PAPER_MAX_FILLS", "99"),
            ("PAPER_MAX_TRADES", "99"),
            ("PAPER_MAX_LOGS", "99"),
            ("PAPER_HEALTH_CHECK_INTERVAL_SECONDS", "9"),
            ("PAPER_SESSION_TIMEOUT_SECONDS", "59"),
            ("PAPER_PERSIST_INTERVAL_SECONDS", "9"),
        ],
    )
    def test_below_minimum(self, monkeypatch: pytest.MonkeyPatch, env_var: str, below_min: str):
        monkeypatch.setenv(env_var, below_min)
        with pytest.raises(ValidationError):
            PaperTradingSettings()

    def test_max_sessions_lower_bound(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PAPER_MAX_SESSIONS", "1")
        s = PaperTradingSettings()
        assert s.max_sessions == 1

    def test_max_sessions_upper_bound(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PAPER_MAX_SESSIONS", "100")
        s = PaperTradingSettings()
        assert s.max_sessions == 100

    def test_max_sessions_below_min(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PAPER_MAX_SESSIONS", "0")
        with pytest.raises(ValidationError):
            PaperTradingSettings()

    def test_max_sessions_above_max(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PAPER_MAX_SESSIONS", "101")
        with pytest.raises(ValidationError):
            PaperTradingSettings()


# ===========================================================================
# Settings -- app_env validator
# ===========================================================================


class TestSettingsAppEnv:
    """Tests for Settings.validate_app_env."""

    @pytest.mark.parametrize(
        "input_env,expected",
        [
            ("development", "development"),
            ("DEVELOPMENT", "development"),
            ("test", "test"),
            ("TEST", "test"),
            ("staging", "staging"),
            ("Staging", "staging"),
            ("production", "production"),
            ("PRODUCTION", "production"),
        ],
    )
    def test_valid_app_env(self, monkeypatch: pytest.MonkeyPatch, input_env: str, expected: str):
        for k, v in _REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("APP_ENV", input_env)
        s = Settings()
        assert s.app_env == expected

    def test_invalid_app_env(self, monkeypatch: pytest.MonkeyPatch):
        for k, v in _REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("APP_ENV", "local")
        with pytest.raises(ValidationError, match="APP_ENV"):
            Settings()


# ===========================================================================
# get_settings() lru_cache singleton
# ===========================================================================


class TestGetSettings:
    """Tests for get_settings() caching behavior."""

    def test_returns_settings_instance(self, monkeypatch: pytest.MonkeyPatch):
        for k, v in _REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        s = get_settings()
        assert isinstance(s, Settings)

    def test_returns_same_instance(self, monkeypatch: pytest.MonkeyPatch):
        for k, v in _REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cache_clear_produces_new_instance(self, monkeypatch: pytest.MonkeyPatch):
        for k, v in _REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        s1 = get_settings()
        get_settings.cache_clear()
        s2 = get_settings()
        assert s1 is not s2


# ===========================================================================
# Backward compatibility aliases
# ===========================================================================


class TestBackwardCompatibilityAliases:
    """Test a representative sample of backward compat aliases."""

    @pytest.fixture()
    def settings(self, monkeypatch: pytest.MonkeyPatch) -> Settings:
        for k, v in _REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.setenv("DEFAULT_EXCHANGE", "binance")
        return Settings()

    def test_log_level_alias(self, settings: Settings):
        assert settings.log_level == settings.logging.level
        assert settings.log_level == "WARNING"

    def test_log_format_alias(self, settings: Settings):
        assert settings.log_format == settings.logging.format
        assert settings.log_format == "json"

    def test_database_url_alias(self, settings: Settings):
        assert settings.database_url is settings.database.url

    def test_redis_url_alias(self, settings: Settings):
        assert settings.redis_url is settings.redis.url

    def test_secret_key_alias(self, settings: Settings):
        assert settings.secret_key is settings.security.secret_key

    def test_encryption_key_alias(self, settings: Settings):
        assert settings.encryption_key is settings.security.encryption_key

    def test_default_exchange_alias(self, settings: Settings):
        assert settings.default_exchange == settings.exchange.default_exchange
        assert settings.default_exchange == "binance"

    def test_jwt_secret_key_computed(self, settings: Settings):
        """jwt_secret_key should return the plain string from security.secret_key."""
        assert settings.jwt_secret_key == settings.security.secret_key.get_secret_value()

    def test_strategy_aliases(self, settings: Settings):
        assert settings.strategy_max_processes == settings.strategy.max_processes
        assert settings.strategy_memory_limit_mb == settings.strategy.memory_limit_mb
        assert settings.strategy_cpu_limit_seconds == settings.strategy.cpu_limit_seconds
        assert settings.strategy_sandbox_enabled == settings.strategy.sandbox_enabled

    def test_risk_aliases(self, settings: Settings):
        assert settings.risk_max_position_ratio == settings.risk.max_position_ratio
        assert settings.risk_max_daily_loss_ratio == settings.risk.max_daily_loss_ratio
        assert settings.risk_max_orders_per_minute == settings.risk.max_orders_per_minute

    def test_paper_aliases(self, settings: Settings):
        assert settings.paper_max_sessions == settings.paper.max_sessions
        assert settings.paper_max_equity_curve_size == settings.paper.max_equity_curve_size
        assert (
            settings.paper_health_check_interval_seconds
            == settings.paper.health_check_interval_seconds
        )

    def test_circuit_breaker_aliases(self, settings: Settings):
        assert (
            settings.circuit_breaker_cooldown_minutes == settings.circuit_breaker.cooldown_minutes
        )
        assert settings.circuit_breaker_auto_enabled == settings.circuit_breaker.auto_enabled


# ===========================================================================
# SecretStr masking
# ===========================================================================


class TestSecretStrMasking:
    """Verify that SecretStr fields do not leak values in string representations."""

    def test_database_url_masked(self, monkeypatch: pytest.MonkeyPatch):
        real_url = "postgresql+asyncpg://user:supersecret@host:5432/db"
        monkeypatch.setenv("DATABASE_URL", real_url)
        s = DatabaseSettings()
        assert "supersecret" not in str(s.url)
        assert "supersecret" not in repr(s.url)

    def test_redis_url_masked(self, monkeypatch: pytest.MonkeyPatch):
        real_url = "redis://default:mypassword@host:6379/0"
        monkeypatch.setenv("REDIS_URL", real_url)
        s = RedisSettings()
        assert "mypassword" not in str(s.url)

    def test_secret_key_masked(self, monkeypatch: pytest.MonkeyPatch):
        key = "this-is-a-very-secret-key-that-must-not-leak"
        monkeypatch.setenv("SECRET_KEY", key)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 32)
        s = SecuritySettings()
        assert key not in str(s.secret_key)
        assert key not in repr(s)

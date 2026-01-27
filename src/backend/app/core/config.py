from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Squant"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "your-secret-key-change-this-in-production"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/squant"
    test_database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/squant_test"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # CORS
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Trading
    max_position_size: int = 10000
    max_daily_trades: int = 100

    # Encryption
    encryption_key: str = ""  # 必须配置，否则应用无法启动

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

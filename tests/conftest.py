"""Pytest configuration and fixtures."""

import os
from pathlib import Path

import pytest

# ==========================================================================
# 集成测试环境配置
# ==========================================================================

def _load_env_file_for_integration(env_file: Path) -> None:
    """为集成测试加载 .env.test 环境变量（覆盖关键变量）"""
    if not env_file.exists():
        return

    override_keys = {
        "DATABASE_URL",
        "REDIS_URL",
        "SECRET_KEY",
        "ENCRYPTION_KEY",
        "APP_ENV",
    }

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and (key in override_keys or key not in os.environ):
                    os.environ[key] = value


def pytest_configure(config):
    """pytest 配置钩子 - 在测试收集之前执行"""
    # 检查是否运行集成测试
    # 通过检查 testpaths 或命令行参数判断
    args = config.invocation_params.args if hasattr(config, 'invocation_params') else []
    is_integration = any('integration' in str(arg) for arg in args)

    if is_integration:
        # 加载 .env.test 配置
        env_test_path = Path(__file__).parent.parent / ".env.test"
        _load_env_file_for_integration(env_test_path)

        # 清除 get_settings 缓存
        try:
            from squant.config import get_settings
            get_settings.cache_clear()
        except ImportError:
            pass


# ==========================================================================
# 通用 Fixtures (延迟导入以避免提前加载配置)
# ==========================================================================

@pytest.fixture
def client():
    """Create test client (延迟导入)."""
    from fastapi.testclient import TestClient

    from squant.main import app
    return TestClient(app)

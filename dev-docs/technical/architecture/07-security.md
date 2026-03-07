# 安全设计

> **关联文档**: [架构概览](./01-overview.md)

## 1. API Key 存储

```
┌─────────────────────────────────────────────────────────┐
│                    API Key 加密流程                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  用户输入 API Key                                        │
│        │                                                │
│        ▼                                                │
│  ┌─────────────────┐                                    │
│  │ AES-256-GCM 加密 │◀── Master Key (环境变量)          │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │   PostgreSQL    │  存储: encrypted_key + nonce       │
│  └─────────────────┘                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 加密实现

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

def encrypt_api_key(api_key: str, master_key: bytes) -> tuple[bytes, bytes]:
    """加密 API Key"""
    nonce = os.urandom(12)  # 96-bit nonce
    aesgcm = AESGCM(master_key)
    encrypted = aesgcm.encrypt(nonce, api_key.encode(), None)
    return encrypted, nonce

def decrypt_api_key(encrypted: bytes, nonce: bytes, master_key: bytes) -> str:
    """解密 API Key"""
    aesgcm = AESGCM(master_key)
    decrypted = aesgcm.decrypt(nonce, encrypted, None)
    return decrypted.decode()
```

## 2. 策略沙箱

| 层级 | 机制 | 说明 |
|------|------|------|
| **代码层** | RestrictedPython | 禁止危险模块和操作 |
| **进程层** | 独立子进程 | 进程级隔离 |
| **资源层** | resource 模块 | CPU 时间、内存限制 |
| **网络层** | 默认禁止 | 策略不能发起网络请求 |

### 禁止的操作

```python
# 禁止的内置函数
DISALLOWED_BUILTINS = {
    "eval", "exec", "compile",
    "open", "file",
    "__import__",
    "input", "raw_input",
    "globals", "locals",
    "getattr", "setattr", "delattr",
}

# 禁止的模块
DISALLOWED_MODULES = {
    "os", "sys", "subprocess", "shutil",
    "socket", "urllib", "requests", "httpx",
    "pickle", "marshal",
    "ctypes", "multiprocessing",
}
```

## 3. 权限控制

```python
# API Key 权限最小化原则
REQUIRED_PERMISSIONS = {
    "binance": {
        "read": True,           # 读取账户、行情
        "spot_trade": True,     # 现货交易
        "futures_trade": False, # 禁止合约（Phase 1）
        "withdraw": False       # 禁止提现
    }
}
```

## 4. 安全检查清单

| 检查项 | 说明 |
|--------|------|
| Master Key | 通过环境变量配置，不提交到代码库 |
| API Key | AES-256-GCM 加密存储 |
| 数据库密码 | 强密码，通过环境变量配置 |
| Redis 密码 | 生产环境必须设置密码 |
| HTTPS | 生产环境使用 Caddy 自动配置 |
| DEBUG | 生产环境必须关闭 |
| 策略沙箱 | 生产环境必须启用 |

## 5. 敏感信息管理

```python
# 使用 Pydantic SecretStr
from pydantic import SecretStr

class Settings(BaseSettings):
    secret_key: SecretStr
    database_url: SecretStr
    binance_api_key: SecretStr | None = None

# SecretStr 不会在日志中泄露
settings.secret_key  # 显示: SecretStr('**********')
settings.secret_key.get_secret_value()  # 获取实际值
```

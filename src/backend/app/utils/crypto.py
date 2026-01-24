"""
加密工具模块

使用 Fernet 对称加密算法加密敏感数据（如 API Key）。
"""
from cryptography.fernet import Fernet
import base64
import hashlib

from app.core.config import settings


def get_encryption_key() -> str:
    """
    获取加密密钥。

    从配置或环境变量读取加密密钥。
    密钥必须是 32 字节（Fernet 要求）。

    Returns:
        str: URL-safe base64 编码的加密密钥

    Raises:
        ValueError: 如果未配置加密密钥
    """
    # 从配置中读取密钥（必须配置）
    key_str = settings.encryption_key

    if not key_str:
        raise ValueError(
            "未配置加密密钥 (ENCRYPTION_KEY)。"
            "请在 .env 文件中设置 ENCRYPTION_KEY 环境变量。"
            "可以使用以下命令生成密钥："
            "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    # 确保密钥是 32 字节
    key_bytes = key_str.encode('utf-8')
    if len(key_bytes) < 32:
        # 如果密钥太短，用零填充到 32 字节
        key_bytes = key_bytes.ljust(32, b'\x00')[:32]
    elif len(key_bytes) > 32:
        # 如果密钥太长，用 SHA-256 哈希得到 32 字节
        key_bytes = hashlib.sha256(key_bytes).digest()

    # 转换为 Fernet 需要的 base64 格式
    return base64.urlsafe_b64encode(key_bytes).decode()


# 初始化 Fernet 实例（应用启动时必须成功，否则报错）
ENCRYPTION_KEY = get_encryption_key()
fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


def encrypt_data(data: str) -> str:
    """
    加密字符串数据。

    Args:
        data: 要加密的明文字符串

    Returns:
        str: base64 编码的加密数据

    Raises:
        Exception: 加密失败时抛出异常
    """
    if not data:
        return ""
    encrypted = fernet.encrypt(data.encode('utf-8'))
    return encrypted.decode('utf-8')


def decrypt_data(encrypted: str) -> str:
    """
    解密字符串数据。

    Args:
        encrypted: base64 编码的加密数据

    Returns:
        str: 解密后的明文字符串

    Raises:
        InvalidToken: 解密失败（密钥错误或数据损坏）
    """
    if not encrypted:
        return ""
    decrypted = fernet.decrypt(encrypted.encode('utf-8'))
    return decrypted.decode('utf-8')

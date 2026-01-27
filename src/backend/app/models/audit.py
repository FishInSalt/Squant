"""
审计日志模型

定义所有审计日志相关的数据模型。
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.sql import func

from app.db.database import Base
import logging

logger = logging.getLogger(__name__)


class AuditLog(Base):
    """审计日志表"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 操作信息
    action_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="操作类型: CREATE, UPDATE, DELETE, VALIDATE_API, VALIDATE_ACCOUNT, UPDATE_VALIDATION_STATUS",
    )

    # 操作者信息
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="操作者用户ID",
    )
    username = Column(String(50), nullable=True, comment="用户名")

    # 请求信息
    ip_address = Column(String(45), nullable=True, index=True, comment="IP地址")
    user_agent = Column(String(500), nullable=True, comment="User-Agent")
    request_id = Column(String(100), nullable=True, unique=True, comment="请求ID")

    # 操作目标
    resource_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment="资源类型: account, exchange_connection, api_validation",
    )
    resource_id = Column(
        Integer, nullable=True, index=True, comment="资源ID（如account_id）"
    )

    # 操作数据
    request_data = Column(
        Text, nullable=True, comment="请求数据（JSON字符串，敏感信息已脱敏）"
    )

    # 操作结果
    status = Column(
        String(20), nullable=False, index=True, comment="操作状态: SUCCESS, FAILED"
    )
    error_message = Column(Text, nullable=True, comment="错误信息（如果失败）")

    # 敏感信息（掩码）
    sensitive_data = Column(Text, nullable=True, comment="敏感数据掩码后的信息")

    # 时间戳
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), comment="更新时间"
    )

    # 索引
    __table_args__ = (
        Index("idx_audit_action_type", "action_type"),
        Index("idx_audit_user_id", "user_id"),
        Index("idx_audit_resource_type", "resource_type"),
        Index("idx_audit_resource_id", "resource_id"),
        Index("idx_audit_status", "status"),
        Index("idx_audit_created_at", "created_at"),
        Index("idx_audit_user_action", "user_id", "action_type"),
        Index("idx_audit_resource_user", "resource_type", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action={self.action_type}, "
            f"user_id={self.user_id}, status={self.status})>"
        )


class AuditActionType:
    """审计操作类型常量"""

    CREATE_ACCOUNT = "CREATE_ACCOUNT"
    UPDATE_ACCOUNT = "UPDATE_ACCOUNT"
    DELETE_ACCOUNT = "DELETE_ACCOUNT"
    VALIDATE_API = "VALIDATE_API"
    VALIDATE_ACCOUNT = "VALIDATE_ACCOUNT"
    UPDATE_VALIDATION_STATUS = "UPDATE_VALIDATION_STATUS"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    READ_ACCOUNT = "READ_ACCOUNT"
    READ_ACCOUNTS = "READ_ACCOUNTS"


class AuditStatus:
    """审计状态常量"""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class MaskingHelper:
    """敏感信息掩码辅助类"""

    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """
        掩码API Key

        Args:
            api_key: API Key字符串

        Returns:
            掩码后的API Key
        """
        if not api_key or len(api_key) < 8:
            return "***"
        # 保留前4位和后4位
        return f"{api_key[:4]}...{api_key[-4:]}"

    @staticmethod
    def mask_api_passphrase(passphrase: str) -> str:
        """
        掩码Passphrase

        Args:
            passphrase: Passphrase字符串

        Returns:
            掩码后的Passphrase
        """
        if not passphrase:
            return "***"
        # Passphrase应该完全隐藏
        return f"****{len(passphrase) - 4}****"

    @staticmethod
    def mask_api_secret(api_secret: str) -> str:
        """
        掩码API Secret

        Args:
            api_secret: API Secret字符串

        Returns:
            掩码后的API Secret
        """
        if not api_secret:
            return "***"
        # API Secret应该完全隐藏
        return f"****{len(api_secret) - 4}****"

    @staticmethod
    def mask_sensitive_data(data: dict) -> dict:
        """
        掩码敏感数据字典

        Args:
            data: 原始数据字典

        Returns:
            掩码后的数据字典
        """
        if not isinstance(data, dict):
            return {}

        masked = data.copy()

        # 掩码敏感字段
        sensitive_fields = [
            "api_key",
            "api_secret",
            "passphrase",
            "apiKey",
            "apiSecret",
            "passPhrase",
        ]

        for field in sensitive_fields:
            if field in masked:
                if field in ["api_key", "apiKey"]:
                    masked[field] = MaskingHelper.mask_api_key(str(masked[field]))
                elif field in ["api_secret", "apiSecret"]:
                    masked[field] = MaskingHelper.mask_api_secret(str(masked[field]))
                else:  # passphrase
                    masked[field] = "****"

        return masked

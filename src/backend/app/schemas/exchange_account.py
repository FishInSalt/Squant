"""
交易所账户相关的 Pydantic schemas
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.models.exchange_account import ExchangeType


# ==================== 基础 Schema ====================

class ExchangeAccountBase(BaseModel):
    """交易所账户基础 schema"""
    exchange: ExchangeType
    label: str = Field(..., min_length=1, max_length=100, description="账户标签")
    is_active: Optional[bool] = True


class ExchangeAccountCreate(ExchangeAccountBase):
    """创建交易所账户的请求"""
    api_key: str = Field(..., min_length=1, description="交易所 API Key")
    api_secret: str = Field(..., min_length=1, description="交易所 API Secret")
    passphrase: Optional[str] = Field(None, description="API Passphrase（某些交易所需要）")

    @field_validator('exchange')
    @classmethod
    def validate_exchange(cls, v: ExchangeType) -> ExchangeType:
        """验证交易所类型"""
        if v not in ExchangeType:
            raise ValueError(f"不支持的交易所类型: {v}")
        return v


class ExchangeAccountUpdate(BaseModel):
    """更新交易所账户的请求"""
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    api_key: Optional[str] = Field(None, min_length=1)
    api_secret: Optional[str] = Field(None, min_length=1)
    passphrase: Optional[str] = Field(None)
    is_active: Optional[bool] = None


class ExchangeAccountValidateRequest(BaseModel):
    """验证交易所连接的请求"""
    api_key: str
    api_secret: str
    exchange: ExchangeType
    passphrase: Optional[str] = None


# ==================== 响应 Schema ====================

class ExchangeAccountResponse(ExchangeAccountBase):
    """交易所账户响应（不返回敏感信息）"""
    id: int
    user_id: int
    is_validated: bool
    last_validated_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ExchangeAccountDetailResponse(ExchangeAccountResponse):
    """交易所账户详细响应（包含部分脱敏的 API 信息）"""
    # 脱敏的 API Key（只显示前 4 位）
    api_key_masked: str

    @classmethod
    def from_account(cls, account, api_key: str):
        """从账户对象创建，添加脱敏的 API Key"""
        masked = api_key[:4] + "****" if api_key else ""
        return cls(
            id=account.id,
            user_id=account.user_id,
            exchange=account.exchange,
            label=account.label,
            is_active=account.is_active,
            is_validated=account.is_validated,
            last_validated_at=account.last_validated_at,
            created_at=account.created_at,
            updated_at=account.updated_at,
            api_key_masked=masked
        )


class ValidationResponse(BaseModel):
    """账户验证响应"""
    is_valid: bool
    message: str
    exchange_account_id: Optional[int] = None

"""
交易所账户配置 API

提供创建、读取、更新、删除和验证交易所账户的端点。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timezone
from typing import List

from app.db.database import get_db
from app.models.exchange_account import ExchangeAccount
from app.schemas.exchange_account import (
    ExchangeAccountCreate,
    ExchangeAccountUpdate,
    ExchangeAccountResponse,
    ExchangeAccountDetailResponse,
    ExchangeAccountValidateRequest,
    ValidationResponse
)
from app.utils.crypto import encrypt_data, decrypt_data
from app.market.exchange_validator import ExchangeValidator


router = APIRouter()


# ==================== 创建账户 ====================

@router.post("/", response_model=ExchangeAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_exchange_account(
    account: ExchangeAccountCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    创建新的交易所账户。

    API Key 和 Secret 会自动加密存储。
    """
    # 加密敏感信息
    encrypted_key = encrypt_data(account.api_key)
    encrypted_secret = encrypt_data(account.api_secret)
    encrypted_passphrase = encrypt_data(account.passphrase) if account.passphrase else None

    # 创建数据库记录
    db_account = ExchangeAccount(
        user_id=1,  # TODO: 从认证上下文获取用户 ID
        exchange=account.exchange,
        label=account.label,
        api_key=encrypted_key,
        api_secret=encrypted_secret,
        passphrase=encrypted_passphrase,
        is_active=account.is_active
    )

    try:
        db.add(db_account)
        await db.commit()
        await db.refresh(db_account)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建账户失败: {str(e)}"
        )

    return db_account


# ==================== 获取账户列表 ====================

@router.get("/", response_model=List[ExchangeAccountResponse])
async def get_exchange_accounts(db: AsyncSession = Depends(get_db)):
    """获取所有交易所账户列表（不返回敏感信息）。"""
    result = await db.execute(select(ExchangeAccount))
    accounts = result.scalars().all()
    return accounts


# ==================== 获取单个账户 ====================

@router.get("/{account_id}", response_model=ExchangeAccountDetailResponse)
async def get_exchange_account(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个交易所账户的详细信息（包含脱敏的 API Key）。"""
    result = await db.execute(
        select(ExchangeAccount).where(ExchangeAccount.id == account_id)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账户 ID {account_id} 不存在"
        )

    # 解密 API Key 用于脱敏显示
    api_key = decrypt_data(str(account.api_key))  # type: ignore[arg-type]
    return ExchangeAccountDetailResponse.from_account(account, api_key)


# ==================== 更新账户 ====================

@router.put("/{account_id}", response_model=ExchangeAccountResponse)
async def update_exchange_account(
    account_id: int,
    account_update: ExchangeAccountUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新交易所账户信息。"""
    result = await db.execute(
        select(ExchangeAccount).where(ExchangeAccount.id == account_id)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账户 ID {account_id} 不存在"
        )

    # 更新字段（只更新提供的字段）
    if account_update.label is not None:
        account.label = account_update.label  # type: ignore[assignment]
    if account_update.api_key is not None:
        account.api_key = encrypt_data(account_update.api_key)  # type: ignore[assignment]
        # 更新 API Key 后需要重新验证
        account.is_validated = False  # type: ignore[assignment]
        account.last_validated_at = None  # type: ignore[assignment]
    if account_update.api_secret is not None:
        account.api_secret = encrypt_data(account_update.api_secret)  # type: ignore[assignment]
        account.is_validated = False  # type: ignore[assignment]
        account.last_validated_at = None  # type: ignore[assignment]
    if account_update.passphrase is not None:
        account.passphrase = encrypt_data(account_update.passphrase)  # type: ignore[assignment]
        account.is_validated = False  # type: ignore[assignment]
        account.last_validated_at = None  # type: ignore[assignment]
    if account_update.is_active is not None:
        account.is_active = account_update.is_active  # type: ignore[assignment]

    try:
        await db.commit()
        await db.refresh(account)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新账户失败: {str(e)}"
        )

    return account


# ==================== 删除账户 ====================

@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exchange_account(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除交易所账户。"""
    result = await db.execute(
        delete(ExchangeAccount).where(ExchangeAccount.id == account_id)
    )

    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账户 ID {account_id} 不存在"
        )

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除账户失败: {str(e)}"
        )


# ==================== 验证账户连接 ====================

@router.post("/{account_id}/validate", response_model=ValidationResponse)
async def validate_exchange_account(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """验证交易所账户的 API 连接。"""
    result = await db.execute(
        select(ExchangeAccount).where(ExchangeAccount.id == account_id)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账户 ID {account_id} 不存在"
        )

    # 解密 API 凭证
    api_key = decrypt_data(str(account.api_key))  # type: ignore[arg-type]
    api_secret = decrypt_data(str(account.api_secret))  # type: ignore[arg-type]
    passphrase = decrypt_data(str(account.passphrase)) if account.passphrase else None  # type: ignore[arg-type]

    # 调用验证器
    validation_result = await ExchangeValidator.validate_exchange(
        exchange=account.exchange,  # type: ignore[arg-type]
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase if passphrase else ""  # type: ignore[arg-type]
    )

    # 更新验证状态
    account.is_validated = validation_result['is_valid']  # type: ignore[assignment]
    account.last_validated_at = datetime.now(timezone.utc) if validation_result['is_valid'] else None  # type: ignore[assignment]

    try:
        await db.commit()
        await db.refresh(account)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新验证状态失败: {str(e)}"
        )

    return ValidationResponse(
        is_valid=validation_result['is_valid'],
        message=validation_result['message'],
        exchange_account_id=int(account.id)  # type: ignore[arg-type]
    )


# ==================== 验证新的 API 凭证 ====================

@router.post("/validate", response_model=ValidationResponse)
async def validate_api_credentials(
    request: ExchangeAccountValidateRequest
):
    """
    在创建账户前验证 API 凭证是否有效。

    不创建数据库记录，仅验证。
    """
    validation_result = await ExchangeValidator.validate_exchange(
        exchange=request.exchange,
        api_key=request.api_key,
        api_secret=request.api_secret,
        passphrase=request.passphrase if request.passphrase else ""  # type: ignore[arg-type]
    )

    return ValidationResponse(
        is_valid=validation_result['is_valid'],
        message=validation_result['message']
    )

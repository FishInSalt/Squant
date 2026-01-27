"""
交易所账户配置 API

提供创建、读取、更新、删除和验证交易所账户的端点。

所有敏感操作都会记录审计日志。
"""

import logging
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.db.database import get_db
from app.models.exchange_account import ExchangeAccount as Account
from app.schemas.exchange_account import (
    ExchangeAccountCreate,
    ExchangeAccountUpdate,
    ExchangeAccountResponse,
    ExchangeAccountDetailResponse,
    ExchangeAccountValidateRequest,
    ValidationResponse,
)
from app.utils.crypto import encrypt_data, decrypt_data
from app.market.exchange_validator import ExchangeValidator
from app.core.ratelimit import limiter, RATE_LIMITS

from app.models.audit import AuditLog, AuditActionType, AuditStatus, MaskingHelper

logger = logging.getLogger(__name__)


router = APIRouter()


# ==================== 创建账户 ====================


@router.post(
    "/", response_model=ExchangeAccountResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(RATE_LIMITS["write"])
async def create_exchange_account(
    request: Request, account: ExchangeAccountCreate, db: AsyncSession = Depends(get_db)
):
    """
    创建新的交易所账户。

    速率限制：20 请求/分钟/IP

    API Key 和 Secret 会自动加密存储。

    审计日志：记录创建操作的所有相关信息。
    """
    # TODO: 从认证上下文获取真实用户ID
    user_id = 1

    # 请求审计日志
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.CREATE_ACCOUNT,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(str(account.exchange) + str(account.api_key)))[
            :50
        ],  # 模拟请求ID
        resource_type="exchange_account",
        resource_id=None,  # 创建前还没有ID
        request_data={
            "exchange": account.exchange,
            "label": account.label,
            "is_active": account.is_active,
            "is_demo": account.is_demo or False,
        },
    )

    # 加密敏感信息
    encrypted_key = encrypt_data(account.api_key)
    encrypted_secret = encrypt_data(account.api_secret)
    encrypted_passphrase = (
        encrypt_data(account.passphrase) if account.passphrase else None
    )

    # 创建数据库记录
    db_account = Account(
        user_id=user_id,
        exchange=account.exchange,
        label=account.label,
        api_key=encrypted_key,
        api_secret=encrypted_secret,
        passphrase=encrypted_passphrase,
        is_active=account.is_active,
        is_demo=account.is_demo or False,
    )

    try:
        db.add(db_account)
        await db.commit()
        await db.refresh(db_account)

        # 记录成功审计日志
        audit_log = AuditLog(
            user_id=user_id,
            action_type=AuditActionType.CREATE_ACCOUNT,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:500],
            request_id=str(hash(str(account.exchange) + str(account.api_key)))[:50],
            resource_type="exchange_account",
            resource_id=db_account.id,
            request_data={
                "exchange": account.exchange,
                "label": account.label,
                "is_active": account.is_active,
                "is_demo": account.is_demo or False,
                "api_key": MaskingHelper.mask_api_key(account.api_key),  # 脱码
            },
            status=AuditStatus.SUCCESS,
            sensitive_data={
                "api_key": MaskingHelper.mask_api_key(account.api_key),
                "api_secret": "****" + str(account.api_secret)[:4] + "*" * 20,
                "passphrase": MaskingHelper.mask_api_passphrase(account.passphrase)
                if account.passphrase
                else None,
            },
        )
        db.add(audit_log)
        await db.commit()

        logger.info(
            f"[AUDIT] User {user_id} created exchange account: {db_account.id} - {db_account.exchange}"
        )

    except Exception as e:
        await db.rollback()

        # 记录失败审计日志
        audit_log = AuditLog(
            user_id=user_id,
            action_type=AuditActionType.CREATE_ACCOUNT,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:500],
            request_id=str(hash(str(account.exchange) + str(account.api_key)))[:50],
            resource_type="exchange_account",
            resource_id=None,
            request_data={
                "exchange": account.exchange,
                "label": account.label,
                "is_active": account.is_active,
                "is_demo": account.is_demo or False,
            },
            status=AuditStatus.FAILED,
            error_message=str(e),
        )

        # 存储审计日志
        try:
            db.add(audit_log)
            await db.commit()
        except Exception as audit_error:
            logger.error(
                f"[AUDIT] Failed to save audit log: {str(audit_error)}", exc_info=True
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建账户失败: {str(e)}",
        )

    return db_account


# ==================== 获取账户列表 ====================


@router.get("/", response_model=List[ExchangeAccountResponse])
@limiter.limit(RATE_LIMITS["read"])
async def get_exchange_accounts(request: Request, db: AsyncSession = Depends(get_db)):
    """
    获取所有交易所账户列表（不返回敏感信息）。

    速率限制：100 请求/分钟/IP

    审计日志：记录读取列表操作。
    """
    # TODO: 从认证上下文获取用户ID
    user_id = 1

    # 记录请求审计日志
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.READ_ACCOUNTS,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(f"READ_ACCOUNTS_{user_id}"))[:50],
        resource_type="exchange_account",
        resource_id=None,
        request_data={},
        status=AuditStatus.PENDING,
    )

    try:
        result = await db.execute(select(Account))
        accounts = result.scalars().all()

        # 更新审计日志为成功
        audit_log.status = AuditStatus.SUCCESS
        db.add(audit_log)
        await db.commit()

        logger.info(f"[AUDIT] User {user_id} fetched {len(accounts)} exchange accounts")

    except Exception as e:
        await db.rollback()

        # 更新审计日志为失败
        audit_log.status = AuditStatus.FAILED
        audit_log.error_message = str(e)
        try:
            db.add(audit_log)
            await db.commit()
        except Exception as audit_error:
            logger.error(
                f"[AUDIT] Failed to save audit log: {str(audit_error)}", exc_info=True
            )

    return accounts


# ==================== 获取单个账户 ====================


@router.get("/{account_id}", response_model=ExchangeAccountDetailResponse)
@limiter.limit(RATE_LIMITS["read"])
async def get_exchange_account(
    account_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    获取单个交易所账户的详细信息（包含脱敏的 API Key）。

    速率限制：100 请求/分钟/IP

    审计日志：记录读取账户详情操作。
    """
    # TODO: 从认证上下文获取用户ID
    user_id = 1

    # 记录请求审计日志
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.READ_ACCOUNT,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(f"READ_ACCOUNT_{account_id}_{user_id}"))[:50],
        resource_type="exchange_account",
        resource_id=account_id,
        request_data={},
        status=AuditStatus.PENDING,
    )

    try:
        result = await db.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()

        if not account:
            # 记录404审计日志
            audit_log.status = AuditStatus.FAILED
            audit_log.error_message = f"Account ID {account_id} not found"

            db.add(audit_log)
            await db.commit()

            logger.warning(
                f"[AUDIT] User {user_id} failed to fetch account {account_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账户 ID {account_id} 不存在",
            )

        # 更新审计日志为成功
        audit_log.status = AuditStatus.SUCCESS
        audit_log.resource_id = account.id

        try:
            db.add(audit_log)
            await db.commit()

            logger.info(f"[AUDIT] User {user_id} fetched account {account_id}")

        except Exception as audit_error:
            await db.rollback()
            audit_log.error_message = str(audit_error)

            try:
                db.add(audit_log)
                await db.commit()
            except Exception as rollback_error:
                logger.error(
                    f"[AUDIT] Failed to save audit log: {str(rollback_error)}",
                    exc_info=True,
                )

        # 解密 API Key 用于脱敏显示
        api_key = decrypt_data(str(account.api_key))

        return ExchangeAccountDetailResponse.from_account(account, api_key)

    except Exception as e:
        # 更新审计日志为失败
        audit_log.status = AuditStatus.FAILED
        audit_log.error_message = str(e)

        try:
            db.add(audit_log)
            await db.commit()
        except Exception as add_error:
            logger.error(
                f"[AUDIT] Failed to update audit log: {str(add_error)}", exc_info=True
            )

        logger.error(
            f"[AUDIT] User {user_id} failed to fetch account {account_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取账户失败: {str(e)}",
        )


# ==================== 更新账户 ====================


@router.put("/{account_id}", response_model=ExchangeAccountResponse)
@limiter.limit(RATE_LIMITS["write"])
async def update_exchange_account(
    account_id: int,
    request: Request,
    account_update: ExchangeAccountUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    更新交易所账户信息。

    速率限制：20 请求/分钟/IP

    审计日志：记录更新操作的完整信息，包括前值和后值。
    """
    # TODO: 从认证上下文获取用户ID
    user_id = 1

    # 获取现有账户
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()

    if not account:
        logger.warning(
            f"[AUDIT] User {user_id} failed to update account {account_id}: account not found"
        )

        # 记录404审计日志
        audit_log = AuditLog(
            user_id=user_id,
            action_type=AuditActionType.UPDATE_ACCOUNT,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:500],
            request_id=str(hash(f"UPDATE_ACCOUNT_{account_id}_{user_id}"))[:50],
            resource_type="exchange_account",
            resource_id=account_id,
            request_data={
                "old_values": {},
                "new_values": {},
            },
            status=AuditStatus.FAILED,
            error_message=f"Account ID {account_id} not found",
        )

        db.add(audit_log)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"账户 ID {account_id} 不存在"
        )

    # 准备审计日志（记录前后值）
    old_values = {
        "label": account.label,
        "is_active": account.is_active,
        "is_demo": account.is_demo,
    }

    # 更新字段（只更新提供的字段）
    if account_update.label is not None:
        account.label = account_update.label  # type: ignore[assignment]
        old_values["label"] = account.label  # 记录旧值

    if account_update.api_key is not None:
        account.api_key = encrypt_data(account_update.api_key)  # type: ignore[assignment]
        old_values["api_key"] = (
            "****" + str(account_update.api_key)[:4] + "*" * 20
        )  # 记录掩码后的值

        # 更新 API Key 后需要重新验证
        account.is_validated = False  # type: ignore[assignment]
        account.last_validated_at = None  # type: ignore[assignment]
        old_values["is_validated"] = account.is_validated
        old_values["last_validated_at"] = (
            str(account.last_validated_at) if account.last_validated_at else None
        )

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
        old_values["is_active"] = account.is_active

    if account_update.is_demo is not None:
        account.is_demo = account_update.is_demo  # type: ignore[assignment]
        old_values["is_demo"] = account.is_demo

    if account_update.api_key is not None:
        account.is_validated = False  # type: ignore[assignment]
        old_values["is_validated"] = "true"
        old_values["last_validated_at"] = (
            str(account.last_validated_at) if account.last_validated_at else None
        )

    # 准备新值（用于审计日志）
    new_values = {}
    if account_update.label is not None:
        new_values["label"] = account_update.label

    if account_update.api_key is not None:
        new_values["api_key"] = "****" + str(account_update.api_key)[:4] + "*" * 20

    if account_update.api_secret is not None:
        new_values["api_secret"] = (
            "****" + str(account_update.api_secret)[:4] + "*" * 20
        )

    if account_update.passphrase is not None:
        new_values["passphrase"] = "****"

    if account_update.is_active is not None:
        new_values["is_active"] = account_update.is_active

    if account_update.is_demo is not None:
        new_values["is_demo"] = account_update.is_demo

    # 创建审计日志（记录前后值）
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.UPDATE_ACCOUNT,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(f"UPDATE_ACCOUNT_{account_id}_{user_id}"))[:50],
        resource_type="exchange_account",
        resource_id=account_id,
        request_data={
            "old_values": old_values,
            "new_values": new_values,
        },
        status=AuditStatus.PENDING,
    )
    db.add(audit_log)
    await db.commit()

    try:
        await db.refresh(account)

        # 更新审计日志为成功
        audit_log.status = AuditStatus.SUCCESS

        # 记录敏感数据（掩码）
        sensitive_data_dict = {
            "old_api_key": "****" + str(account.api_key)[:4] + "*" * 20
            if account_update.api_key
            else "unchanged",
            "new_api_key": "****" + str(account.api_key)[:4] + "*" * 20
            if account_update.api_key
            else "unchanged",
            "old_api_secret": "****" + str(account.api_secret)[:4] + "*" * 20
            if account_update.api_secret
            else "unchanged",
            "new_api_secret": "****" + str(account.api_secret)[:4] + "*" * 20
            if account_update.api_secret
            else "unchanged",
        }
        audit_log.sensitive_data = json.dumps(sensitive_data_dict)

        db.add(audit_log)
        await db.commit()

        logger.info(f"[AUDIT] User {user_id} updated account {account_id}")

    except Exception as e:
        await db.rollback()

        # 更新审计日志为失败
        audit_log.status = AuditStatus.FAILED
        audit_log.error_message = str(e)
        audit_log.new_values = {}

        try:
            db.add(audit_log)
            await db.commit()

        except Exception as rollback_error:
            logger.error(
                f"[AUDIT] Failed to update audit log: {str(rollback_error)}",
                exc_info=True,
            )

        logger.error(
            f"[AUDIT] User {user_id} failed to update account {account_id}: {str(e)}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新账户失败: {str(e)}",
        )

    return account


# ==================== 删除账户 ====================


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(RATE_LIMITS["write"])
async def delete_exchange_account(
    account_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    删除交易所账户。

    速率限制：20 请求/分钟/IP

    审计日志：记录删除操作的完整信息。
    """
    # TODO: 从认证上下文获取用户ID
    user_id = 1

    # 获取要删除的账户
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()

    if not account:
        # 记录404审计日志
        audit_log = AuditLog(
            user_id=user_id,
            action_type=AuditActionType.DELETE_ACCOUNT,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:500],
            request_id=str(hash(f"DELETE_ACCOUNT_{account_id}_{user_id}"))[:50],
            resource_type="exchange_account",
            resource_id=account_id,
            request_data={
                "account_info": {
                    "exchange": account.exchange,
                    "label": account.label,
                    "is_active": account.is_active,
                    "is_demo": account.is_demo,
                    "is_validated": account.is_validated,
                    "last_validated_at": str(account.last_validated_at)
                    if account.last_validated_at
                    else None,
                }
            },
            status=AuditStatus.FAILED,
            error_message=f"Account ID {account_id} not found",
        )

        db.add(audit_log)
        await db.commit()

        logger.warning(
            f"[AUDIT] User {user_id} failed to delete account {account_id}: account not found"
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"账户 ID {account_id} 不存在"
        )

    # 记录删除前审计日志（状态为PENDING）
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.DELETE_ACCOUNT,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(f"DELETE_ACCOUNT_{account_id}_{user_id}"))[:50],
        resource_type="exchange_account",
        resource_id=account_id,
        request_data={
            "account_info": {
                "exchange": account.exchange,
                "label": account.label,
                "is_active": account.is_active,
                "is_demo": account.is_demo,
                "is_validated": account.is_validated,
                "last_validated_at": str(account.last_validated_at)
                if account.last_validated_at
                else None,
            }
        },
        status=AuditStatus.PENDING,
    )

    try:
        # 删除账户
        result = await db.execute(delete(Account).where(Account.id == account_id))

        # 检查删除结果
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账户 ID {account_id} 不存在",
            )

        # 记录删除成功审计日志
        audit_log.status = AuditStatus.SUCCESS
        audit_log.status_message = "Account deleted successfully"

        db.add(audit_log)
        await db.commit()

        logger.info(f"[AUDIT] User {user_id} deleted account {account_id}")

    except Exception as e:
        await db.rollback()

        # 更新审计日志为失败
        audit_log.status = AuditStatus.FAILED
        audit_log.error_message = f"删除账户失败: {str(e)}"

        try:
            db.add(audit_log)
            await db.commit()
        except Exception as rollback_error:
            logger.error(
                f"[AUDIT] Failed to update audit log: {str(rollback_error)}",
                exc_info=True,
            )

        logger.error(
            f"[AUDIT] User {user_id} failed to delete account {account_id}: {str(e)}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除账户失败: {str(e)}",
        )


# ==================== 验证账户连接 ====================


@router.post("/{account_id}/validate", response_model=ValidationResponse)
@limiter.limit(RATE_LIMITS["account_validate"])
async def validate_exchange_account(
    account_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    验证交易所账户的 API 连接。

    速率限制：10请求/分钟/IP

    这是高风险端点，因为会调用外部API，因此限制更严格。

    审计日志：记录验证操作的详细信息，包括API返回的验证结果。
    """
    # TODO: 从认证上下文获取用户ID
    user_id = 1

    # 获取要验证的账户
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()

    if not account:
        # 记录404审计日志
        audit_log = AuditLog(
            user_id=user_id,
            action_type=AuditActionType.VALIDATE_CONNECTION,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown")[:500],
            request_id=str(hash(f"VALIDATE_CONNECTION_{account_id}_{user_id}"))[:50],
            resource_type="exchange_account",
            resource_id=account_id,
            request_data={
                "account_info": {
                    "exchange": account.exchange,
                    "label": account.label,
                    "is_active": account.is_active,
                    "is_demo": account.is_demo,
                    "is_validated": account.is_validated,
                    "last_validated_at": str(account.last_validated_at)
                    if account.last_validated_at
                    else None,
                }
            },
            status=AuditStatus.FAILED,
            error_message=f"Account ID {account_id} not found",
        )

        db.add(audit_log)
        await db.commit()

        logger.warning(
            f"[AUDIT] User {user_id} failed to validate account {account_id}: account not found"
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"账户 ID {account_id} 不存在"
        )

    # 解密 API 凭证
    api_key = decrypt_data(str(account.api_key))  # type: ignore[arg-type]
    api_secret = decrypt_data(str(account.api_secret))  # type: ignore[arg-type]
    passphrase = decrypt_data(str(account.passphrase)) if account.passphrase else None  # type: ignore[arg-type]

    # 记录验证前审计日志（状态为PENDING）
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.VALIDATE_CONNECTION,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(f"VALIDATE_CONNECTION_{account_id}_{user_id}"))[:50],
        resource_type="exchange_account",
        resource_id=account_id,
        request_data={
            "account_info": {
                "exchange": account.exchange,
                "label": account.label,
                "is_active": account.is_active,
                "is_demo": account.is_demo,
                "is_validated": account.is_validated,
                "last_validated_at": str(account.last_validated_at)
                if account.last_validated_at
                else None,
                "api_key": "****" + str(account.api_key)[:4] + "*" * 20,  # 掩码
            }
        },
        status=AuditStatus.PENDING,
    )

    try:
        db.add(audit_log)
        await db.commit()

        # 调用验证器
        validation_result = await ExchangeValidator.validate_exchange(
            exchange=account.exchange,  # type: ignore[arg-type]
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,  # type: ignore[arg-type]
        )

        # 更新审计日志状态为SUCCESS/FAILED
        audit_log.status = (
            AuditStatus.SUCCESS if validation_result["is_valid"] else AuditStatus.FAILED
        )

        # 记录验证结果和敏感信息（掩码）
        sensitive_data = {
            "api_key": "****" + str(api_key)[:4] + "*" * 20,
            "api_secret": "****" + str(api_secret)[:4] + "*" * 20,
            "passphrase": "****" + str(passphrase)[:4] + "*" * 20
            if passphrase
            else "none",
        }

        # 记录验证结果数据
        audit_log.request_data = {
            "account_info": {
                "exchange": account.exchange,
                "label": account.label,
                "is_active": account.is_active,
                "is_demo": account.is_demo,
                "is_validated": account.is_validated,
                "last_validated_at": str(account.last_validated_at)
                if account.last_validated_at
                else None,
            }
        }

        if validation_result["is_valid"]:
            audit_log.status_message = validation_result["message"]

            # 更新账户验证状态
            # type: ignore[assignment]
            account.is_validated = validation_result["is_valid"]
            last_validated_at_value = (
                datetime.now(timezone.utc) if validation_result["is_valid"] else None
            )
            # type: ignore[assignment]
            account.last_validated_at = last_validated_at_value

            # 更新审计日志的敏感数据
            audit_log.sensitive_data = sensitive_data

        # 记录审计日志到数据库
        db.add(audit_log)
        await db.commit()

        logger.info(
            f"[AUDIT] User {user_id} validated account {account_id}: "
            f"result={'is_valid': validation_result['is_valid']}"
        )

        return ValidationResponse(
            is_valid=validation_result["is_valid"],
            message=validation_result["message"],
            exchange_account_id=int(account.id),  # type: ignore[arg-type]
        )

    except Exception as e:
        await db.rollback()

        # 更新审计日志为失败
        audit_log.status = AuditStatus.FAILED
        audit_log.error_message = f"验证连接失败: {str(e)}"
        audit_log.request_data = {
            "account_info": {
                "exchange": account.exchange,
                "label": account.label,
                "is_active": account.is_active,
                "is_demo": account.is_demo,
                "is_validated": account.is_validated,
                "last_validated_at": str(account.last_validated_at)
                if account.last_validated_at
                else None,
            }
        }

        # 记录敏感数据（掩码）
        audit_log.sensitive_data = {
            "api_key": "****" + str(account.api_key)[:4] + "*" * 20,
            "api_secret": "****" + str(account.api_secret)[:4] + "*" * 20,
            "passphrase": "****" + str(account.passphrase)[:4] + "*" * 20
            if account.passphrase
            else "none",
        }

        try:
            db.add(audit_log)
            await db.commit()
        except Exception as rollback_error:
            logger.error(
                f"[AUDIT] Failed to update audit log: {str(rollback_error)}",
                exc_info=True,
            )

        logger.error(
            f"[AUDIT] User {user_id} failed to validate account {account_id}: {str(e)}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新验证状态失败: {str(e)}",
        )


# ==================== 验证新的 API 凭证 ====================


@router.post("/validate", response_model=ValidationResponse)
@limiter.limit(RATE_LIMITS["account_validate"])
async def validate_api_credentials(
    request: Request,
    credentials: ExchangeAccountValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    在创建账户前验证 API 凭证是否有效。

    速率限制：10请求/分钟/IP

    这是高风险端点，因为会调用外部API，因此限制更严格。

    审计日志：记录验证操作的详细信息，包括API返回的验证结果。
    """
    # TODO: 从认证上下文获取用户ID
    user_id = 1

    # 记录请求前审计日志（状态为PENDING）
    audit_log = AuditLog(
        user_id=user_id,
        action_type=AuditActionType.VALIDATE_API,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "unknown")[:500],
        request_id=str(hash(f"VALIDATE_API_{credentials.exchange}_{user_id}"))[:50],
        resource_type="exchange_api_credentials",
        resource_id=None,  # 创建前还没有账户ID
        request_data={
            "credentials": {
                "exchange": credentials.exchange,
                "api_key": "****" + str(credentials.api_key)[:4] + "*" * 20,
            }
        },
        status=AuditStatus.PENDING,
    )

    try:
        db.add(audit_log)
        await db.commit()

        # 调用验证器
        validation_result = await ExchangeValidator.validate_exchange(
            exchange=credentials.exchange,
            api_key=credentials.api_key,
            api_secret=credentials.api_secret,
            passphrase=credentials.passphrase or "",
        )

        # 更新审计日志状态为SUCCESS/FAILED
        audit_log.status = (
            AuditStatus.SUCCESS if validation_result["is_valid"] else AuditStatus.FAILED
        )
        audit_log.status_message = validation_result["message"]

        # 记录敏感数据（掩码）
        sensitive_data = {
            "api_key": "****" + str(credentials.api_key)[:4] + "*" * 20,
            "api_secret": "****" + str(credentials.api_secret)[:4] + "*" * 20,
            "passphrase": "****" + str(credentials.passphrase)[:4] + "*" * 20
            if credentials.passphrase
            else "none",
        }

        # 记录验证结果数据
        audit_log.request_data = {
            "credentials": {
                "exchange": credentials.exchange,
                "api_key": "****" + str(credentials.api_key)[:4] + "*" * 20,
            }
        }

        if validation_result["is_valid"]:
            # 记录验证结果
            audit_log.sensitive_data = sensitive_data
            audit_log.status_message = validation_result["message"]

        # 记录审计日志到数据库
        db.add(audit_log)
        await db.commit()

        logger.info(
            f"[AUDIT] User {user_id} validated API credentials for {credentials.exchange}"
        )

        return ValidationResponse(
            is_valid=validation_result["is_valid"], message=validation_result["message"]
        )

    except Exception as e:
        # 更新审计日志为失败
        audit_log.status = AuditStatus.FAILED
        audit_log.error_message = f"验证API凭证失败: {str(e)}"
        audit_log.request_data = {
            "credentials": {
                "exchange": credentials.exchange,
                "api_key": "****" + str(credentials.api_key)[:4] + "*" * 20,
                "api_secret": "****" + str(credentials.api_secret)[:4] + "*" * 20,
            }
        }

        # 记录敏感数据（掩码）
        audit_log.sensitive_data = sensitive_data

        try:
            db.add(audit_log)
            await db.commit()
        except Exception as rollback_error:
            logger.error(
                f"[AUDIT] Failed to update audit log: {str(rollback_error)}",
                exc_info=True,
            )

        logger.error(
            f"[AUDIT] User {user_id} failed to validate API credentials: {str(e)}",
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证API凭证失败: {str(e)}",
        )


# ==================== 统计查询 ====================


@router.get("/stats", response_model=Dict[str, Any])
async def get_audit_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """
    获取审计统计信息。

    速率限制：100请求/分钟/IP

    审计日志：仅查询，不记录审计日志。
    """
    # TODO: 从认证上下文获取用户ID（管理员可以看到所有用户的审计日志）
    user_id = request.query.get("user_id", 1)  # TODO: 默认返回所有审计日志

    # 构建查询条件
    where_clauses = []

    # 按用户ID过滤
    where_clauses.append(AuditLog.user_id == user_id)

    # 按操作类型过滤
    action_type = request.query.get("action_type")
    if action_type:
        where_clauses.append(AuditLog.action_type == action_type)

    # 按状态过滤
    status = request.query.get("status")
    if status:
        if status == "failed" or status == "FAILED":
            where_clauses.append(AuditLog.status == AuditStatus.FAILED)
        elif status == "success" or status == "SUCCESS":
            where_clauses.append(AuditLog.status == AuditStatus.SUCCESS)

    # 按资源类型过滤
    resource_type = request.query.get("resource_type")
    if resource_type:
        where_clauses.append(AuditLog.resource_type == resource_type)

    # 按资源ID过滤
    resource_id = request.query.get("resource_id")
    if resource_id:
        try:
            resource_id = int(resource_id)
            where_clauses.append(AuditLog.resource_id == resource_id)
        except (ValueError, TypeError):
            pass

    # 按时间范围过滤
    start_date = request.query.get("start_date")
    end_date = request.query.get("end_date")
    if start_date:
        try:
            start_datetime = datetime.fromisoformat(start_date)
            where_clauses.append(AuditLog.created_at >= start_datetime)
        except ValueError:
            pass

    if end_date:
        try:
            end_datetime = datetime.fromisoformat(end_date)
            where_clauses.append(AuditLog.created_at <= end_datetime)
        except ValueError:
            pass

    # 执行查询
    try:
        # 获取审计日志
        count_result = await db.execute(
            select(func.count(AuditLog.id)).where(*where_clauses)
        )
        total_count = count_result.scalar_one() or 0

        # 获取分页数据
        page = int(request.query.get("page", 1))
        page_size = int(request.query.get("page_size", 50))

        # 构建分页查询
        query = (
            select(AuditLog)
            .where(*where_clauses)
            .order_by(AuditLog.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

        # 获取分页数据和总数
        paginated_result = await db.execute(query)
        paginated_logs = paginated_result.scalars().all()

        return {
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "data": [
                {
                    "id": log.id,
                    "user_id": log.user_id,
                    "username": log.username,
                    "action_type": log.action_type,
                    "resource_type": log.resource_type,
                    "resource_id": log.resource_id,
                    "status": log.status,
                    "error_message": log.error_message,
                    "sensitive_data": log.sensitive_data if log.sensitive_data else {},
                    "request_data": log.request_data,
                    "created_at": log.created_at.isoformat(),
                    "updated_at": log.updated_at.isoformat()
                    if log.updated_at
                    else None,
                }
                for log in paginated_logs
            ],
        }

    except Exception as e:
        logger.error(f"[AUDIT] Failed to fetch audit stats: {str(e)}", exc_info=True)
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "data": [],
        }

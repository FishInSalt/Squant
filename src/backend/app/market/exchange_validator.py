"""
交易所连接验证模块

支持测试 Binance 和 OKX 的 API Key 有效性。
"""

import hmac
import hashlib
import time
import base64
import json
from typing import Dict, Any
import logging

from app.models.exchange_account import ExchangeType
from app.models.okx_api import (
    OKXBaseResponse,
    OKXBalanResponse,
    validate_okx_response,
    validate_okx_balance_data,
)
from app.core.http_client import get_with_retry

logger = logging.getLogger(__name__)


class ExchangeValidator:
    """交易所验证器"""

    @staticmethod
    async def validate_binance(
        api_key: str, api_secret: str, passphrase: str = ""
    ) -> Dict[str, Any]:
        """
        验证 Binance API Key 有效性。

        使用全局 HTTP 客户端（带连接池和重试机制）。

        Args:
            api_key: Binance API Key
            api_secret: Binance API Secret

        Returns:
            Dict: {
                'is_valid': bool,
                'message': str,
                'account_type': Optional[str]
            }
        """
        try:
            logger.info("Validating Binance API Key")

            # Binance 获取账户信息的 API
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"

            # 生成签名
            signature = hmac.new(
                api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            # 发送请求
            headers = {"X-MBX-APIKEY": api_key}
            params: Dict[str, str] = {
                "timestamp": str(timestamp),
                "signature": signature,
            }

            response = await get_with_retry(
                "https://api.binance.com/api/v3/account",
                headers=headers,
                params=params,
            )

            if response.status_code == 200:
                logger.info("Binance API Key validated successfully")
                return {
                    "is_valid": True,
                    "message": "Binance API Key 验证成功",
                    "data": response.json(),
                }
            elif response.status_code == 401:
                logger.warning("Binance API Key validation failed: invalid key")
                return {"is_valid": False, "message": "Binance API Key 无效或已过期"}
            else:
                logger.warning(f"Binance API validation failed: {response.status_code}")
                return {
                    "is_valid": False,
                    "message": f"Binance API 返回错误: {response.status_code} - {response.text}",
                }

        except Exception as e:
            logger.error(f"Binance API validation exception: {str(e)}", exc_info=True)
            return {"is_valid": False, "message": f"Binance API 验证失败: {str(e)}"}

    @staticmethod
    async def validate_okx(
        api_key: str, api_secret: str, passphrase: str = ""
    ) -> Dict[str, Any]:
        """
        验证 OKX API Key 有效性。

        使用全局 HTTP 客户端（带连接池和重试机制）。
        使用 Pydantic 模型验证 API 响应。

        Args:
            api_key: OKX API Key
            api_secret: OKX API Secret
            passphrase: OKX API Passphrase（必需）

        Returns:
            Dict: {
                'is_valid': bool,
                'message': str
            }
        """
        try:
            if not passphrase:
                logger.warning("OKX validation failed: passphrase required")
                return {"is_valid": False, "message": "OKX 需要 API Passphrase"}

            logger.info("Validating OKX API Key")

            # OKX 获取账户余额的 API
            timestamp = time.time()
            timestamp_str = f"{timestamp:.0f}"

            # 准备请求体
            body = ""
            body_str = json.dumps(body)

            # 签名
            sign_str = timestamp_str + "GET" + "/api/v5/account/balance" + body_str
            sign = base64.b64encode(
                hmac.new(
                    api_secret.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256
                ).digest()
            ).decode()

            # 发送请求
            headers = {
                "OK-ACCESS-KEY": api_key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": timestamp_str,
                "OK-ACCESS-PASSPHRASE": passphrase,
                "Content-Type": "application/json",
            }

            response = await get_with_retry(
                "https://www.okx.com/api/v5/account/balance",
                headers=headers,
            )

            if response.status_code == 200:
                # 验证JSON格式
                try:
                    response_data = response.json()
                except Exception as e:
                    logger.error(
                        f"OKX API JSON parsing failed: {str(e)}", exc_info=True
                    )
                    return {"is_valid": False, "message": "OKX API JSON 解析失败"}

                # 验证OKX API响应结构
                try:
                    validated_response = validate_okx_response(
                        response_data, expected_fields=["code", "msg", "data"]
                    )
                except ValueError as e:
                    logger.error(
                        f"OKX API response validation failed: {str(e)}", exc_info=True
                    )
                    return {
                        "is_valid": False,
                        "message": f"OKX API 响应格式无效: {str(e)}",
                    }

                # 检查响应码
                if not validated_response.is_success():
                    msg = validated_response.get_error_message()
                    logger.warning(f"OKX API validation failed: {msg}")
                    return {"is_valid": False, "message": msg}

                # 验证余额数据
                try:
                    balance_data = validated_response.data

                    if isinstance(balance_data, list):
                        # 验证每个余额项
                        for i, balance in enumerate(balance_data):
                            validate_okx_balance_data(balance)

                        logger.info(
                            "OKX API Key validated successfully with balance data"
                        )
                        return {
                            "is_valid": True,
                            "message": "OKX API Key 验证成功",
                            "data": response_data,
                        }
                    else:
                        logger.warning(
                            f"OKX API data type invalid: {type(balance_data)}"
                        )
                        return {
                            "is_valid": False,
                            "message": "OKX API 返回数据格式无效",
                        }

                except ValueError as e:
                    logger.error(
                        f"OKX API balance data validation failed: {str(e)}",
                        exc_info=True,
                    )
                    return {
                        "is_valid": False,
                        "message": f"OKX API 余额数据验证失败: {str(e)}",
                    }

            elif response.status_code == 401:
                logger.warning("OKX API Key validation failed: invalid key")
                return {"is_valid": False, "message": "OKX API Key 无效或已过期"}
            else:
                logger.warning(f"OKX API validation failed: {response.status_code}")
                return {
                    "is_valid": False,
                    "message": f"OKX API 返回错误: {response.status_code}",
                }

        except Exception as e:
            logger.error(f"OKX API validation exception: {str(e)}", exc_info=True)
            return {"is_valid": False, "message": f"OKX API 验证失败: {str(e)}"}

    @staticmethod
    async def validate_exchange(
        exchange: ExchangeType, api_key: str, api_secret: str, passphrase: str = ""
    ) -> Dict[str, Any]:
        """
        验证交易所连接（统一入口）。

        Args:
            exchange: 交易所类型
            api_key: API Key
            api_secret: API Secret
            passphrase: API Passphrase（可选）

        Returns:
            Dict: 验证结果
        """
        if exchange == ExchangeType.BINANCE:
            return await ExchangeValidator.validate_binance(
                api_key, api_secret, passphrase or ""
            )
        elif exchange == ExchangeType.OKX:
            passphrase_okx = passphrase if passphrase else ""
            return await ExchangeValidator.validate_okx(
                api_key, api_secret, passphrase_okx
            )
        elif exchange == ExchangeType.HUOBI:
            # TODO: 实现火币验证
            return {"is_valid": False, "message": "火币验证功能待实现"}
        else:
            return {"is_valid": False, "message": f"不支持的交易所类型: {exchange}"}

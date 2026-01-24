"""
交易所连接验证模块

支持测试 Binance 和 OKX 的 API Key 有效性。
"""
import hmac
import hashlib
import time
import base64
import json
import httpx
from typing import Dict, Any

from app.models.exchange_account import ExchangeType


class ExchangeValidator:
    """交易所验证器"""

    @staticmethod
    async def validate_binance(api_key: str, api_secret: str, passphrase: str = "") -> Dict[str, Any]:
        """
        验证 Binance API Key 有效性。

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
            async with httpx.AsyncClient() as client:
                # Binance 获取账户信息的 API
                timestamp = int(time.time() * 1000)
                query_string = f"timestamp={timestamp}"

                # 生成签名
                signature = hmac.new(
                    api_secret.encode('utf-8'),
                    query_string.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()

                # 发送请求
                headers = {
                    "X-MBX-APIKEY": api_key
                }
                params: Dict[str, str] = {
                    "timestamp": str(timestamp),
                    "signature": signature
                }

                response = await client.get(
                    "https://api.binance.com/api/v3/account",
                    headers=headers,
                    params=params,
                    timeout=10.0
                )

                if response.status_code == 200:
                    return {
                        'is_valid': True,
                        'message': 'Binance API Key 验证成功',
                        'data': response.json()
                    }
                elif response.status_code == 401:
                    return {
                        'is_valid': False,
                        'message': 'Binance API Key 无效或已过期'
                    }
                else:
                    return {
                        'is_valid': False,
                        'message': f'Binance API 返回错误: {response.status_code} - {response.text}'
                    }

        except httpx.TimeoutException:
            return {
                'is_valid': False,
                'message': 'Binance API 连接超时'
            }
        except Exception as e:
            return {
                'is_valid': False,
                'message': f'Binance API 验证失败: {str(e)}'
            }

    @staticmethod
    async def validate_okx(api_key: str, api_secret: str, passphrase: str = "") -> Dict[str, Any]:
        """
        验证 OKX API Key 有效性。

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
                return {
                    'is_valid': False,
                    'message': 'OKX 需要 API Passphrase'
                }

            async with httpx.AsyncClient() as client:
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
                        api_secret.encode('utf-8'),
                        sign_str.encode('utf-8'),
                        hashlib.sha256
                    ).digest()
                ).decode()

                # 发送请求
                headers = {
                    "OK-ACCESS-KEY": api_key,
                    "OK-ACCESS-SIGN": sign,
                    "OK-ACCESS-TIMESTAMP": timestamp_str,
                    "OK-ACCESS-PASSPHRASE": passphrase,
                    "Content-Type": "application/json"
                }

                response = await client.get(
                    "https://www.okx.com/api/v5/account/balance",
                    headers=headers,
                    timeout=10.0
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == '0':
                        return {
                            'is_valid': True,
                            'message': 'OKX API Key 验证成功',
                            'data': result
                        }
                    else:
                        return {
                            'is_valid': False,
                            'message': f'OKX API 错误: {result.get("msg", "未知错误")}'
                        }
                elif response.status_code == 401:
                    return {
                        'is_valid': False,
                        'message': 'OKX API Key 无效或已过期'
                    }
                else:
                    return {
                        'is_valid': False,
                        'message': f'OKX API 返回错误: {response.status_code}'
                    }

        except httpx.TimeoutException:
            return {
                'is_valid': False,
                'message': 'OKX API 连接超时'
            }
        except Exception as e:
            return {
                'is_valid': False,
                'message': f'OKX API 验证失败: {str(e)}'
            }

    @staticmethod
    async def validate_exchange(
        exchange: ExchangeType,
        api_key: str,
        api_secret: str,
        passphrase: str = ""
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
            return await ExchangeValidator.validate_binance(api_key, api_secret, passphrase or "")
        elif exchange == ExchangeType.OKX:
            passphrase_okx = passphrase if passphrase else ""
            return await ExchangeValidator.validate_okx(api_key, api_secret, passphrase_okx)
        elif exchange == ExchangeType.HUOBI:
            # TODO: 实现火币验证
            return {
                'is_valid': False,
                'message': '火币验证功能待实现'
            }
        else:
            return {
                'is_valid': False,
                'message': f'不支持的交易所类型: {exchange}'
            }

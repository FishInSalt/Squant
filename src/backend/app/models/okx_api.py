"""
OKX API 响应模型

使用 Pydantic 验证 OKX API 返回的数据结构。
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Any, Union
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ========== OKX API 基础响应模型 ==========


class OKXBaseResponse(BaseModel):
    """OKX API 基础响应"""

    code: str = Field(..., description="响应码")
    msg: str = Field("", description="响应消息")
    data: Any = Field(None, description="响应数据")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        """验证code字段"""
        if v is None:
            raise ValueError("OKX API response missing 'code' field")
        return str(v)

    def is_success(self) -> bool:
        """检查响应是否成功"""
        return self.code == "0"

    def get_error_message(self) -> str:
        """获取错误消息"""
        if self.is_success():
            return "Success"
        return self.msg or f"OKX API error code: {self.code}"


class OKXErrorResponse(BaseModel):
    """OKX API 错误响应"""

    code: str
    msg: str
    data: Optional[Any] = None


# ========== Ticker 相关模型 ==========


class OKXTicker(BaseModel):
    """OKX Ticker 数据"""

    instId: str = Field(..., alias="instId", description="交易对ID")
    last: str = Field(..., description="最新成交价")
    lastSz: str = Field(..., description="最新成交的数量")
    askPx: str = Field(..., description="卖一价")
    askSz: str = Field(..., description="卖一的数量")
    bidPx: str = Field(..., description="买一价")
    bidSz: str = Field(..., description="买一的数量")
    open24h: str = Field(..., description="24小时开盘价")
    high24h: str = Field(..., description="24小时最高价")
    low24h: str = Field(..., description="24小时最低价")
    volCcy24h: str = Field(..., description="24小时成交量，以交易货币计")
    vol24h: str = Field(..., description="24小时成交量，以计价货币计")
    ts: str = Field(..., description="数据产生时间戳")

    @field_validator("last", "askPx", "bidPx", "open24h", "high24h", "low24h")
    @classmethod
    def validate_price_fields(cls, v: str) -> str:
        """验证价格字段"""
        if not v:
            raise ValueError("Price field cannot be empty")
        # 尝试转换为浮点数验证
        try:
            float(v)
        except ValueError:
            raise ValueError(f"Invalid price value: {v}")
        return v

    @field_validator("volCcy24h", "vol24h", "lastSz", "askSz", "bidSz")
    @classmethod
    def validate_volume_fields(cls, v: str) -> str:
        """验证成交量字段"""
        if not v:
            raise ValueError("Volume field cannot be empty")
        return v

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """验证时间戳"""
        if not v:
            raise ValueError("Timestamp cannot be empty")
        try:
            int(v)
        except ValueError:
            raise ValueError(f"Invalid timestamp: {v}")
        return v


class OKXTickersResponse(OKXBaseResponse):
    """OKX Tickers 响应"""

    data: List[OKXTicker] = Field(default_factory=list, description="Ticker列表")

    @field_validator("data", mode="before")
    @classmethod
    def validate_data(cls, v: Any) -> List[OKXTicker]:
        """验证data字段"""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError(f"Expected 'data' to be a list, got {type(v).__name__}")
        return v


# ========== K线相关模型 ==========


class OKXKline(BaseModel):
    """OKX K线数据（单个）"""

    timestamp: str = Field(..., description="时间戳")
    open_price: str = Field(..., alias="0", description="开盘价")
    high_price: str = Field(..., alias="1", description="最高价")
    low_price: str = Field(..., alias="2", description="最低价")
    close_price: str = Field(..., alias="3", description="收盘价")
    volume: str = Field(..., alias="4", description="成交量（以张为单位）")
    volCcy: str = Field(..., alias="5", description="成交量（以币为单位）")
    volCcyQuote: str = Field(..., alias="6", description="成交量（以计价货币为单位）")
    confirm: Optional[str] = Field(None, alias="7", description="K线状态")

    @field_validator("timestamp", "0", "1", "2", "3")
    @classmethod
    def validate_numeric_fields(cls, v: str) -> str:
        """验证数值字段"""
        if not v:
            raise ValueError("Numeric field cannot be empty")
        try:
            float(v)
        except ValueError:
            raise ValueError(f"Invalid numeric value: {v}")
        return v

    @field_validator("4", "5", "6")
    @classmethod
    def validate_volume_fields(cls, v: str) -> str:
        """验证成交量字段"""
        if not v:
            raise ValueError("Volume field cannot be empty")
        return v


class OKXKlinesResponse(OKXBaseResponse):
    """OKX Klines 响应"""

    data: List[List[Any]] = Field(default_factory=list, description="K线数据列表")

    @field_validator("data", mode="before")
    @classmethod
    def validate_data(cls, v: Any) -> List[List[Any]]:
        """验证data字段"""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError(f"Expected 'data' to be a list, got {type(v).__name__}")

        # 验证每个K线数据
        validated_klines = []
        for i, kline in enumerate(v):
            if not isinstance(kline, list):
                raise ValueError(f"Kline at index {i} is not a list")
            if len(kline) < 6:
                raise ValueError(
                    f"Kline at index {i} has invalid length: {len(kline)} (expected at least 6)"
                )

            validated_klines.append(kline)

        return validated_klines


# ========== 账户相关模型 ==========


class OKXBalance(BaseModel):
    """OKX 账户余额（单个）"""

    ccy: str = Field(..., description="币种")
    bal: str = Field(..., description="余额")
    frozenBal: str = Field(..., description="冻结余额")
    availBal: str = Field(..., description="可用余额")


class OKXBalanResponse(OKXBaseResponse):
    """OKX 账户余额响应"""

    data: List[OKXBalance] = Field(default_factory=list, description="余额列表")

    @field_validator("data", mode="before")
    @classmethod
    def validate_data(cls, v: Any) -> List[OKXBalance]:
        """验证data字段"""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError(f"Expected 'data' to be a list, got {type(v).__name__}")
        return v


# ========== 验证工具函数 ==========


def validate_okx_response(
    response_data: Any, expected_fields: Optional[List[str]] = None
) -> OKXBaseResponse:
    """
    验证 OKX API 响应数据

    Args:
        response_data: 原始响应数据
        expected_fields: 期望的字段列表

    Returns:
        OKXBaseResponse: 验证后的响应对象

    Raises:
        ValueError: 如果数据格式无效
    """
    # 验证基础结构
    if not isinstance(response_data, dict):
        raise ValueError(
            f"Expected OKX API response to be a dict, got {type(response_data).__name__}"
        )

    # 验证必需字段
    if "code" not in response_data:
        raise ValueError("OKX API response missing 'code' field")

    # 尝试解析为Pydantic模型
    try:
        response = OKXBaseResponse(**response_data)
    except Exception as e:
        raise ValueError(f"Failed to validate OKX API response: {str(e)}") from e

    # 验证期望的字段
    if expected_fields:
        for field in expected_fields:
            if field not in response_data:
                raise ValueError(f"OKX API response missing required field: {field}")

    return response


def validate_okx_ticker_data(ticker_data: Any) -> OKXTicker:
    """
    验证 OKX Ticker 数据

    Args:
        ticker_data: 原始ticker数据

    Returns:
        OKXTicker: 验证后的ticker对象

    Raises:
        ValueError: 如果数据格式无效
    """
    if not isinstance(ticker_data, dict):
        raise ValueError(
            f"Expected ticker data to be a dict, got {type(ticker_data).__name__}"
        )

    if "instId" not in ticker_data:
        raise ValueError("Ticker data missing required field: instId")

    try:
        return OKXTicker(**ticker_data)
    except Exception as e:
        raise ValueError(f"Failed to validate ticker data: {str(e)}") from e


def validate_okx_kline_data(kline_data: Any) -> OKXKline:
    """
    验证 OKX Kline 数据

    Args:
        kline_data: 原始kline数据（列表或字典）

    Returns:
        OKXKline: 验证后的kline对象

    Raises:
        ValueError: 如果数据格式无效
    """
    # OKX返回的K线是列表格式
    if isinstance(kline_data, list):
        if len(kline_data) < 6:
            raise ValueError(
                f"Kline data has invalid length: {len(kline_data)} (expected at least 6)"
            )

        # 转换为字典格式以供Pydantic验证
        data_dict = {
            "0": str(kline_data[0]),  # timestamp
            "1": str(kline_data[1]),  # open
            "2": str(kline_data[2]),  # high
            "3": str(kline_data[3]),  # low
            "4": str(kline_data[4]),  # close
            "5": str(kline_data[5]),  # volume
        }

        if len(kline_data) > 6:
            data_dict["6"] = str(kline_data[6])  # volCcy
        if len(kline_data) > 7:
            data_dict["7"] = str(kline_data[7])  # confirm

        try:
            return OKXKline(**data_dict)
        except Exception as e:
            raise ValueError(f"Failed to validate kline data: {str(e)}") from e

    elif isinstance(kline_data, dict):
        # 如果是字典格式，转换为列表格式
        timestamp = kline_data.get("timestamp") or kline_data.get("0")
        open_price = kline_data.get("open_price") or kline_data.get("1")
        high_price = kline_data.get("high_price") or kline_data.get("2")
        low_price = kline_data.get("low_price") or kline_data.get("3")
        close_price = kline_data.get("close_price") or kline_data.get("4")
        volume = kline_data.get("volume") or kline_data.get("5")

        data_list = [
            timestamp or "0",
            open_price or "0",
            high_price or "0",
            low_price or "0",
            close_price or "0",
            volume or "0",
        ]

        if kline_data.get("volCcy") or kline_data.get("6"):
            data_list.append(str(kline_data.get("volCcy") or kline_data.get("6")))
        if kline_data.get("confirm") or kline_data.get("7"):
            data_list.append(str(kline_data.get("confirm") or kline_data.get("7")))

        return validate_okx_kline_data(data_list)
    else:
        raise ValueError(
            f"Expected kline data to be a list or dict, got {type(kline_data).__name__}"
        )


def validate_okx_balance_data(balance_data: Any) -> OKXBalance:
    """
    验证 OKX 余额数据

    Args:
        balance_data: 原始余额数据

    Returns:
        OKXBalance: 验证后的余额对象

    Raises:
        ValueError: 如果数据格式无效
    """
    if not isinstance(balance_data, dict):
        raise ValueError(
            f"Expected balance data to be a dict, got {type(balance_data).__name__}"
        )

    if "ccy" not in balance_data:
        raise ValueError("Balance data missing required field: ccy")

    try:
        return OKXBalance(**balance_data)
    except Exception as e:
        raise ValueError(f"Failed to validate balance data: {str(e)}") from e


# ========== 导出 ==========

__all__ = [
    # 基础模型
    "OKXBaseResponse",
    "OKXErrorResponse",
    # Ticker 模型
    "OKXTicker",
    "OKXTickersResponse",
    # K线模型
    "OKXKline",
    "OKXKlinesResponse",
    # 账户模型
    "OKXBalance",
    "OKXBalanResponse",
    # 验证函数
    "validate_okx_response",
    "validate_okx_ticker_data",
    "validate_okx_kline_data",
    "validate_okx_balance_data",
]

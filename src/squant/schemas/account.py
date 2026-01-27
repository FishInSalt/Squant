"""Pydantic schemas for exchange account API requests and responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class CreateExchangeAccountRequest(BaseModel):
    """Request to create a new exchange account configuration."""

    exchange: Literal["okx", "binance"] = Field(
        ..., description="Exchange identifier (okx or binance)"
    )
    name: str = Field(
        ..., min_length=1, max_length=64, description="Unique account name"
    )
    api_key: SecretStr = Field(..., description="Exchange API key")
    api_secret: SecretStr = Field(..., description="Exchange API secret")
    passphrase: SecretStr | None = Field(
        None, description="API passphrase (required for OKX)"
    )
    testnet: bool = Field(False, description="Whether to use testnet/sandbox mode")


class UpdateExchangeAccountRequest(BaseModel):
    """Request to update an existing exchange account configuration."""

    name: str | None = Field(
        None, min_length=1, max_length=64, description="New account name"
    )
    api_key: SecretStr | None = Field(None, description="New API key")
    api_secret: SecretStr | None = Field(None, description="New API secret")
    passphrase: SecretStr | None = Field(None, description="New passphrase")
    testnet: bool | None = Field(None, description="Whether to use testnet/sandbox")
    is_active: bool | None = Field(None, description="Whether the account is active")


class ExchangeAccountResponse(BaseModel):
    """Exchange account details response.

    Note: Credentials are never returned in the response for security.
    """

    id: UUID
    exchange: str
    name: str
    testnet: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExchangeAccountListItem(BaseModel):
    """Exchange account item for list response."""

    id: UUID
    exchange: str
    name: str
    testnet: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResponse(BaseModel):
    """Response for exchange connection test."""

    success: bool = Field(..., description="Whether the connection test succeeded")
    message: str | None = Field(None, description="Error message if failed")
    balance_count: int | None = Field(
        None, description="Number of currencies with balance (if successful)"
    )

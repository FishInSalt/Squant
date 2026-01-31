"""Pydantic schemas for strategy API requests and responses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from squant.models.enums import StrategyStatus


class CreateStrategyRequest(BaseModel):
    """Request to create a new strategy."""

    name: str = Field(..., min_length=1, max_length=128, description="Strategy name")
    code: str = Field(..., min_length=1, description="Strategy Python code")
    description: str | None = Field(None, max_length=1000, description="Strategy description")
    params_schema: dict[str, Any] | None = Field(
        None, description="JSON Schema for strategy parameters"
    )
    default_params: dict[str, Any] | None = Field(None, description="Default parameter values")


class UpdateStrategyRequest(BaseModel):
    """Request to update an existing strategy."""

    name: str | None = Field(None, min_length=1, max_length=128, description="New name")
    code: str | None = Field(None, min_length=1, description="Updated code")
    description: str | None = Field(None, max_length=1000, description="Updated description")
    params_schema: dict[str, Any] | None = Field(None, description="Updated params schema")
    default_params: dict[str, Any] | None = Field(None, description="Updated default params")
    status: StrategyStatus | None = Field(None, description="Strategy status")


class ValidateCodeRequest(BaseModel):
    """Request to validate strategy code."""

    code: str = Field(..., min_length=1, description="Strategy code to validate")


class ValidationResultResponse(BaseModel):
    """Response for code validation."""

    valid: bool = Field(..., description="Whether the code is valid")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")


class StrategyResponse(BaseModel):
    """Strategy details response."""

    id: UUID
    name: str
    version: str
    description: str | None
    code: str
    params_schema: dict[str, Any]
    default_params: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyListItem(BaseModel):
    """Strategy item for list response (without code)."""

    id: UUID
    name: str
    version: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

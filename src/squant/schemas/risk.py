"""Pydantic schemas for risk rule API requests and responses."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from squant.models.enums import RiskRuleType


class CreateRiskRuleRequest(BaseModel):
    """Request to create a new risk rule."""

    name: str = Field(..., min_length=1, max_length=64, description="Rule name")
    description: str | None = Field(None, max_length=500, description="Rule description")
    type: RiskRuleType = Field(..., description="Risk rule type")
    params: dict[str, Any] = Field(..., description="Rule parameters")
    enabled: bool = Field(True, description="Whether the rule is enabled")


class UpdateRiskRuleRequest(BaseModel):
    """Request to update an existing risk rule."""

    name: str | None = Field(None, min_length=1, max_length=64, description="New name")
    description: str | None = Field(None, max_length=500, description="Rule description")
    type: RiskRuleType | None = Field(None, description="New rule type")
    params: dict[str, Any] | None = Field(None, description="Updated parameters")
    enabled: bool | None = Field(None, description="Enable/disable the rule")


class ToggleRiskRuleRequest(BaseModel):
    """Request to toggle a risk rule's enabled status."""

    enabled: bool = Field(..., description="New enabled status")


class RiskRuleResponse(BaseModel):
    """Risk rule details response."""

    id: UUID
    name: str
    description: str | None = None
    type: str
    params: dict[str, Any]
    enabled: bool
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RiskRuleListItem(BaseModel):
    """Risk rule item for list response."""

    id: UUID
    name: str
    type: str
    enabled: bool
    last_triggered_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

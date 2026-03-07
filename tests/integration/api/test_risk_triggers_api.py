"""Integration tests for Risk Triggers API endpoints.

Tests the RSK-008 acceptance criteria for risk trigger audit records.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
class TestListRiskTriggers:
    """Test listing risk trigger records (RSK-008)."""

    async def test_list_risk_triggers_with_pagination(self, client):
        """Test RSK-008-1: List risk triggers with pagination."""
        # Create mock triggers
        triggers = []
        for i in range(3):
            trigger = MagicMock()
            trigger.id = uuid4()
            trigger.time = datetime.now(UTC) - timedelta(hours=i)
            trigger.rule_id = uuid4()
            trigger.run_id = uuid4()
            trigger.trigger_type = "daily_loss_limit"
            trigger.details = {"rule_type": "daily_loss_limit", "reason": "test"}
            trigger.rule = None
            trigger.run = None
            triggers.append(trigger)

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=(triggers, 3),
        ):
            response = await client.get("/api/v1/risk-triggers?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()

        # Check ApiResponse wrapper
        assert "data" in data
        result = data["data"]

        # Check pagination metadata
        assert result["total"] == 3
        assert result["page"] == 1
        assert result["page_size"] == 10

        # Check trigger data
        assert len(result["items"]) == 3
        for item in result["items"]:
            assert "id" in item
            assert "time" in item
            assert "rule_id" in item
            assert "run_id" in item
            assert item["trigger_type"] == "daily_loss_limit"

    async def test_list_risk_triggers_second_page(self, client):
        """Test RSK-008-1: Second page of risk triggers."""
        trigger = MagicMock()
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC)
        trigger.rule_id = uuid4()
        trigger.run_id = None
        trigger.trigger_type = "position_limit"
        trigger.details = {"rule_type": "position_limit", "reason": "test"}
        trigger.rule = None
        trigger.run = None

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([trigger], 21),
        ):
            response = await client.get("/api/v1/risk-triggers?page=2&page_size=20")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 21
        assert result["page"] == 2
        assert result["page_size"] == 20
        assert len(result["items"]) == 1

    async def test_list_risk_triggers_empty(self, client):
        """Test RSK-008-1: Empty list of risk triggers."""
        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            response = await client.get("/api/v1/risk-triggers")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 0
        assert result["page"] == 1
        assert len(result["items"]) == 0

    async def test_filter_triggers_by_time_range(self, client):
        """Test RSK-008-2: Filter triggers by time range."""
        from urllib.parse import quote

        start_time = datetime.now(UTC) - timedelta(days=7)
        end_time = datetime.now(UTC)

        trigger = MagicMock()
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC) - timedelta(days=3)
        trigger.rule_id = uuid4()
        trigger.run_id = uuid4()
        trigger.trigger_type = "order_limit"
        trigger.details = {"rule_type": "order_limit", "reason": "test"}
        trigger.rule = None
        trigger.run = None

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([trigger], 1),
        ) as mock_list:
            # URL encode the datetime strings
            start_str = quote(start_time.isoformat())
            end_str = quote(end_time.isoformat())
            response = await client.get(
                f"/api/v1/risk-triggers?start_time={start_str}&end_time={end_str}"
            )

            # Verify service was called with time filters
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["start_time"] is not None
            assert call_kwargs["end_time"] is not None

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 1
        assert len(result["items"]) == 1

    async def test_filter_triggers_by_rule_id(self, client):
        """Test RSK-008-3: Filter triggers by rule ID."""
        rule_id = uuid4()

        triggers = []
        for i in range(2):
            trigger = MagicMock()
            trigger.id = uuid4()
            trigger.time = datetime.now(UTC) - timedelta(hours=i)
            trigger.rule_id = rule_id
            trigger.run_id = uuid4()
            trigger.trigger_type = "daily_loss_limit"
            trigger.details = {"rule_type": "daily_loss_limit", "reason": "test"}
            trigger.rule = None
            trigger.run = None
            triggers.append(trigger)

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=(triggers, 2),
        ) as mock_list:
            response = await client.get(f"/api/v1/risk-triggers?rule_id={rule_id}")

            # Verify service was called with rule_id filter
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["rule_id"] == rule_id

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 2
        assert len(result["items"]) == 2

        # All triggers should have the same rule_id
        for item in result["items"]:
            assert item["rule_id"] == str(rule_id)

    async def test_filter_triggers_by_run_id(self, client):
        """Test RSK-008-3: Filter triggers by run ID."""
        run_id = uuid4()

        trigger = MagicMock()
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC)
        trigger.rule_id = uuid4()
        trigger.run_id = run_id
        trigger.trigger_type = "position_limit"
        trigger.details = {"rule_type": "position_limit", "reason": "test"}
        trigger.rule = None
        trigger.run = None

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([trigger], 1),
        ) as mock_list:
            response = await client.get(f"/api/v1/risk-triggers?run_id={run_id}")

            # Verify service was called with run_id filter
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["run_id"] == run_id

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["run_id"] == str(run_id)

    async def test_triggers_with_multiple_filters(self, client):
        """Test RSK-008-3: Filter triggers by multiple criteria."""
        from urllib.parse import quote

        rule_id = uuid4()
        run_id = uuid4()
        start_time = datetime.now(UTC) - timedelta(days=1)
        end_time = datetime.now(UTC)

        trigger = MagicMock()
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC) - timedelta(hours=6)
        trigger.rule_id = rule_id
        trigger.run_id = run_id
        trigger.trigger_type = "total_loss_limit"
        trigger.details = {"rule_type": "total_loss_limit", "reason": "test"}
        trigger.rule = None
        trigger.run = None

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([trigger], 1),
        ) as mock_list:
            # URL encode the datetime strings
            start_str = quote(start_time.isoformat())
            end_str = quote(end_time.isoformat())
            response = await client.get(
                f"/api/v1/risk-triggers?rule_id={rule_id}&run_id={run_id}"
                f"&start_time={start_str}&end_time={end_str}"
            )

            # Verify all filters were passed
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["rule_id"] == rule_id
            assert call_kwargs["run_id"] == run_id
            assert call_kwargs["start_time"] is not None
            assert call_kwargs["end_time"] is not None

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 1

    async def test_triggers_with_different_types(self, client):
        """Test RSK-008-4: Show different trigger types."""
        triggers = []
        trigger_types = [
            "order_limit",
            "position_limit",
            "daily_loss_limit",
            "total_loss_limit",
            "frequency_limit",
            "volatility_break",
        ]

        for i, trigger_type in enumerate(trigger_types):
            trigger = MagicMock()
            trigger.id = uuid4()
            trigger.time = datetime.now(UTC) - timedelta(hours=i)
            trigger.rule_id = uuid4()
            trigger.run_id = uuid4()
            trigger.trigger_type = trigger_type
            trigger.details = {"rule_type": trigger_type, "reason": "test"}
            trigger.rule = None
            trigger.run = None
            triggers.append(trigger)

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=(triggers, len(triggers)),
        ):
            response = await client.get("/api/v1/risk-triggers?page_size=50")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == len(trigger_types)
        assert len(result["items"]) == len(trigger_types)

        # Verify all trigger types are present
        returned_types = {item["trigger_type"] for item in result["items"]}
        assert returned_types == set(trigger_types)

    async def test_triggers_without_rule_id(self, client):
        """Test RSK-008-4: Triggers without associated rule (manual triggers)."""
        trigger = MagicMock()
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC)
        trigger.rule_id = None  # Manual trigger without rule
        trigger.run_id = uuid4()
        trigger.trigger_type = "circuit_breaker"
        trigger.details = {"rule_type": "circuit_breaker", "reason": "test"}
        trigger.rule = None
        trigger.run = None

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([trigger], 1),
        ):
            response = await client.get("/api/v1/risk-triggers")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result["items"]) == 1
        assert result["items"][0]["rule_id"] is None
        assert result["items"][0]["trigger_type"] == "circuit_breaker"

    async def test_triggers_without_run_id(self, client):
        """Test RSK-008-4: Triggers without associated run (global triggers)."""
        trigger = MagicMock()
        trigger.id = uuid4()
        trigger.time = datetime.now(UTC)
        trigger.rule_id = uuid4()
        trigger.run_id = None  # Global trigger not tied to specific run
        trigger.trigger_type = "circuit_breaker"
        trigger.details = {"rule_type": "circuit_breaker", "reason": "test"}
        trigger.rule = None
        trigger.run = None

        with patch(
            "squant.services.risk.RiskTriggerService.list_triggers",
            new_callable=AsyncMock,
            return_value=([trigger], 1),
        ):
            response = await client.get("/api/v1/risk-triggers")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result["items"]) == 1
        assert result["items"][0]["run_id"] is None
        assert result["items"][0]["rule_id"] is not None

    async def test_pagination_validation(self, client):
        """Test pagination parameter validation."""
        # Page must be >= 1
        response = await client.get("/api/v1/risk-triggers?page=0")
        assert response.status_code == 422

        # Page size must be >= 1
        response = await client.get("/api/v1/risk-triggers?page_size=0")
        assert response.status_code == 422

        # Page size must be <= 100
        response = await client.get("/api/v1/risk-triggers?page_size=101")
        assert response.status_code == 422

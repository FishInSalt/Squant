"""Integration tests for Risk Management API endpoints.

Tests CRUD operations for risk rules that protect against excessive losses.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from squant.models.enums import RiskRuleType


class TestCreateRiskRule:
    """Test creating risk rules."""

    @pytest.mark.asyncio
    async def test_create_order_limit_rule(self, client):
        """Test creating an order limit risk rule."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Max Order Size"
        mock_rule.type = RiskRuleType.ORDER_LIMIT
        mock_rule.params = {"max_order_value": 1000, "currency": "USDT"}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Max Order Size",
            "type": "order_limit",
            "params": {"max_order_value": 1000, "currency": "USDT"},
            "enabled": True,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "id" in result
        assert result["name"] == "Max Order Size"
        assert result["type"] == "order_limit"
        assert result["enabled"] is True

    @pytest.mark.asyncio
    async def test_create_position_limit_rule(self, client):
        """Test creating a position limit risk rule."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Max Position Size"
        mock_rule.type = RiskRuleType.POSITION_LIMIT
        mock_rule.params = {"max_position_pct": 0.5, "symbol": "BTC/USDT"}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Max Position Size",
            "type": "position_limit",
            "params": {"max_position_pct": 0.5, "symbol": "BTC/USDT"},
            "enabled": True,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["type"] == "position_limit"
        assert result["params"]["max_position_pct"] == 0.5

    @pytest.mark.asyncio
    async def test_create_daily_loss_limit_rule(self, client):
        """Test creating a daily loss limit risk rule."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Daily Loss Limit"
        mock_rule.type = RiskRuleType.DAILY_LOSS_LIMIT
        mock_rule.params = {"max_daily_loss": 500, "currency": "USDT"}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Daily Loss Limit",
            "type": "daily_loss_limit",
            "params": {"max_daily_loss": 500, "currency": "USDT"},
            "enabled": True,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["type"] == "daily_loss_limit"

    @pytest.mark.asyncio
    async def test_create_rule_disabled_by_default(self, client):
        """Test creating a risk rule that is disabled by default."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Test Rule"
        mock_rule.type = RiskRuleType.FREQUENCY_LIMIT
        mock_rule.params = {"max_trades_per_hour": 10}
        mock_rule.enabled = False
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Test Rule",
            "type": "frequency_limit",
            "params": {"max_trades_per_hour": 10},
            "enabled": False,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["enabled"] is False


class TestListRiskRules:
    """Test listing risk rules."""

    @pytest.mark.asyncio
    async def test_list_all_rules(self, client):
        """Test listing all risk rules."""
        mock_rule1 = MagicMock()
        mock_rule1.id = uuid4()
        mock_rule1.name = "Rule 1"
        mock_rule1.type = RiskRuleType.ORDER_LIMIT
        mock_rule1.enabled = True
        mock_rule1.created_at = datetime.now(UTC)

        mock_rule2 = MagicMock()
        mock_rule2.id = uuid4()
        mock_rule2.name = "Rule 2"
        mock_rule2.type = RiskRuleType.POSITION_LIMIT
        mock_rule2.enabled = False
        mock_rule2.created_at = datetime.now(UTC)

        with patch(
            "squant.services.risk.RiskRuleService.list",
            new_callable=AsyncMock,
            return_value=([mock_rule1, mock_rule2], 2),
        ):
            response = await client.get("/api/v1/risk-rules?page=1&page_size=20")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 2
        assert result["page"] == 1
        assert result["page_size"] == 20
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_filter_by_enabled_status(self, client):
        """Test filtering rules by enabled status."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Enabled Rule"
        mock_rule.type = RiskRuleType.DAILY_LOSS_LIMIT
        mock_rule.enabled = True
        mock_rule.created_at = datetime.now(UTC)

        with patch(
            "squant.services.risk.RiskRuleService.list",
            new_callable=AsyncMock,
            return_value=([mock_rule], 1),
        ):
            response = await client.get("/api/v1/risk-rules?enabled=true")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 1
        assert result["items"][0]["enabled"] is True

    @pytest.mark.asyncio
    async def test_pagination(self, client):
        """Test pagination of risk rules."""
        rules = []
        for i in range(5):
            mock_rule = MagicMock()
            mock_rule.id = uuid4()
            mock_rule.name = f"Rule {i}"
            mock_rule.type = RiskRuleType.ORDER_LIMIT
            mock_rule.enabled = True
            mock_rule.created_at = datetime.now(UTC)
            rules.append(mock_rule)

        with patch(
            "squant.services.risk.RiskRuleService.list",
            new_callable=AsyncMock,
            return_value=(rules, 5),
        ):
            response = await client.get("/api/v1/risk-rules?page=1&page_size=5")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["total"] == 5
        assert len(result["items"]) == 5


class TestGetRiskRule:
    """Test getting individual risk rule details."""

    @pytest.mark.asyncio
    async def test_get_rule_by_id(self, client):
        """Test getting a risk rule by ID."""
        rule_id = uuid4()

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Test Rule"
        mock_rule.type = RiskRuleType.ORDER_LIMIT
        mock_rule.params = {"max_order_value": 1000}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        with patch(
            "squant.services.risk.RiskRuleService.get",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.get(f"/api/v1/risk-rules/{rule_id}")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["id"] == str(rule_id)
        assert result["name"] == "Test Rule"

    @pytest.mark.asyncio
    async def test_get_nonexistent_rule(self, client):
        """Test getting a rule that doesn't exist."""
        from squant.services.risk import RiskRuleNotFoundError

        rule_id = uuid4()

        with patch(
            "squant.services.risk.RiskRuleService.get",
            new_callable=AsyncMock,
            side_effect=RiskRuleNotFoundError(f"Risk rule {rule_id} not found"),
        ):
            response = await client.get(f"/api/v1/risk-rules/{rule_id}")

        assert response.status_code == 404
        data = response.json()
        assert "message" in data


class TestUpdateRiskRule:
    """Test updating risk rules."""

    @pytest.mark.asyncio
    async def test_update_rule_name(self, client):
        """Test updating a risk rule's name."""
        rule_id = uuid4()

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Updated Rule Name"
        mock_rule.type = RiskRuleType.ORDER_LIMIT
        mock_rule.params = {"max_order_value": 1000}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        update_data = {"name": "Updated Rule Name"}

        with patch(
            "squant.services.risk.RiskRuleService.update",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.put(f"/api/v1/risk-rules/{rule_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["name"] == "Updated Rule Name"

    @pytest.mark.asyncio
    async def test_update_rule_params(self, client):
        """Test updating a risk rule's parameters."""
        rule_id = uuid4()

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Test Rule"
        mock_rule.type = RiskRuleType.DAILY_LOSS_LIMIT
        mock_rule.params = {"max_daily_loss": 1000, "currency": "USDT"}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        update_data = {"params": {"max_daily_loss": 1000, "currency": "USDT"}}

        with patch(
            "squant.services.risk.RiskRuleService.update",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.put(f"/api/v1/risk-rules/{rule_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["params"]["max_daily_loss"] == 1000

    @pytest.mark.asyncio
    async def test_update_nonexistent_rule(self, client):
        """Test updating a rule that doesn't exist."""
        from squant.services.risk import RiskRuleNotFoundError

        rule_id = uuid4()
        update_data = {"name": "New Name"}

        with patch(
            "squant.services.risk.RiskRuleService.update",
            new_callable=AsyncMock,
            side_effect=RiskRuleNotFoundError(f"Risk rule {rule_id} not found"),
        ):
            response = await client.put(f"/api/v1/risk-rules/{rule_id}", json=update_data)

        assert response.status_code == 404
        data = response.json()
        assert "message" in data


class TestDeleteRiskRule:
    """Test deleting risk rules."""

    @pytest.mark.asyncio
    async def test_delete_rule(self, client):
        """Test deleting a risk rule."""
        rule_id = uuid4()

        with patch(
            "squant.services.risk.RiskRuleService.delete",
            new_callable=AsyncMock,
            return_value=None,
        ):
            response = await client.delete(f"/api/v1/risk-rules/{rule_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["data"] is None
        assert "deleted" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_rule(self, client):
        """Test deleting a rule that doesn't exist."""
        from squant.services.risk import RiskRuleNotFoundError

        rule_id = uuid4()

        with patch(
            "squant.services.risk.RiskRuleService.delete",
            new_callable=AsyncMock,
            side_effect=RiskRuleNotFoundError(f"Risk rule {rule_id} not found"),
        ):
            response = await client.delete(f"/api/v1/risk-rules/{rule_id}")

        assert response.status_code == 404
        data = response.json()
        assert "message" in data


class TestToggleRiskRule:
    """Test enabling/disabling risk rules."""

    @pytest.mark.asyncio
    async def test_enable_rule(self, client):
        """Test enabling a disabled risk rule."""
        rule_id = uuid4()

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Test Rule"
        mock_rule.type = RiskRuleType.ORDER_LIMIT
        mock_rule.params = {"max_order_value": 1000}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        toggle_data = {"enabled": True}

        with patch(
            "squant.services.risk.RiskRuleService.toggle",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post(f"/api/v1/risk-rules/{rule_id}/toggle", json=toggle_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_rule(self, client):
        """Test disabling an enabled risk rule."""
        rule_id = uuid4()

        mock_rule = MagicMock()
        mock_rule.id = rule_id
        mock_rule.name = "Test Rule"
        mock_rule.type = RiskRuleType.POSITION_LIMIT
        mock_rule.params = {"max_position_pct": 0.5}
        mock_rule.enabled = False
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        toggle_data = {"enabled": False}

        with patch(
            "squant.services.risk.RiskRuleService.toggle",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post(f"/api/v1/risk-rules/{rule_id}/toggle", json=toggle_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["enabled"] is False

    @pytest.mark.asyncio
    async def test_toggle_nonexistent_rule(self, client):
        """Test toggling a rule that doesn't exist."""
        from squant.services.risk import RiskRuleNotFoundError

        rule_id = uuid4()
        toggle_data = {"enabled": True}

        with patch(
            "squant.services.risk.RiskRuleService.toggle",
            new_callable=AsyncMock,
            side_effect=RiskRuleNotFoundError(f"Risk rule {rule_id} not found"),
        ):
            response = await client.post(f"/api/v1/risk-rules/{rule_id}/toggle", json=toggle_data)

        assert response.status_code == 404
        data = response.json()
        assert "message" in data


class TestAllRiskRuleTypes:
    """Test creating all types of risk rules."""

    @pytest.mark.asyncio
    async def test_total_loss_limit_rule(self, client):
        """Test creating a total loss limit rule."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Total Loss Limit"
        mock_rule.type = RiskRuleType.TOTAL_LOSS_LIMIT
        mock_rule.params = {"max_total_loss": 2000, "currency": "USDT"}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Total Loss Limit",
            "type": "total_loss_limit",
            "params": {"max_total_loss": 2000, "currency": "USDT"},
            "enabled": True,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["type"] == "total_loss_limit"

    @pytest.mark.asyncio
    async def test_frequency_limit_rule(self, client):
        """Test creating a frequency limit rule."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Trading Frequency Limit"
        mock_rule.type = RiskRuleType.FREQUENCY_LIMIT
        mock_rule.params = {"max_trades_per_day": 50}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Trading Frequency Limit",
            "type": "frequency_limit",
            "params": {"max_trades_per_day": 50},
            "enabled": True,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["type"] == "frequency_limit"

    @pytest.mark.asyncio
    async def test_volatility_break_rule(self, client):
        """Test creating a volatility break rule."""
        mock_rule = MagicMock()
        mock_rule.id = uuid4()
        mock_rule.name = "Volatility Circuit Breaker"
        mock_rule.type = RiskRuleType.VOLATILITY_BREAK
        mock_rule.params = {"volatility_threshold": 0.1, "lookback_period": 60}
        mock_rule.enabled = True
        mock_rule.description = None
        mock_rule.last_triggered = None
        mock_rule.created_at = datetime.now(UTC)
        mock_rule.updated_at = datetime.now(UTC)

        request_data = {
            "name": "Volatility Circuit Breaker",
            "type": "volatility_break",
            "params": {"volatility_threshold": 0.1, "lookback_period": 60},
            "enabled": True,
        }

        with patch(
            "squant.services.risk.RiskRuleService.create",
            new_callable=AsyncMock,
            return_value=mock_rule,
        ):
            response = await client.post("/api/v1/risk-rules", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["type"] == "volatility_break"

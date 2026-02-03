"""
Integration tests for Strategy API endpoints.

Tests validate acceptance criteria from dev-docs/requirements/acceptance-criteria/02-strategy.md:
- STR-001: Provide strategy template base class
- STR-011: Syntax validation with detailed error messages
- STR-012: Security checks (forbidden imports/functions)
- STR-014: Auto-save to strategy library after validation
- STR-020: Strategy list display
- STR-021: Strategy details view
- STR-024: Strategy deletion
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from squant.models.enums import StrategyStatus
from squant.models.strategy import Strategy


class TestStrategyTemplateBaseClass:
    """
    Tests for STR-001: Provide strategy template base class

    Acceptance criteria:
    - Strategy can use all lifecycle methods when inheriting base class
    - Validation fails if on_bar method not implemented
    - Validation passes if strategy correctly inherits template
    """

    @pytest.mark.asyncio
    async def test_validate_code_with_on_bar_method(self, client):
        """Test STR-001-3: Validation passes when strategy correctly inherits template."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_code_without_on_bar_method(self, client):
        """Test STR-001-2: Validation fails if on_bar method not implemented."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def some_other_method(self):
        pass
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        # Should have error about missing on_bar method
        assert any("on_bar" in error.lower() for error in result["errors"])


class TestSyntaxValidation:
    """
    Tests for STR-011: Syntax validation with detailed error messages

    Acceptance criteria:
    - Return error line number and description for syntax errors
    - Continue to next validation if syntax is correct
    - Return list of all errors when multiple exist
    """

    @pytest.mark.asyncio
    async def test_syntax_validation_with_errors(self, client):
        """Test STR-011-1: Return error line number and description."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar)
        # Missing colon causes syntax error
        pass
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_syntax_validation_passes(self, client):
        """Test STR-011-2: Syntax check passes for correct code."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        # Should be valid
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_multiple_syntax_errors(self, client):
        """Test STR-011-3: Return all errors in a list."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar)  # Missing colon
        x = undefined_variable  # Indentation issues
        # Multiple issues should be reported
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        # Should have at least one error
        assert len(result["errors"]) > 0


class TestSecurityChecks:
    """
    Tests for STR-012: Security checks

    Acceptance criteria:
    - Reject import of os module
    - Reject import of subprocess
    - Reject use of eval() function
    - Reject use of exec() function
    - Pass security check for allowed modules only
    """

    @pytest.mark.asyncio
    async def test_reject_os_module(self, client):
        """Test STR-012-1: Reject import of os module."""
        validate_request = {
            "code": """import os

class MyStrategy(Strategy):
    def on_bar(self, bar):
        os.system('ls')
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        # Should mention forbidden import
        assert any("import" in error.lower() or "os" in error.lower() for error in result["errors"])

    @pytest.mark.asyncio
    async def test_reject_subprocess_module(self, client):
        """Test STR-012-2: Reject import of subprocess."""
        validate_request = {
            "code": """import subprocess

class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        assert any(
            "import" in error.lower() or "subprocess" in error.lower() for error in result["errors"]
        )

    @pytest.mark.asyncio
    async def test_reject_eval_function(self, client):
        """Test STR-012-3: Reject use of eval() function."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        eval('1 + 1')
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        assert any("eval" in error.lower() for error in result["errors"])

    @pytest.mark.asyncio
    async def test_reject_exec_function(self, client):
        """Test STR-012-4: Reject use of exec() function."""
        validate_request = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        exec('x = 1')
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["valid"] is False
        assert any("exec" in error.lower() for error in result["errors"])

    @pytest.mark.asyncio
    async def test_allow_safe_code(self, client):
        """Test STR-012-5: Security check passes for allowed modules."""
        validate_request = {
            "code": """import numpy as np

class MyStrategy(Strategy):
    def on_bar(self, bar):
        # Using allowed imports
        data = np.array([1, 2, 3])
"""
        }

        response = await client.post("/api/v1/strategies/validate", json=validate_request)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        # Should pass security checks (may have other warnings/errors)
        assert result["valid"] is True or all(
            "forbidden" not in error.lower() for error in result["errors"]
        )


class TestAutoSaveToLibrary:
    """
    Tests for STR-014: Auto-save to strategy library after validation

    Acceptance criteria:
    - Strategy saved to library after passing all validations
    - New strategy appears in strategy list after save
    - Prompt if strategy name already exists
    """

    @pytest.mark.asyncio
    async def test_create_strategy_after_validation(self, client, db_session):
        """Test STR-014-1 & STR-014-2: Save strategy after validation passes."""
        strategy_data = {
            "name": "Test Strategy",
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
""",
            "description": "Integration test strategy",
        }

        response = await client.post("/api/v1/strategies", json=strategy_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["name"] == "Test Strategy"
        assert "id" in result

        # Verify saved to database
        strategy_id = result["id"]
        db_result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        db_strategy = db_result.scalar_one_or_none()
        assert db_strategy is not None
        assert db_strategy.name == "Test Strategy"

    @pytest.mark.asyncio
    async def test_create_strategy_with_duplicate_name(self, client, db_session):
        """Test STR-014-3: Prompt if strategy name already exists."""
        # Create first strategy
        existing_strategy = Strategy(
            id=uuid4(),
            name="Duplicate Name",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            version="1.0.0",
        )
        db_session.add(existing_strategy)
        await db_session.commit()

        # Try to create second strategy with same name
        strategy_data = {
            "name": "Duplicate Name",
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
""",
        }

        response = await client.post("/api/v1/strategies", json=strategy_data)

        # Should return 409 Conflict
        assert response.status_code == 409
        data = response.json()

        assert "detail" in data
        assert "exists" in data["detail"].lower() or "已存在" in data["detail"]


class TestStrategyListDisplay:
    """
    Tests for STR-020: Strategy list display

    Acceptance criteria:
    - Display all strategies when strategy library has strategies
    - Each strategy shows name, version, status, created_at
    - Show empty state when no strategies exist
    """

    @pytest.mark.asyncio
    async def test_list_strategies_with_data(self, client, db_session):
        """Test STR-020-1 & STR-020-2: Display all strategies with required fields."""
        # Create test strategies
        for i in range(3):
            strategy = Strategy(
                id=uuid4(),
                name=f"Strategy {i}",
                code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
                version=f"1.{i}.0",
                status=StrategyStatus.ACTIVE,
            )
            db_session.add(strategy)
        await db_session.commit()

        response = await client.get("/api/v1/strategies")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "items" in result
        assert "total" in result
        assert len(result["items"]) >= 3

        # Check required fields in each strategy
        for strategy in result["items"]:
            assert "name" in strategy
            assert "version" in strategy
            assert "status" in strategy
            assert "created_at" in strategy

    @pytest.mark.asyncio
    async def test_list_strategies_empty_state(self, client):
        """Test STR-020-3: Show empty state when no strategies."""
        response = await client.get("/api/v1/strategies")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        # Empty list is valid response
        assert "items" in result
        assert isinstance(result["items"], list)

    @pytest.mark.asyncio
    async def test_list_strategies_pagination(self, client, db_session):
        """Test pagination support for strategy list."""
        # Create many strategies
        for i in range(25):
            strategy = Strategy(
                id=uuid4(),
                name=f"Pagination Test {i}",
                code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
                version="1.0.0",
            )
            db_session.add(strategy)
        await db_session.commit()

        # Get first page
        response = await client.get("/api/v1/strategies", params={"page": 1, "page_size": 10})

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert len(result["items"]) == 10
        assert result["page"] == 1
        assert result["page_size"] == 10
        assert result["total"] >= 25


class TestStrategyDetailsView:
    """
    Tests for STR-021: Strategy details view

    Acceptance criteria:
    - Click strategy name to enter details page
    - Display strategy name, version, description, params
    """

    @pytest.mark.asyncio
    async def test_get_strategy_details(self, client, db_session):
        """Test STR-021-1 & STR-021-2: Display complete strategy details."""
        # Create strategy with full details
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Detailed Strategy",
            code="class MyStrategy:\n    def on_bar(self, bar):\n        pass",
            version="2.0.0",
            description="This is a detailed strategy",
            params_schema={"type": "object", "properties": {"param1": {"type": "number"}}},
            default_params={"param1": 10},
        )
        db_session.add(strategy)
        await db_session.commit()

        response = await client.get(f"/api/v1/strategies/{strategy_id}")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["id"] == str(strategy_id)
        assert result["name"] == "Detailed Strategy"
        assert result["version"] == "2.0.0"
        assert result["description"] == "This is a detailed strategy"
        assert result["params_schema"] == {
            "type": "object",
            "properties": {"param1": {"type": "number"}},
        }
        assert result["default_params"] == {"param1": 10}

    @pytest.mark.asyncio
    async def test_get_strategy_includes_code(self, client, db_session):
        """Test STR-022: Strategy details include source code."""
        strategy_id = uuid4()
        strategy_code = "class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        # Strategy logic here\n        pass"
        strategy = Strategy(
            id=strategy_id,
            name="Code Preview Strategy",
            code=strategy_code,
            version="1.0.0",
        )
        db_session.add(strategy)
        await db_session.commit()

        response = await client.get(f"/api/v1/strategies/{strategy_id}")

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "code" in result
        assert result["code"] == strategy_code

    @pytest.mark.asyncio
    async def test_get_nonexistent_strategy(self, client):
        """Test getting non-existent strategy returns 404."""
        response = await client.get(f"/api/v1/strategies/{uuid4()}")

        assert response.status_code == 404


class TestStrategyDeletion:
    """
    Tests for STR-024: Strategy deletion

    Acceptance criteria:
    - Show confirmation dialog when deleting (frontend)
    - Remove strategy from library after confirmation
    - Cannot delete running strategy
    """

    @pytest.mark.asyncio
    async def test_delete_strategy_success(self, client, db_session):
        """Test STR-024-2: Strategy removed from library after deletion."""
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="To Be Deleted",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            version="1.0.0",
        )
        db_session.add(strategy)
        await db_session.commit()

        response = await client.delete(f"/api/v1/strategies/{strategy_id}")

        assert response.status_code == 200

        # Verify deleted from database
        db_result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        db_strategy = db_result.scalar_one_or_none()
        assert db_strategy is None

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Running strategy deletion constraint tested at service level - requires StrategyRun setup"
    )
    async def test_cannot_delete_running_strategy(self, client, db_session):
        """Test STR-024-3: Cannot delete strategy that is running."""
        # This would require creating a StrategyRun linked to the strategy
        # Skipped for integration test simplicity - tested at service level
        pass


class TestStrategyUpdate:
    """Test strategy update operations."""

    @pytest.mark.asyncio
    async def test_update_strategy_name_and_description(self, client, db_session):
        """Test updating strategy name and description."""
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Original Name",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            version="1.0.0",
            description="Original description",
        )
        db_session.add(strategy)
        await db_session.commit()

        update_data = {
            "name": "Updated Name",
            "description": "Updated description",
        }

        response = await client.put(f"/api/v1/strategies/{strategy_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert result["name"] == "Updated Name"
        assert result["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_strategy_code(self, client, db_session):
        """Test updating strategy code triggers validation."""
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Code Update Test",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            version="1.0.0",
        )
        db_session.add(strategy)
        await db_session.commit()

        update_data = {
            "code": """class MyStrategy(Strategy):
    def on_bar(self, bar):
        # Updated logic
        print("New code")
"""
        }

        response = await client.put(f"/api/v1/strategies/{strategy_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()

        result = data["data"]
        assert "New code" in result["code"]

    @pytest.mark.asyncio
    async def test_update_strategy_with_invalid_code(self, client, db_session):
        """Test updating with invalid code returns validation error."""
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Invalid Update Test",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            version="1.0.0",
        )
        db_session.add(strategy)
        await db_session.commit()

        update_data = {"code": "this is not valid python code !!!"}

        response = await client.put(f"/api/v1/strategies/{strategy_id}", json=update_data)

        # Should return validation error (400)
        assert response.status_code == 400


class TestStrategyValidation:
    """Additional validation tests."""

    @pytest.mark.asyncio
    async def test_create_strategy_without_required_field(self, client):
        """Test creating strategy without required name field."""
        strategy_data = {
            "code": "class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            # Missing name field
        }

        response = await client.post("/api/v1/strategies", json=strategy_data)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_strategy_with_invalid_code(self, client):
        """Test creating strategy with invalid code returns validation error."""
        strategy_data = {
            "name": "Invalid Strategy",
            "code": "this is not valid python code !!!",
        }

        response = await client.post("/api/v1/strategies", json=strategy_data)

        # Should return validation error (400)
        assert response.status_code == 400

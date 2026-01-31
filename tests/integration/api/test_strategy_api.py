"""
API集成测试示例 - Strategy API

展示如何进行完整的API集成测试，包括数据库持久化验证。
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from squant.api.deps import get_session
from squant.main import app
from squant.models.strategy import Strategy

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session):
    """创建异步测试客户端，使用真实数据库session"""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestStrategyAPIIntegration:
    """策略API集成测试"""

    @pytest.mark.asyncio
    async def test_create_strategy_end_to_end(self, client, db_session):
        """
        测试创建策略的完整流程

        验证: API请求 → 数据持久化 → 响应正确性
        """
        # Arrange
        strategy_data = {
            "name": "Integration Test Strategy",
            "code": "class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            "description": "A strategy created in integration test",
        }

        # Act - 通过API创建策略
        response = await client.post("/api/v1/strategies", json=strategy_data)

        # Assert - 验证响应
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["code"] == 0
        created_strategy = response_data["data"]
        assert created_strategy["name"] == strategy_data["name"]
        assert "id" in created_strategy
        strategy_id = created_strategy["id"]

        # Assert - 验证数据库持久化
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        db_strategy = result.scalar_one_or_none()
        assert db_strategy is not None
        assert db_strategy.name == strategy_data["name"]
        assert db_strategy.code == strategy_data["code"]

    @pytest.mark.asyncio
    async def test_get_strategy_by_id(self, client, db_session):
        """测试通过ID获取策略"""
        # Arrange - 先在数据库中创建策略
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Get Test Strategy",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act - 通过API获取策略
        response = await client.get(f"/api/v1/strategies/{strategy_id}")

        # Assert
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["code"] == 0
        strategy_data = response_data["data"]
        assert strategy_data["id"] == str(strategy_id)
        assert strategy_data["name"] == "Get Test Strategy"

    @pytest.mark.asyncio
    async def test_update_strategy(self, client, db_session):
        """测试更新策略"""
        # Arrange - 创建初始策略
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Original Name",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act - 通过API更新策略
        update_data = {
            "name": "Updated Name",
            "description": "Updated description",
        }
        response = await client.put(f"/api/v1/strategies/{strategy_id}", json=update_data)

        # Assert - 验证响应
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["code"] == 0
        updated_strategy = response_data["data"]
        assert updated_strategy["name"] == "Updated Name"

        # Assert - 验证数据库更新
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        db_strategy = result.scalar_one()
        assert db_strategy.name == "Updated Name"
        assert db_strategy.description == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_strategy(self, client, db_session):
        """测试删除策略"""
        # Arrange - 创建策略
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="To Be Deleted",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act - 通过API删除策略
        response = await client.delete(f"/api/v1/strategies/{strategy_id}")

        # Assert - 验证响应
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["code"] == 0

        # Assert - 验证数据库删除
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        db_strategy = result.scalar_one_or_none()
        assert db_strategy is None

    @pytest.mark.asyncio
    async def test_list_strategies(self, client, db_session):
        """测试列出所有策略"""
        # Arrange - 创建多个策略
        for i in range(3):
            strategy = Strategy(
                id=uuid4(),
                name=f"List Test Strategy {i}",
                code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            )
            db_session.add(strategy)
        await db_session.commit()

        # Act - 通过API获取策略列表
        response = await client.get("/api/v1/strategies")

        # Assert
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["code"] == 0
        strategies = response_data["data"]["items"]
        assert isinstance(strategies, list)
        assert len(strategies) >= 3


class TestStrategyAPIValidation:
    """测试API数据验证"""

    @pytest.mark.asyncio
    async def test_create_strategy_with_invalid_code(self, client):
        """测试创建包含无效代码的策略"""
        # Arrange
        strategy_data = {
            "name": "Invalid Strategy",
            "code": "this is not valid python code !!!",
        }

        # Act
        response = await client.post("/api/v1/strategies", json=strategy_data)

        # Assert - 可能是422（验证失败）或400（业务逻辑错误）
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_create_strategy_without_required_field(self, client):
        """测试缺少必需字段"""
        # Arrange
        strategy_data = {
            "code": "class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            # 缺少 name 字段
        }

        # Act
        response = await client.post("/api/v1/strategies", json=strategy_data)

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_nonexistent_strategy(self, client):
        """测试获取不存在的策略"""
        # Act
        response = await client.get(f"/api/v1/strategies/{uuid4()}")

        # Assert
        assert response.status_code == 404


class TestStrategyAPIErrorHandling:
    """测试API错误处理"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Mock doesn't work correctly with async session - test needs redesign")
    async def test_database_error_handling(self, client, db_session):
        """测试数据库错误处理"""
        from unittest.mock import patch

        # Arrange
        strategy_data = {
            "name": "Test Strategy",
            "code": "class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        }

        # Act - Mock数据库提交失败
        with patch.object(db_session, "commit", side_effect=Exception("Database error")):
            response = await client.post("/api/v1/strategies", json=strategy_data)

        # Assert
        # 应该返回500或适当的错误码
        assert response.status_code >= 400


class TestStrategyAPIConcurrency:
    """测试API并发场景"""

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, client, db_session):
        """测试并发更新同一策略"""
        # Arrange - 创建策略
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Concurrent Test",
            code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act - 两次更新
        update1 = {"name": "Update 1"}
        update2 = {"name": "Update 2"}

        response1 = await client.put(f"/api/v1/strategies/{strategy_id}", json=update1)
        response2 = await client.put(f"/api/v1/strategies/{strategy_id}", json=update2)

        # Assert - 两次更新都应该成功
        assert response1.status_code == 200
        assert response2.status_code == 200

        # 最后一次更新应该生效
        final_response = await client.get(f"/api/v1/strategies/{strategy_id}")
        final_data = final_response.json()
        assert final_data["code"] == 0
        assert final_data["data"]["name"] == "Update 2"


class TestStrategyAPIPerformance:
    """测试API性能"""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_bulk_create_strategies(self, client, db_session):
        """测试批量创建策略的性能"""
        import time

        # Act
        start = time.time()
        for i in range(10):
            strategy_data = {
                "name": f"Bulk Strategy {i}",
                "code": "class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            }
            response = await client.post("/api/v1/strategies", json=strategy_data)
            assert response.status_code == 200

        duration = time.time() - start

        # Assert - 10个请求应该在合理时间内完成
        assert duration < 5.0  # 5秒内完成

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_list_large_number_of_strategies(self, client, db_session):
        """测试列出大量策略的性能"""
        import time

        # Arrange - 创建100个策略
        for i in range(100):
            strategy = Strategy(
                id=uuid4(),
                name=f"Performance Test Strategy {i}",
                code="class MyStrategy(Strategy):\n    def on_bar(self, bar):\n        pass",
            )
            db_session.add(strategy)
        await db_session.commit()

        # Act
        start = time.time()
        response = await client.get("/api/v1/strategies")
        duration = time.time() - start

        # Assert
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["code"] == 0
        # API returns paginated results with default limit=20
        # Check total count instead of items length
        data = response_data["data"]
        assert data["total"] >= 100 or len(data["items"]) >= 20
        assert duration < 2.0  # 2秒内完成

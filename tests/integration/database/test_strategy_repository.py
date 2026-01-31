"""
数据库集成测试示例 - Strategy Repository

这个测试文件展示如何编写真实数据库集成测试。
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from squant.models.strategy import Strategy

pytestmark = pytest.mark.integration


class TestStrategyRepository:
    """测试Strategy数据库操作"""

    @pytest.mark.asyncio
    async def test_create_strategy(self, db_session):
        """测试创建策略并持久化到数据库"""
        # Arrange
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Test Strategy",
            code="def initialize(context): pass",
            description="A test strategy",
        )

        # Act
        db_session.add(strategy)
        await db_session.commit()
        await db_session.refresh(strategy)

        # Assert
        assert str(strategy.id) == str(strategy_id)
        assert strategy.name == "Test Strategy"
        assert strategy.created_at is not None

    @pytest.mark.asyncio
    async def test_query_strategy_by_id(self, db_session):
        """测试通过ID查询策略"""
        # Arrange - 先创建一个策略
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="Query Test Strategy",
            code="def initialize(context): pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act - 重新查询
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        found_strategy = result.scalar_one_or_none()

        # Assert
        assert found_strategy is not None
        assert str(found_strategy.id) == str(strategy_id)
        assert found_strategy.name == "Query Test Strategy"

    @pytest.mark.asyncio
    async def test_update_strategy(self, db_session):
        """测试更新策略"""
        # Arrange
        strategy = Strategy(
            id=uuid4(),
            name="Original Name",
            code="def initialize(context): pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act
        strategy.name = "Updated Name"
        strategy.description = "Updated description"
        await db_session.commit()
        await db_session.refresh(strategy)

        # Assert
        assert strategy.name == "Updated Name"
        assert strategy.description == "Updated description"
        assert strategy.updated_at > strategy.created_at

    @pytest.mark.asyncio
    async def test_delete_strategy(self, db_session):
        """测试删除策略"""
        # Arrange
        strategy_id = uuid4()
        strategy = Strategy(
            id=strategy_id,
            name="To Be Deleted",
            code="def initialize(context): pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act
        await db_session.delete(strategy)
        await db_session.commit()

        # Assert - 验证已删除
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        found = result.scalar_one_or_none()
        assert found is None

    @pytest.mark.asyncio
    async def test_list_all_strategies(self, db_session):
        """测试查询所有策略"""
        # Arrange - 创建多个策略
        strategies = [
            Strategy(id=uuid4(), name=f"Strategy {i}", code="def initialize(context): pass")
            for i in range(3)
        ]
        for strategy in strategies:
            db_session.add(strategy)
        await db_session.commit()

        # Act
        result = await db_session.execute(select(Strategy))
        all_strategies = result.scalars().all()

        # Assert
        assert len(all_strategies) >= 3  # 至少包含我们创建的3个

    @pytest.mark.asyncio
    async def test_strategy_with_long_code(self, db_session):
        """测试保存包含长代码的策略"""
        # Arrange
        long_code = (
            """
def initialize(context):
    context.ma_short = 10
    context.ma_long = 30

def handle_data(context, data):
    # Get historical data
    short_ma = data.history('close', context.ma_short).mean()
    long_ma = data.history('close', context.ma_long).mean()
    current_price = data.current('close')

    # Trading logic
    if short_ma > long_ma:
        if context.position == 0:
            context.order('BTC/USDT', 0.1)
    elif short_ma < long_ma:
        if context.position > 0:
            context.order('BTC/USDT', -context.position)
"""
            * 10
        )  # 重复10次使代码很长

        strategy = Strategy(
            id=uuid4(),
            name="Long Code Strategy",
            code=long_code,
        )

        # Act
        db_session.add(strategy)
        await db_session.commit()
        await db_session.refresh(strategy)

        # Assert
        assert strategy.code == long_code
        assert len(strategy.code) > 1000

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, db_session):
        """测试事务回滚"""
        # Arrange
        strategy = Strategy(
            id=uuid4(),
            name="Rollback Test",
            code="def initialize(context): pass",
        )
        db_session.add(strategy)

        # Act - 不提交，直接回滚
        await db_session.rollback()

        # Assert - 数据不应该被保存
        result = await db_session.execute(select(Strategy))
        all_strategies = result.scalars().all()
        assert not any(s.name == "Rollback Test" for s in all_strategies)

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, db_session):
        """测试并发更新（简单场景）"""
        # Arrange
        strategy = Strategy(
            id=uuid4(),
            name="Concurrent Test",
            code="def initialize(context): pass",
        )
        db_session.add(strategy)
        await db_session.commit()

        # Act - 模拟两次更新
        strategy.name = "Update 1"
        await db_session.commit()

        strategy.name = "Update 2"
        await db_session.commit()

        await db_session.refresh(strategy)

        # Assert
        assert strategy.name == "Update 2"

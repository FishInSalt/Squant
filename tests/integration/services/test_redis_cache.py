"""
Redis集成测试示例

展示如何测试Redis缓存功能。
"""

import json
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


class TestRedisCache:
    """测试Redis缓存操作"""

    @pytest.mark.asyncio
    async def test_set_and_get_string(self, redis):
        """测试设置和获取字符串"""
        # Act
        await redis.set("test_key", "test_value")
        value = await redis.get("test_key")

        # Assert
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_set_with_expiration(self, redis):
        """测试带过期时间的键"""
        # Act
        await redis.set("expiring_key", "value", ex=1)  # 1秒过期

        # Assert - 立即读取应该存在
        value = await redis.get("expiring_key")
        assert value == "value"

        # Wait for expiration
        import asyncio

        await asyncio.sleep(1.1)

        # Assert - 过期后应该不存在
        value = await redis.get("expiring_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete_key(self, redis):
        """测试删除键"""
        # Arrange
        await redis.set("to_delete", "value")

        # Act
        result = await redis.delete("to_delete")

        # Assert
        assert result == 1  # 返回删除的键数量
        value = await redis.get("to_delete")
        assert value is None

    @pytest.mark.asyncio
    async def test_exists(self, redis):
        """测试检查键是否存在"""
        # Arrange
        await redis.set("existing_key", "value")

        # Act & Assert
        assert await redis.exists("existing_key") == 1
        assert await redis.exists("non_existing_key") == 0

    @pytest.mark.asyncio
    async def test_increment(self, redis):
        """测试递增操作"""
        # Act
        await redis.set("counter", "0")
        value1 = await redis.incr("counter")
        value2 = await redis.incr("counter")

        # Assert
        assert value1 == 1
        assert value2 == 2

    @pytest.mark.asyncio
    async def test_hash_operations(self, redis):
        """测试Hash操作"""
        # Act
        await redis.hset("user:1", "name", "Alice")
        await redis.hset("user:1", "age", "30")

        # Assert
        name = await redis.hget("user:1", "name")
        age = await redis.hget("user:1", "age")
        all_data = await redis.hgetall("user:1")

        assert name == "Alice"
        assert age == "30"
        assert all_data == {"name": "Alice", "age": "30"}

    @pytest.mark.asyncio
    async def test_list_operations(self, redis):
        """测试List操作"""
        # Act
        await redis.rpush("my_list", "item1")
        await redis.rpush("my_list", "item2")
        await redis.rpush("my_list", "item3")

        # Assert
        length = await redis.llen("my_list")
        assert length == 3

        items = await redis.lrange("my_list", 0, -1)
        assert items == ["item1", "item2", "item3"]

        first = await redis.lpop("my_list")
        assert first == "item1"

    @pytest.mark.asyncio
    async def test_set_operations(self, redis):
        """测试Set操作"""
        # Act
        await redis.sadd("my_set", "member1")
        await redis.sadd("my_set", "member2")
        await redis.sadd("my_set", "member1")  # 重复添加

        # Assert
        size = await redis.scard("my_set")
        assert size == 2  # Set自动去重

        is_member = await redis.sismember("my_set", "member1")
        assert is_member

        members = await redis.smembers("my_set")
        assert "member1" in members
        assert "member2" in members

    @pytest.mark.asyncio
    async def test_sorted_set_operations(self, redis):
        """测试Sorted Set操作"""
        # Act
        await redis.zadd("leaderboard", {"player1": 100})
        await redis.zadd("leaderboard", {"player2": 200})
        await redis.zadd("leaderboard", {"player3": 150})

        # Assert
        # 获取排名（从高到低）
        top_players = await redis.zrevrange("leaderboard", 0, -1, withscores=True)
        assert top_players[0][0] == "player2"  # 分数最高
        assert float(top_players[0][1]) == 200

        # 获取玩家排名
        rank = await redis.zrevrank("leaderboard", "player2")
        assert rank == 0  # 排名第一（从0开始）

    @pytest.mark.asyncio
    async def test_json_caching(self, redis):
        """测试缓存JSON数据"""
        # Arrange
        data = {
            "symbol": "BTC/USDT",
            "price": 50000.0,
            "timestamp": datetime.now().isoformat(),
        }

        # Act
        await redis.set("ticker:BTCUSDT", json.dumps(data))
        cached = await redis.get("ticker:BTCUSDT")
        restored_data = json.loads(cached)

        # Assert
        assert restored_data["symbol"] == data["symbol"]
        assert restored_data["price"] == data["price"]


class TestRedisPubSub:
    """测试Redis Pub/Sub功能"""

    @pytest.mark.asyncio
    async def test_publish_subscribe(self, redis):
        """测试发布订阅"""
        import asyncio

        received_messages = []

        # 订阅者任务
        async def subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("test_channel")

            # 等待并确认订阅完成
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            # 接收消息
            for _ in range(2):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    received_messages.append(message["data"])

            await pubsub.unsubscribe("test_channel")
            await pubsub.aclose()

        # 启动订阅者
        sub_task = asyncio.create_task(subscriber())

        # 等待订阅者准备好
        await asyncio.sleep(0.5)

        # 发布消息
        await redis.publish("test_channel", "message1")
        await asyncio.sleep(0.1)
        await redis.publish("test_channel", "message2")

        # 等待订阅者完成
        await sub_task

        # Assert
        assert len(received_messages) == 2
        assert "message1" in received_messages
        assert "message2" in received_messages

    @pytest.mark.asyncio
    async def test_pattern_subscribe(self, redis):
        """测试模式订阅"""
        import asyncio

        received_messages = []

        async def subscriber():
            pubsub = redis.pubsub()
            await pubsub.psubscribe("ticker:*")

            # 等待并确认模式订阅完成
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "psubscribe":
                    break

            for _ in range(2):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "pmessage":
                    received_messages.append(message["channel"])

            await pubsub.punsubscribe("ticker:*")
            await pubsub.aclose()

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)

        await redis.publish("ticker:BTCUSDT", "data1")
        await asyncio.sleep(0.1)
        await redis.publish("ticker:ETHUSDT", "data2")

        await sub_task

        # Assert
        assert len(received_messages) == 2


class TestRedisTransactions:
    """测试Redis事务"""

    @pytest.mark.asyncio
    async def test_pipeline(self, redis):
        """测试Pipeline批量操作"""
        # Act
        pipe = redis.pipeline()
        pipe.set("key1", "value1")
        pipe.set("key2", "value2")
        pipe.get("key1")
        pipe.get("key2")
        results = await pipe.execute()

        # Assert
        assert results[0] is True  # set key1
        assert results[1] is True  # set key2
        assert results[2] == "value1"  # get key1
        assert results[3] == "value2"  # get key2

    @pytest.mark.asyncio
    async def test_watch_multi(self, redis):
        """测试WATCH和MULTI（乐观锁）"""
        # Arrange
        await redis.set("counter", "10")

        # Act
        async with redis.pipeline() as pipe:
            while True:
                try:
                    # Watch the key
                    await pipe.watch("counter")
                    current_value = int(await pipe.get("counter"))

                    # Start transaction
                    pipe.multi()
                    pipe.set("counter", str(current_value + 1))
                    await pipe.execute()
                    break
                except Exception:
                    continue

        # Assert
        final_value = await redis.get("counter")
        assert final_value == "11"


class TestRedisPerformance:
    """Redis性能相关测试"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_bulk_operations(self, redis):
        """测试批量操作性能"""
        import time

        # Act - 批量设置1000个键
        start = time.time()
        pipe = redis.pipeline()
        for i in range(1000):
            pipe.set(f"bulk_key_{i}", f"value_{i}")
        await pipe.execute()
        duration = time.time() - start

        # Assert
        assert duration < 1.0  # 应该在1秒内完成

        # 验证数据
        value = await redis.get("bulk_key_500")
        assert value == "value_500"

    @pytest.mark.asyncio
    async def test_large_value(self, redis):
        """测试存储大值"""
        # Arrange
        large_value = "x" * (1024 * 1024)  # 1MB

        # Act
        await redis.set("large_key", large_value)
        retrieved = await redis.get("large_key")

        # Assert
        assert len(retrieved) == len(large_value)
        assert retrieved == large_value

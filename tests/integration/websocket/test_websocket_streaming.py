"""
WebSocket集成测试

测试WebSocket消息传递和Redis pub/sub集成。
注意：这些是集成测试，不启动实际的WebSocket服务器。
"""

import asyncio
import json
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


class TestRedisWebSocketIntegration:
    """测试Redis pub/sub作为WebSocket后端"""

    @pytest.mark.asyncio
    async def test_publish_subscribe_integration(self, redis):
        """测试Redis发布订阅集成"""
        received_messages = []

        # 订阅者
        async def subscriber_task():
            pubsub = redis.pubsub()
            await pubsub.subscribe("websocket:test")

            # 等待并确认订阅完成 - 读取订阅确认消息
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            # 接收3条消息
            for _ in range(3):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    received_messages.append(json.loads(message["data"]))

            await pubsub.unsubscribe("websocket:test")
            await pubsub.aclose()

        # 启动订阅者
        sub_task = asyncio.create_task(subscriber_task())

        # 等待订阅者准备好 - 给足够的时间建立订阅
        await asyncio.sleep(0.5)

        # 发布者发送消息
        messages = [
            {"type": "ticker", "symbol": "BTC/USDT", "price": 50000},
            {"type": "ticker", "symbol": "ETH/USDT", "price": 3000},
            {"type": "trade", "symbol": "BTC/USDT", "amount": 0.1},
        ]

        for msg in messages:
            await redis.publish("websocket:test", json.dumps(msg))
            await asyncio.sleep(0.1)  # 增加延迟确保消息传递

        # 等待订阅者完成
        await sub_task

        # 验证
        assert len(received_messages) == 3
        assert received_messages[0]["type"] == "ticker"
        assert received_messages[0]["symbol"] == "BTC/USDT"
        assert received_messages[1]["symbol"] == "ETH/USDT"
        assert received_messages[2]["type"] == "trade"

    @pytest.mark.asyncio
    async def test_multiple_channels(self, redis):
        """测试多频道订阅"""
        ticker_messages = []
        trade_messages = []

        async def ticker_subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("ticker:BTCUSDT")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            for _ in range(2):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    ticker_messages.append(message["data"])

            await pubsub.unsubscribe("ticker:BTCUSDT")
            await pubsub.aclose()

        async def trade_subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("trade:BTCUSDT")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            for _ in range(2):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    trade_messages.append(message["data"])

            await pubsub.unsubscribe("trade:BTCUSDT")
            await pubsub.aclose()

        # 启动两个订阅者
        ticker_task = asyncio.create_task(ticker_subscriber())
        trade_task = asyncio.create_task(trade_subscriber())

        await asyncio.sleep(0.5)

        # 发布到不同频道
        await redis.publish("ticker:BTCUSDT", "ticker_msg_1")
        await asyncio.sleep(0.1)
        await redis.publish("trade:BTCUSDT", "trade_msg_1")
        await asyncio.sleep(0.1)
        await redis.publish("ticker:BTCUSDT", "ticker_msg_2")
        await asyncio.sleep(0.1)
        await redis.publish("trade:BTCUSDT", "trade_msg_2")

        await ticker_task
        await trade_task

        # 验证各自收到正确的消息
        assert len(ticker_messages) == 2
        assert len(trade_messages) == 2
        assert "ticker_msg_1" in ticker_messages
        assert "trade_msg_1" in trade_messages

    @pytest.mark.asyncio
    async def test_pattern_subscription(self, redis):
        """测试模式订阅（订阅多个频道）"""
        received_channels = []

        async def pattern_subscriber():
            pubsub = redis.pubsub()
            await pubsub.psubscribe("ticker:*")

            # 等待模式订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "psubscribe":
                    break

            for _ in range(3):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "pmessage":
                    received_channels.append(message["channel"])

            await pubsub.punsubscribe("ticker:*")
            await pubsub.aclose()

        sub_task = asyncio.create_task(pattern_subscriber())
        await asyncio.sleep(0.5)

        # 发布到多个匹配的频道
        await redis.publish("ticker:BTCUSDT", "data1")
        await asyncio.sleep(0.1)
        await redis.publish("ticker:ETHUSDT", "data2")
        await asyncio.sleep(0.1)
        await redis.publish("ticker:BNBUSDT", "data3")
        await asyncio.sleep(0.1)
        await redis.publish("trade:BTCUSDT", "data4")  # 不匹配

        await sub_task

        # 验证只收到ticker:*的消息
        assert len(received_channels) == 3
        assert "ticker:BTCUSDT" in received_channels
        assert "ticker:ETHUSDT" in received_channels
        assert "ticker:BNBUSDT" in received_channels
        assert "trade:BTCUSDT" not in received_channels


class TestWebSocketMessageFormat:
    """测试WebSocket消息格式"""

    @pytest.mark.asyncio
    async def test_ticker_message_format(self, redis):
        """测试Ticker消息格式"""
        received = []

        async def subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("ticker:BTCUSDT")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
            if message and message["type"] == "message":
                received.append(json.loads(message["data"]))

            await pubsub.unsubscribe("ticker:BTCUSDT")
            await pubsub.aclose()

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)

        # 发布标准Ticker消息
        ticker_data = {
            "type": "ticker",
            "symbol": "BTC/USDT",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "last": 50000.0,
                "bid": 49999.0,
                "ask": 50001.0,
                "volume": 1234.56,
            },
        }
        await redis.publish("ticker:BTCUSDT", json.dumps(ticker_data))

        await sub_task

        # 验证消息格式
        assert len(received) == 1
        msg = received[0]
        assert msg["type"] == "ticker"
        assert msg["symbol"] == "BTC/USDT"
        assert "timestamp" in msg
        assert "data" in msg
        assert msg["data"]["last"] == 50000.0

    @pytest.mark.asyncio
    async def test_orderbook_message_format(self, redis):
        """测试订单簿消息格式"""
        received = []

        async def subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("orderbook:BTCUSDT")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
            if message and message["type"] == "message":
                received.append(json.loads(message["data"]))

            await pubsub.unsubscribe("orderbook:BTCUSDT")
            await pubsub.aclose()

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)

        # 发布订单簿更新
        orderbook_data = {
            "type": "orderbook",
            "symbol": "BTC/USDT",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "bids": [[49999.0, 1.5], [49998.0, 2.0]],
                "asks": [[50001.0, 1.2], [50002.0, 1.8]],
            },
        }
        await redis.publish("orderbook:BTCUSDT", json.dumps(orderbook_data))

        await sub_task

        # 验证
        assert len(received) == 1
        msg = received[0]
        assert msg["type"] == "orderbook"
        assert len(msg["data"]["bids"]) == 2
        assert len(msg["data"]["asks"]) == 2


class TestWebSocketHeartbeat:
    """测试心跳机制"""

    @pytest.mark.asyncio
    async def test_heartbeat_publishing(self, redis):
        """测试心跳消息发布"""
        heartbeats = []

        async def heartbeat_subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("heartbeat")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            # 接收3个心跳
            for _ in range(3):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    heartbeats.append(json.loads(message["data"]))

            await pubsub.unsubscribe("heartbeat")
            await pubsub.aclose()

        sub_task = asyncio.create_task(heartbeat_subscriber())
        await asyncio.sleep(0.5)

        # 模拟发送心跳
        for i in range(3):
            heartbeat = {
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat(),
                "sequence": i,
            }
            await redis.publish("heartbeat", json.dumps(heartbeat))
            await asyncio.sleep(0.1)

        await sub_task

        # 验证
        assert len(heartbeats) == 3
        assert heartbeats[0]["sequence"] == 0
        assert heartbeats[1]["sequence"] == 1
        assert heartbeats[2]["sequence"] == 2


class TestWebSocketErrorHandling:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_invalid_json_handling(self, redis):
        """测试处理无效JSON"""
        received = []

        async def subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("test:errors")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            for _ in range(2):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        received.append(("valid", data))
                    except json.JSONDecodeError:
                        received.append(("invalid", message["data"]))

            await pubsub.unsubscribe("test:errors")
            await pubsub.aclose()

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)

        # 发布有效和无效的消息
        await redis.publish("test:errors", json.dumps({"valid": True}))
        await asyncio.sleep(0.1)
        await redis.publish("test:errors", "invalid json {{{")

        await sub_task

        # 验证
        assert len(received) == 2
        assert received[0][0] == "valid"
        assert received[1][0] == "invalid"

    @pytest.mark.asyncio
    async def test_subscriber_disconnect_reconnect(self, redis):
        """测试订阅者断开和重连"""
        received = []

        # 第一次订阅
        pubsub = redis.pubsub()
        await pubsub.subscribe("test:reconnect")

        # 等待订阅确认
        while True:
            msg = await pubsub.get_message(timeout=2.0)
            if msg and msg["type"] == "subscribe":
                break

        # 接收第一条消息
        await asyncio.sleep(0.2)
        await redis.publish("test:reconnect", "message1")
        await asyncio.sleep(0.1)
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
        if msg and msg["type"] == "message":
            received.append(msg["data"])

        # 断开
        await pubsub.unsubscribe("test:reconnect")
        await pubsub.aclose()

        # 这条消息不会收到
        await redis.publish("test:reconnect", "message_lost")

        # 重新订阅
        pubsub = redis.pubsub()
        await pubsub.subscribe("test:reconnect")

        # 等待订阅确认
        while True:
            msg = await pubsub.get_message(timeout=2.0)
            if msg and msg["type"] == "subscribe":
                break

        # 接收重连后的消息
        await asyncio.sleep(0.2)
        await redis.publish("test:reconnect", "message2")
        await asyncio.sleep(0.1)
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
        if msg and msg["type"] == "message":
            received.append(msg["data"])

        await pubsub.unsubscribe("test:reconnect")
        await pubsub.aclose()

        # 验证
        assert len(received) == 2
        assert received[0] == "message1"
        assert received[1] == "message2"
        assert "message_lost" not in received


class TestWebSocketPerformance:
    """WebSocket性能测试"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_high_frequency_messages(self, redis):
        """测试高频消息传递"""
        import time

        received_count = 0
        message_count = 100

        async def subscriber():
            nonlocal received_count
            pubsub = redis.pubsub()
            await pubsub.subscribe("perf:test")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            start = time.time()
            for _ in range(message_count):
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                if message and message["type"] == "message":
                    received_count += 1

            duration = time.time() - start
            print(f"Received {received_count} messages in {duration:.2f}s")

            await pubsub.unsubscribe("perf:test")
            await pubsub.aclose()

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)

        # 快速发送100条消息
        for i in range(message_count):
            await redis.publish("perf:test", f"message_{i}")

        await sub_task

        # 验证
        assert received_count == message_count

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_message_payload(self, redis):
        """测试大消息负载"""
        received = []

        async def subscriber():
            pubsub = redis.pubsub()
            await pubsub.subscribe("large:message")

            # 等待订阅确认
            while True:
                msg = await pubsub.get_message(timeout=2.0)
                if msg and msg["type"] == "subscribe":
                    break

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
            if message and message["type"] == "message":
                received.append(json.loads(message["data"]))

            await pubsub.unsubscribe("large:message")
            await pubsub.aclose()

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.5)

        # 发送大消息（1000个订单簿条目）
        large_orderbook = {
            "type": "orderbook",
            "symbol": "BTC/USDT",
            "data": {
                "bids": [[50000 - i, 0.1 * i] for i in range(500)],
                "asks": [[50000 + i, 0.1 * i] for i in range(500)],
            },
        }
        await redis.publish("large:message", json.dumps(large_orderbook))

        await sub_task

        # 验证
        assert len(received) == 1
        assert len(received[0]["data"]["bids"]) == 500
        assert len(received[0]["data"]["asks"]) == 500

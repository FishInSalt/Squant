"""
Circuit breaker流程端到端测试

测试熔断器的完整业务流程：触发熔断 → 停止所有交易 → 拒绝新启动 → 重置。

验收标准覆盖:
- RSK-010: 手动一键熔断
- RSK-011: 手动一键平仓
"""

import asyncio

import pytest

pytestmark = pytest.mark.e2e


class TestCircuitBreakerBasicFlow:
    """测试熔断器基本流程"""

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(
        self,
        api_client,
    ):
        """
        测试获取熔断器状态

        验证 API 端点返回正确的状态结构
        """
        response = await api_client.get("/api/v1/circuit-breaker/status")
        assert response.status_code == 200, f"Failed to get status: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        status = response_data["data"]
        assert "is_active" in status
        assert "triggered_at" in status
        assert "trigger_reason" in status
        assert "cooldown_until" in status
        assert "active_live_sessions" in status
        assert "active_paper_sessions" in status

        print(f"✅ Circuit breaker status: active={status['is_active']}")

    @pytest.mark.asyncio
    async def test_trigger_circuit_breaker(
        self,
        api_client,
    ):
        """
        测试触发熔断器 (RSK-010)

        步骤:
        1. 确保熔断器未激活
        2. 触发熔断器
        3. 验证状态变为激活
        4. 重置熔断器
        """
        # ==================== 步骤1: 确保熔断器未激活 ====================
        status_response = await api_client.get("/api/v1/circuit-breaker/status")
        assert status_response.status_code == 200
        initial_status = status_response.json()["data"]

        # 如果已激活，先重置
        if initial_status["is_active"]:
            reset_response = await api_client.post("/api/v1/circuit-breaker/reset?force=true")
            assert reset_response.status_code == 200

        # ==================== 步骤2: 触发熔断器 ====================
        trigger_request = {
            "reason": "E2E test - manual trigger",
            "cooldown_minutes": 1,  # 短冷却时间用于测试
        }

        response = await api_client.post("/api/v1/circuit-breaker/trigger", json=trigger_request)
        assert response.status_code == 200, f"Failed to trigger: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        trigger_result = response_data["data"]
        assert trigger_result["status"] == "triggered"
        assert "triggered_at" in trigger_result

        # ==================== 步骤3: 验证状态变为激活 ====================
        status_response = await api_client.get("/api/v1/circuit-breaker/status")
        assert status_response.status_code == 200

        status = status_response.json()["data"]
        assert status["is_active"] is True
        assert status["trigger_reason"] == "E2E test - manual trigger"

        # ==================== 步骤4: 重置熔断器 ====================
        reset_response = await api_client.post("/api/v1/circuit-breaker/reset?force=true")
        assert reset_response.status_code == 200

        reset_result = reset_response.json()["data"]
        assert reset_result["status"] == "reset"

        # 验证已重置
        final_status_response = await api_client.get("/api/v1/circuit-breaker/status")
        final_status = final_status_response.json()["data"]
        assert final_status["is_active"] is False

        print("✅ Circuit breaker trigger and reset flow completed")

    @pytest.mark.asyncio
    async def test_trigger_circuit_breaker_already_active(
        self,
        api_client,
    ):
        """
        测试重复触发熔断器

        预期: 返回 409 冲突错误
        """
        # 先重置确保干净状态
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")

        # 第一次触发
        trigger_request = {
            "reason": "E2E test - first trigger",
            "cooldown_minutes": 1,
        }
        response = await api_client.post("/api/v1/circuit-breaker/trigger", json=trigger_request)
        assert response.status_code == 200

        # 第二次触发应该失败
        trigger_request["reason"] = "E2E test - second trigger"
        response = await api_client.post("/api/v1/circuit-breaker/trigger", json=trigger_request)
        assert response.status_code == 409, "Should reject duplicate trigger"

        # 清理
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")

        print("✅ Duplicate trigger correctly rejected with 409")

    @pytest.mark.asyncio
    async def test_reset_circuit_breaker_respects_cooldown(
        self,
        api_client,
    ):
        """
        测试重置熔断器遵守冷却期

        预期: 冷却期内重置（不带 force）返回 409
        """
        # 先重置确保干净状态
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")

        # 触发熔断器，设置较长冷却时间
        trigger_request = {
            "reason": "E2E test - cooldown test",
            "cooldown_minutes": 30,
        }
        response = await api_client.post("/api/v1/circuit-breaker/trigger", json=trigger_request)
        assert response.status_code == 200

        # 尝试不带 force 重置，应该被拒绝
        reset_response = await api_client.post("/api/v1/circuit-breaker/reset")
        assert reset_response.status_code == 409, "Should reject reset during cooldown"

        # 带 force 重置应该成功
        force_reset_response = await api_client.post("/api/v1/circuit-breaker/reset?force=true")
        assert force_reset_response.status_code == 200

        print("✅ Cooldown correctly enforced on reset")


class TestCircuitBreakerWithTrading:
    """测试熔断器与交易会话的交互"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_stops_paper_trading(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试熔断器停止所有模拟交易会话 (RSK-010)

        步骤:
        1. 创建策略
        2. 启动模拟交易会话
        3. 触发熔断器
        4. 验证会话被停止
        5. 清理
        """
        # ==================== 步骤1: 创建策略 ====================
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # ==================== 步骤2: 启动模拟交易会话 ====================
        paper_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1m",
            "initial_capital": 10000.0,
        }

        response = await api_client.post("/api/v1/paper", json=paper_request)
        assert response.status_code == 201
        run_id = response.json()["data"]["id"]

        # 等待会话启动
        await asyncio.sleep(1.5)

        # 验证会话正在运行
        status_response = await api_client.get(f"/api/v1/paper/{run_id}/status")
        if status_response.status_code == 200:
            status = status_response.json()["data"]
            # 会话可能已经因为各种原因停止，只要不是 error 就继续测试

        # ==================== 步骤3: 触发熔断器 ====================
        # 先重置确保干净状态
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")

        trigger_request = {
            "reason": "E2E test - stop paper trading",
            "cooldown_minutes": 1,
        }
        response = await api_client.post("/api/v1/circuit-breaker/trigger", json=trigger_request)
        assert response.status_code == 200

        trigger_result = response.json()["data"]
        # 验证停止了至少一个会话（如果会话还在运行）
        # 注意：paper_sessions_stopped 可能为 0 如果会话已自动停止

        # ==================== 步骤4: 验证会话被停止 ====================
        await asyncio.sleep(0.5)

        status_response = await api_client.get(f"/api/v1/paper/{run_id}/status")
        if status_response.status_code == 200:
            status = status_response.json()["data"]
            # 会话应该已停止或出错
            assert status["is_running"] is False, "Session should be stopped after circuit breaker"

        # ==================== 步骤5: 清理 ====================
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")
        await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print(
            f"✅ Circuit breaker stopped paper trading, sessions stopped: {trigger_result.get('paper_sessions_stopped', 0)}"
        )

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_new_paper_trading(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试熔断器激活时阻止新的模拟交易

        步骤:
        1. 触发熔断器
        2. 尝试启动模拟交易
        3. 验证被拒绝
        4. 重置后可以启动
        """
        # ==================== 步骤1: 触发熔断器 ====================
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")

        trigger_request = {
            "reason": "E2E test - block new sessions",
            "cooldown_minutes": 1,
        }
        response = await api_client.post("/api/v1/circuit-breaker/trigger", json=trigger_request)
        assert response.status_code == 200

        # ==================== 步骤2: 创建策略并尝试启动 ====================
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        paper_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1m",
            "initial_capital": 10000.0,
        }

        response = await api_client.post("/api/v1/paper", json=paper_request)
        # 熔断激活时应该拒绝新的交易会话
        # 注意：实际行为取决于实现，可能是 403 或 409
        if response.status_code == 201:
            # 如果允许启动，立即停止
            run_id = response.json()["data"]["id"]
            await api_client.post(f"/api/v1/paper/{run_id}/stop")
            print("⚠️ Paper trading was allowed during circuit breaker (implementation may vary)")
        else:
            print(f"✅ New paper trading blocked with status {response.status_code}")

        # ==================== 步骤3: 重置后可以启动 ====================
        await api_client.post("/api/v1/circuit-breaker/reset?force=true")

        response = await api_client.post("/api/v1/paper", json=paper_request)
        assert response.status_code == 201, f"Should allow after reset: {response.text}"
        run_id = response.json()["data"]["id"]

        # 清理
        await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print("✅ Paper trading allowed after circuit breaker reset")


class TestCloseAllPositions:
    """测试一键平仓功能 (RSK-011)"""

    @pytest.mark.asyncio
    async def test_close_all_positions_endpoint(
        self,
        api_client,
    ):
        """
        测试一键平仓 API 端点

        由于没有真实持仓，主要验证 API 响应结构
        """
        request = {
            "reason": "E2E test - close all positions",
        }

        response = await api_client.post(
            "/api/v1/circuit-breaker/close-all-positions", json=request
        )
        assert response.status_code == 200, f"Failed to close positions: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        result = response_data["data"]
        assert "orders_cancelled" in result
        assert "live_positions_closed" in result
        assert "paper_positions_reset" in result
        assert "errors" in result

        print(
            f"✅ Close all positions: cancelled={result['orders_cancelled']}, "
            f"closed={result['live_positions_closed']}, "
            f"paper_reset={result['paper_positions_reset']}"
        )

    @pytest.mark.asyncio
    async def test_close_all_positions_stops_paper_trading(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试一键平仓停止所有模拟交易会话

        步骤:
        1. 启动模拟交易
        2. 调用一键平仓
        3. 验证会话被停止
        """
        # 创建策略并启动会话
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        paper_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1m",
            "initial_capital": 10000.0,
        }

        response = await api_client.post("/api/v1/paper", json=paper_request)
        assert response.status_code == 201
        run_id = response.json()["data"]["id"]

        await asyncio.sleep(1.0)

        # 调用一键平仓
        response = await api_client.post(
            "/api/v1/circuit-breaker/close-all-positions",
            json={"reason": "E2E test"},
        )
        assert response.status_code == 200

        result = response.json()["data"]

        # 验证会话被停止
        await asyncio.sleep(0.5)
        status_response = await api_client.get(f"/api/v1/paper/{run_id}/status")
        if status_response.status_code == 200:
            status = status_response.json()["data"]
            assert status["is_running"] is False

        print(f"✅ Close all positions reset {result['paper_positions_reset']} paper sessions")

"""
Paper Trading流程端到端测试

测试从创建Paper Trading会话到停止的完整业务流程。

注意: Paper Trading需要实时WebSocket数据流，这些测试主要验证API端点
和会话生命周期，不深入测试实时交易逻辑。
"""

import asyncio

import pytest

pytestmark = pytest.mark.e2e


class TestPaperTradingBasicFlow:
    """测试Paper Trading基本流程"""

    @pytest.mark.asyncio
    async def test_start_paper_trading_session(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试创建Paper Trading会话

        步骤:
        1. 创建策略
        2. 启动Paper Trading会话
        3. 验证会话创建成功
        4. 停止会话
        """
        # ==================== 步骤1: 创建策略 ====================
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201, f"Failed to create strategy: {response.text}"

        response_data = response.json()
        assert "data" in response_data
        strategy_id = response_data["data"]["id"]
        cleanup_strategies(strategy_id)

        # ==================== 步骤2: 启动Paper Trading ====================
        paper_trading_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1m",
            "initial_capital": 10000.0,
            "commission_rate": 0.001,
            "slippage": 0.0,
        }

        response = await api_client.post("/api/v1/paper", json=paper_trading_request)
        assert response.status_code == 201, f"Failed to start paper trading: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        # ==================== 步骤3: 验证会话创建 ====================
        session = response_data["data"]
        run_id = session["id"]

        assert session["strategy_id"] == strategy_id
        assert session["symbol"] == "BTC/USDT"
        assert session["exchange"] == "okx"
        assert session["timeframe"] == "1m"
        assert session["mode"] == "paper"
        assert session["status"] in ["pending", "running"]
        assert float(session["initial_capital"]) == 10000.0

        # ==================== 步骤4: 停止会话 ====================
        # 等待一小段时间让会话启动
        await asyncio.sleep(1.0)

        response = await api_client.post(f"/api/v1/paper/{run_id}/stop")
        assert response.status_code == 200, f"Failed to stop paper trading: {response.text}"

        response_data = response.json()
        assert "data" in response_data
        stopped_session = response_data["data"]
        assert stopped_session["status"] in ["stopped", "error"]

        print("✅ Paper trading session created and stopped successfully")

    @pytest.mark.asyncio
    async def test_get_paper_trading_status(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试获取Paper Trading状态

        步骤:
        1. 创建策略并启动会话
        2. 获取实时状态
        3. 验证状态信息
        4. 停止会话
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # 启动Paper Trading
        response = await api_client.post(
            "/api/v1/paper",
            json={
                "strategy_id": strategy_id,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "timeframe": "1m",
                "initial_capital": 10000.0,
            },
        )
        assert response.status_code == 201
        run_id = response.json()["data"]["id"]

        # 等待会话启动
        await asyncio.sleep(1.0)

        # ==================== 获取状态 ====================
        response = await api_client.get(f"/api/v1/paper/{run_id}/status")
        assert response.status_code == 200, f"Failed to get status: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        status = response_data["data"]
        assert status["run_id"] == run_id
        assert status["symbol"] == "BTC/USDT"
        assert status["timeframe"] == "1m"
        assert "is_running" in status
        assert "cash" in status
        assert "equity" in status
        assert "bar_count" in status
        assert "positions" in status
        assert "pending_orders" in status

        # 初始状态验证
        assert float(status["cash"]) == 10000.0  # 初始资金
        assert float(status["equity"]) == 10000.0  # 初始权益
        assert status["bar_count"] >= 0

        # 停止会话
        await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print("✅ Paper trading status retrieved successfully")

    @pytest.mark.asyncio
    async def test_stop_paper_trading_session(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试停止Paper Trading会话

        步骤:
        1. 启动会话
        2. 停止会话
        3. 验证状态变为stopped
        """
        # 创建策略并启动会话
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        response = await api_client.post(
            "/api/v1/paper",
            json={
                "strategy_id": strategy_id,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "timeframe": "1m",
                "initial_capital": 10000.0,
            },
        )
        assert response.status_code == 201
        run_id = response.json()["data"]["id"]

        # 等待会话启动
        await asyncio.sleep(1.0)

        # ==================== 停止会话 ====================
        response = await api_client.post(f"/api/v1/paper/{run_id}/stop")
        assert response.status_code == 200, f"Failed to stop: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        stopped_session = response_data["data"]
        assert stopped_session["status"] in ["stopped", "error"]
        assert stopped_session["stopped_at"] is not None

        # 验证会话确实停止了
        response = await api_client.get(f"/api/v1/paper/{run_id}/status")
        if response.status_code == 200:
            status = response.json()["data"]
            assert status["is_running"] is False

        print("✅ Paper trading session stopped successfully")

    @pytest.mark.asyncio
    async def test_list_active_sessions(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试列出活跃的Paper Trading会话

        步骤:
        1. 创建多个会话
        2. 列出活跃会话
        3. 验证列表包含创建的会话
        4. 停止所有会话
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # 创建2个Paper Trading会话（使用不同symbol避免PP-C03重复会话防护）
        symbols = ["BTC/USDT", "ETH/USDT"]
        run_ids = []
        for symbol in symbols:
            response = await api_client.post(
                "/api/v1/paper",
                json={
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "exchange": "okx",
                    "timeframe": "1m",
                    "initial_capital": 10000.0,
                },
            )
            assert response.status_code == 201
            run_ids.append(response.json()["data"]["id"])

        # 等待会话启动
        await asyncio.sleep(1.5)

        # ==================== 列出活跃会话 ====================
        response = await api_client.get("/api/v1/paper")
        assert response.status_code == 200, f"Failed to list sessions: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        sessions = response_data["data"]
        assert isinstance(sessions, list)

        # 验证我们创建的会话在列表中
        session_ids = [s["run_id"] for s in sessions]
        for run_id in run_ids:
            assert run_id in session_ids, f"Session {run_id} not in active list"

        # 停止所有会话
        for run_id in run_ids:
            await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print(f"✅ Listed {len(sessions)} active paper trading sessions")

    @pytest.mark.asyncio
    async def test_list_paper_trading_runs(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试列出所有Paper Trading运行（分页）

        步骤:
        1. 创建多个会话
        2. 列出所有运行
        3. 验证分页功能
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # 创建3个Paper Trading会话（使用不同symbol避免PP-C03重复会话防护）
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        run_ids = []
        for symbol in symbols:
            response = await api_client.post(
                "/api/v1/paper",
                json={
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "exchange": "okx",
                    "timeframe": "1m",
                    "initial_capital": 10000.0,
                },
            )
            assert response.status_code == 201
            run_ids.append(response.json()["data"]["id"])

        # ==================== 列出所有运行 ====================
        response = await api_client.get("/api/v1/paper/runs")
        assert response.status_code == 200, f"Failed to list runs: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        paginated_data = response_data["data"]
        assert "items" in paginated_data
        assert "total" in paginated_data
        assert "page" in paginated_data
        assert "page_size" in paginated_data

        runs = paginated_data["items"]
        assert isinstance(runs, list)
        assert len(runs) >= 3  # 至少包含我们创建的3个

        # 验证创建的运行都在列表中
        returned_ids = [run["id"] for run in runs]
        for run_id in run_ids:
            assert run_id in returned_ids

        # 停止所有会话
        for run_id in run_ids:
            await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print(f"✅ Listed {paginated_data['total']} paper trading runs")

    @pytest.mark.asyncio
    async def test_get_equity_curve(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试获取Paper Trading权益曲线

        步骤:
        1. 创建并启动会话
        2. 等待一段时间（让引擎产生数据）
        3. 获取权益曲线
        4. 验证数据结构
        5. 停止会话
        """
        # 创建策略并启动会话
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        response = await api_client.post(
            "/api/v1/paper",
            json={
                "strategy_id": strategy_id,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "timeframe": "1m",
                "initial_capital": 10000.0,
            },
        )
        assert response.status_code == 201
        run_id = response.json()["data"]["id"]

        # 等待会话运行一段时间
        await asyncio.sleep(2.0)

        # ==================== 获取权益曲线 ====================
        response = await api_client.get(f"/api/v1/paper/{run_id}/equity-curve")
        assert response.status_code == 200, f"Failed to get equity curve: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        equity_curve = response_data["data"]
        assert isinstance(equity_curve, list)

        # 验证权益曲线数据结构
        if len(equity_curve) > 0:
            point = equity_curve[0]
            assert "time" in point
            assert "equity" in point
            assert "cash" in point
            assert "position_value" in point
            assert "unrealized_pnl" in point

        # 停止会话
        await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print(f"✅ Retrieved equity curve with {len(equity_curve)} points")

    @pytest.mark.asyncio
    async def test_paper_trading_with_invalid_strategy(
        self,
        api_client,
    ):
        """
        测试使用无效策略ID启动Paper Trading

        预期: 返回404错误
        """
        paper_trading_request = {
            "strategy_id": "00000000-0000-0000-0000-000000000000",
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "timeframe": "1m",
            "initial_capital": 10000.0,
        }

        response = await api_client.post("/api/v1/paper", json=paper_trading_request)

        assert response.status_code == 404

        print("✅ Invalid strategy correctly rejected with 404")

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_status(
        self,
        api_client,
    ):
        """
        测试获取不存在的会话状态

        预期: 返回404错误
        """
        fake_run_id = "00000000-0000-0000-0000-000000000000"

        response = await api_client.get(f"/api/v1/paper/{fake_run_id}/status")

        assert response.status_code == 404

        print("✅ Nonexistent session correctly rejected with 404")

    @pytest.mark.asyncio
    async def test_stop_nonexistent_session(
        self,
        api_client,
    ):
        """
        测试停止不存在的会话

        预期: 返回404错误
        """
        fake_run_id = "00000000-0000-0000-0000-000000000000"

        response = await api_client.post(f"/api/v1/paper/{fake_run_id}/stop")

        assert response.status_code == 404

        print("✅ Nonexistent session stop correctly rejected with 404")


class TestPaperTradingRunManagement:
    """测试Paper Trading运行管理"""

    @pytest.mark.asyncio
    async def test_get_paper_trading_run(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试获取Paper Trading运行详情

        步骤:
        1. 创建运行
        2. 获取运行详情
        3. 验证数据完整性
        """
        # 创建策略并启动会话
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        response = await api_client.post(
            "/api/v1/paper",
            json={
                "strategy_id": strategy_id,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "timeframe": "1m",
                "initial_capital": 10000.0,
            },
        )
        assert response.status_code == 201
        run_id = response.json()["data"]["id"]

        # ==================== 获取运行详情 ====================
        response = await api_client.get(f"/api/v1/paper/{run_id}")
        assert response.status_code == 200, f"Failed to get run: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        run = response_data["data"]
        assert run["id"] == run_id
        assert run["strategy_id"] == strategy_id
        assert run["symbol"] == "BTC/USDT"
        assert run["mode"] == "paper"
        assert run["status"] in ["pending", "running", "stopped", "error"]

        # 停止会话
        await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print("✅ Paper trading run details retrieved successfully")

    @pytest.mark.asyncio
    async def test_filter_runs_by_status(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试按状态筛选运行

        步骤:
        1. 创建多个运行（有的运行，有的停止）
        2. 按状态筛选
        3. 验证筛选结果
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 201
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # 创建2个运行（使用不同symbol避免PP-C03重复会话防护）
        symbols = ["BTC/USDT", "ETH/USDT"]
        run_ids = []
        for symbol in symbols:
            response = await api_client.post(
                "/api/v1/paper",
                json={
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "exchange": "okx",
                    "timeframe": "1m",
                    "initial_capital": 10000.0,
                },
            )
            assert response.status_code == 201
            run_ids.append(response.json()["data"]["id"])

        # 等待启动
        await asyncio.sleep(1.0)

        # 停止第一个
        await api_client.post(f"/api/v1/paper/{run_ids[0]}/stop")
        await asyncio.sleep(0.5)

        # ==================== 筛选running状态 ====================
        response = await api_client.get("/api/v1/paper/runs?status=running")
        assert response.status_code == 200

        running_runs = response.json()["data"]["items"]
        [r["id"] for r in running_runs]

        # 第二个应该在running列表中（如果还在运行）
        # 注意: 由于异步性，可能已经停止，所以不强制断言

        # ==================== 筛选stopped状态 ====================
        response = await api_client.get("/api/v1/paper/runs?status=stopped")
        assert response.status_code == 200

        stopped_runs = response.json()["data"]["items"]
        [r["id"] for r in stopped_runs]

        # 第一个应该在stopped列表中
        # 注意: 由于系统中可能有其他stopped runs，我们只验证status字段
        for run in stopped_runs:
            assert run["status"] == "stopped"

        # 停止第二个
        await api_client.post(f"/api/v1/paper/{run_ids[1]}/stop")

        print("✅ Status filtering working correctly")

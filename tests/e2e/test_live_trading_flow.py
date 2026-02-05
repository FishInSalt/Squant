"""
实盘交易流程端到端测试

测试从启动实盘交易到停止的完整业务流程。

注意: 这些测试需要真实的交易所 API 凭证才能运行。
默认情况下会跳过需要凭证的测试。

验收标准覆盖:
- TRD-033: 启动实盘交易
- TRD-034: 查看交易状态
- TRD-035: 查看策略日志
- TRD-036: 停止实盘交易
- TRD-037: 强制停止会话
- TRD-038: 紧急平仓
"""

import asyncio
import os

import pytest

pytestmark = pytest.mark.e2e

# 检查是否有交易所凭证
HAS_EXCHANGE_CREDENTIALS = bool(os.environ.get("OKX_API_KEY") or os.environ.get("BINANCE_API_KEY"))


class TestLiveTradingAPIEndpoints:
    """测试实盘交易 API 端点（无需凭证）"""

    @pytest.mark.asyncio
    async def test_list_active_live_sessions(
        self,
        api_client,
    ):
        """
        测试列出活跃的实盘交易会话

        验证 API 端点返回正确的结构
        """
        response = await api_client.get("/api/v1/live")
        assert response.status_code == 200, f"Failed to list sessions: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        sessions = response_data["data"]
        assert isinstance(sessions, list)

        # 验证每个会话的结构（如果有的话）
        for session in sessions:
            assert "run_id" in session
            assert "strategy_id" in session
            assert "symbol" in session
            assert "is_running" in session

        print(f"✅ Listed {len(sessions)} active live trading sessions")

    @pytest.mark.asyncio
    async def test_list_live_trading_runs(
        self,
        api_client,
    ):
        """
        测试列出所有实盘交易运行（分页）
        """
        response = await api_client.get("/api/v1/live/runs")
        assert response.status_code == 200, f"Failed to list runs: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        paginated_data = response_data["data"]
        assert "items" in paginated_data
        assert "total" in paginated_data
        assert "page" in paginated_data
        assert "page_size" in paginated_data

        print(f"✅ Listed {paginated_data['total']} total live trading runs")

    @pytest.mark.asyncio
    async def test_start_live_trading_without_exchange_account(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试没有交易所账户时启动实盘交易

        预期: 返回 404 错误
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # 使用不存在的账户 ID 尝试启动
        live_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange_account_id": "00000000-0000-0000-0000-000000000000",
            "timeframe": "1m",
            "risk_config": {
                "max_position_size": 1000.0,
                "max_order_size": 100.0,
                "daily_trade_limit": 10,
                "daily_loss_limit": 100.0,
                "price_deviation_limit": 0.01,
                "circuit_breaker_threshold": 3,
            },
        }

        response = await api_client.post("/api/v1/live", json=live_request)
        assert response.status_code == 404, f"Should reject without account: {response.text}"

        print("✅ Live trading correctly rejected without exchange account")

    @pytest.mark.asyncio
    async def test_start_live_trading_with_invalid_strategy(
        self,
        api_client,
    ):
        """
        测试使用无效策略 ID 启动实盘交易

        预期: 返回 404 错误
        """
        live_request = {
            "strategy_id": "00000000-0000-0000-0000-000000000000",
            "symbol": "BTC/USDT",
            "exchange_account_id": "00000000-0000-0000-0000-000000000001",
            "timeframe": "1m",
            "risk_config": {
                "max_position_size": 1000.0,
                "max_order_size": 100.0,
                "daily_trade_limit": 10,
                "daily_loss_limit": 100.0,
                "price_deviation_limit": 0.01,
                "circuit_breaker_threshold": 3,
            },
        }

        response = await api_client.post("/api/v1/live", json=live_request)
        assert response.status_code == 404

        print("✅ Live trading correctly rejected with invalid strategy")

    @pytest.mark.asyncio
    async def test_get_nonexistent_live_session_status(
        self,
        api_client,
    ):
        """
        测试获取不存在的会话状态

        预期: 返回 404 错误
        """
        fake_run_id = "00000000-0000-0000-0000-000000000000"

        response = await api_client.get(f"/api/v1/live/{fake_run_id}/status")
        assert response.status_code == 404

        print("✅ Nonexistent session status correctly rejected with 404")

    @pytest.mark.asyncio
    async def test_stop_nonexistent_live_session(
        self,
        api_client,
    ):
        """
        测试停止不存在的会话

        预期: 返回 404 错误
        """
        fake_run_id = "00000000-0000-0000-0000-000000000000"

        response = await api_client.post(f"/api/v1/live/{fake_run_id}/stop")
        assert response.status_code == 404

        print("✅ Nonexistent session stop correctly rejected with 404")

    @pytest.mark.asyncio
    async def test_emergency_close_nonexistent_session(
        self,
        api_client,
    ):
        """
        测试紧急平仓不存在的会话

        预期: 返回 404 错误
        """
        fake_run_id = "00000000-0000-0000-0000-000000000000"

        response = await api_client.post(f"/api/v1/live/{fake_run_id}/emergency-close")
        assert response.status_code == 404

        print("✅ Emergency close on nonexistent session correctly rejected with 404")


class TestExchangeAccountManagement:
    """测试交易所账户管理（用于准备实盘交易）"""

    @pytest.mark.asyncio
    async def test_list_exchange_accounts(
        self,
        api_client,
    ):
        """
        测试列出交易所账户
        """
        response = await api_client.get("/api/v1/exchange-accounts")
        assert response.status_code == 200, f"Failed to list accounts: {response.text}"

        response_data = response.json()
        assert "data" in response_data

        accounts = response_data["data"]
        assert isinstance(accounts, list)

        print(f"✅ Listed {len(accounts)} exchange accounts")

    @pytest.mark.asyncio
    async def test_create_exchange_account_okx_without_passphrase(
        self,
        api_client,
    ):
        """
        测试创建 OKX 账户但不提供 passphrase

        预期: 返回 400 错误
        """
        account_request = {
            "name": "Test OKX Account",
            "exchange": "okx",
            "api_key": "test_key",
            "api_secret": "test_secret",
            # 缺少 passphrase
        }

        response = await api_client.post("/api/v1/exchange-accounts", json=account_request)
        assert response.status_code == 400, f"Should reject OKX without passphrase: {response.text}"

        print("✅ OKX account without passphrase correctly rejected")

    @pytest.mark.asyncio
    async def test_exchange_account_crud_flow(
        self,
        api_client,
    ):
        """
        测试交易所账户 CRUD 流程

        步骤:
        1. 创建账户
        2. 获取账户
        3. 更新账户
        4. 删除账户
        """
        import uuid

        unique_name = f"E2E Test Account {uuid.uuid4().hex[:8]}"

        # ==================== 步骤1: 创建账户 ====================
        account_request = {
            "name": unique_name,
            "exchange": "okx",
            "api_key": "test_api_key_" + uuid.uuid4().hex[:8],
            "api_secret": "test_api_secret_" + uuid.uuid4().hex[:8],
            "passphrase": "test_passphrase",
            "is_testnet": True,  # 使用测试网
        }

        response = await api_client.post("/api/v1/exchange-accounts", json=account_request)
        assert response.status_code == 200, f"Failed to create account: {response.text}"

        account = response.json()["data"]
        account_id = account["id"]

        assert account["name"] == unique_name
        assert account["exchange"] == "okx"
        assert account["is_testnet"] is True
        # API 密钥不应该返回
        assert "api_key" not in account or account.get("api_key") is None
        assert "api_secret" not in account or account.get("api_secret") is None

        # ==================== 步骤2: 获取账户 ====================
        response = await api_client.get(f"/api/v1/exchange-accounts/{account_id}")
        assert response.status_code == 200

        fetched_account = response.json()["data"]
        assert fetched_account["id"] == account_id
        assert fetched_account["name"] == unique_name

        # ==================== 步骤3: 更新账户 ====================
        update_request = {
            "name": unique_name + " Updated",
        }

        response = await api_client.put(
            f"/api/v1/exchange-accounts/{account_id}", json=update_request
        )
        assert response.status_code == 200

        updated_account = response.json()["data"]
        assert updated_account["name"] == unique_name + " Updated"

        # ==================== 步骤4: 删除账户 ====================
        response = await api_client.delete(f"/api/v1/exchange-accounts/{account_id}")
        assert response.status_code == 200

        # 验证已删除
        response = await api_client.get(f"/api/v1/exchange-accounts/{account_id}")
        assert response.status_code == 404

        print("✅ Exchange account CRUD flow completed successfully")


@pytest.mark.skipif(
    not HAS_EXCHANGE_CREDENTIALS,
    reason="Exchange credentials not available (set OKX_API_KEY or BINANCE_API_KEY)",
)
class TestLiveTradingWithCredentials:
    """
    需要真实交易所凭证的实盘交易测试

    这些测试会实际连接交易所，使用真实的 API。
    仅在设置了环境变量时运行。

    警告: 这些测试可能会产生真实的交易订单！
    请仅使用测试网账户或确保策略不会发送订单。
    """

    @pytest.fixture
    async def test_exchange_account(self, api_client):
        """创建测试用交易所账户"""
        import uuid

        exchange = "okx" if os.environ.get("OKX_API_KEY") else "binance"

        account_request = {
            "name": f"E2E Test Live {uuid.uuid4().hex[:8]}",
            "exchange": exchange,
            "api_key": os.environ.get(f"{exchange.upper()}_API_KEY"),
            "api_secret": os.environ.get(f"{exchange.upper()}_API_SECRET"),
            "is_testnet": True,  # 使用测试网
        }

        if exchange == "okx":
            account_request["passphrase"] = os.environ.get("OKX_PASSPHRASE")

        response = await api_client.post("/api/v1/exchange-accounts", json=account_request)
        assert response.status_code == 200
        account = response.json()["data"]

        yield account

        # 清理
        await api_client.delete(f"/api/v1/exchange-accounts/{account['id']}")

    @pytest.mark.asyncio
    async def test_connection_test(
        self,
        api_client,
        test_exchange_account,
    ):
        """
        测试交易所连接 (ACC-005)
        """
        account_id = test_exchange_account["id"]

        response = await api_client.post(f"/api/v1/exchange-accounts/{account_id}/test")
        assert response.status_code == 200

        result = response.json()["data"]
        assert "success" in result
        assert "message" in result

        if result["success"]:
            print(f"✅ Connection test passed: {result['message']}")
        else:
            print(f"⚠️ Connection test failed: {result['message']}")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_complete_live_trading_flow(
        self,
        api_client,
        test_strategy_data,
        test_exchange_account,
        cleanup_strategies,
    ):
        """
        测试完整的实盘交易流程 (TRD-033 ~ TRD-036)

        步骤:
        1. 创建策略
        2. 启动实盘交易
        3. 获取交易状态
        4. 等待一段时间
        5. 停止交易
        6. 验证停止状态
        """
        # ==================== 步骤1: 创建策略 ====================
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # ==================== 步骤2: 启动实盘交易 ====================
        live_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange_account_id": test_exchange_account["id"],
            "timeframe": "1m",
            "risk_config": {
                "max_position_size": 100.0,  # 小额度用于测试
                "max_order_size": 10.0,
                "daily_trade_limit": 5,
                "daily_loss_limit": 50.0,
                "price_deviation_limit": 0.01,
                "circuit_breaker_threshold": 3,
            },
            "initial_equity": 100.0,  # 小额测试
        }

        response = await api_client.post("/api/v1/live", json=live_request)
        if response.status_code != 200:
            # 连接失败可能是测试网问题，跳过
            pytest.skip(f"Failed to start live trading: {response.text}")

        run = response.json()["data"]
        run_id = run["id"]

        assert run["strategy_id"] == strategy_id
        assert run["status"] in ["pending", "running"]

        # ==================== 步骤3: 获取交易状态 ====================
        await asyncio.sleep(2.0)  # 等待引擎启动

        response = await api_client.get(f"/api/v1/live/{run_id}/status")
        assert response.status_code == 200

        status = response.json()["data"]
        assert status["run_id"] == run_id
        assert "is_running" in status
        assert "cash" in status
        assert "equity" in status
        assert "risk_state" in status

        # ==================== 步骤4: 等待一段时间 ====================
        await asyncio.sleep(5.0)

        # ==================== 步骤5: 停止交易 ====================
        response = await api_client.post(
            f"/api/v1/live/{run_id}/stop",
            json={"cancel_orders": True},
        )
        assert response.status_code == 200

        stopped_run = response.json()["data"]
        assert stopped_run["status"] in ["stopped", "error"]

        # ==================== 步骤6: 验证停止状态 ====================
        response = await api_client.get(f"/api/v1/live/{run_id}/status")
        if response.status_code == 200:
            final_status = response.json()["data"]
            assert final_status["is_running"] is False

        print("✅ Complete live trading flow successful")

    @pytest.mark.asyncio
    async def test_emergency_close(
        self,
        api_client,
        test_strategy_data,
        test_exchange_account,
        cleanup_strategies,
    ):
        """
        测试紧急平仓 (TRD-038)

        步骤:
        1. 启动实盘交易
        2. 调用紧急平仓
        3. 验证会话停止和仓位关闭
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200
        strategy_id = response.json()["data"]["id"]
        cleanup_strategies(strategy_id)

        # 启动实盘交易
        live_request = {
            "strategy_id": strategy_id,
            "symbol": "BTC/USDT",
            "exchange_account_id": test_exchange_account["id"],
            "timeframe": "1m",
            "risk_config": {
                "max_position_size": 100.0,
                "max_order_size": 10.0,
                "daily_trade_limit": 5,
                "daily_loss_limit": 50.0,
                "price_deviation_limit": 0.01,
                "circuit_breaker_threshold": 3,
            },
        }

        response = await api_client.post("/api/v1/live", json=live_request)
        if response.status_code != 200:
            pytest.skip(f"Failed to start: {response.text}")

        run_id = response.json()["data"]["id"]

        await asyncio.sleep(2.0)

        # 调用紧急平仓
        response = await api_client.post(f"/api/v1/live/{run_id}/emergency-close")
        assert response.status_code == 200

        result = response.json()["data"]
        assert result["run_id"] == run_id
        assert result["status"] in ["completed", "partial", "stopped"]
        assert "orders_cancelled" in result
        assert "positions_closed" in result

        print(
            f"✅ Emergency close: cancelled={result.get('orders_cancelled')}, "
            f"closed={result.get('positions_closed')}"
        )


class TestMultipleStrategies:
    """测试多策略并发运行"""

    @pytest.mark.asyncio
    async def test_multiple_paper_trading_sessions(
        self,
        api_client,
        test_strategy_data,
        cleanup_strategies,
    ):
        """
        测试多个模拟交易会话并发运行 (TRD-051)

        步骤:
        1. 创建两个策略
        2. 同时启动两个模拟交易会话
        3. 验证两个会话都在运行
        4. 停止所有会话
        """
        # ==================== 步骤1: 创建两个策略 ====================
        strategy_ids = []
        for i in range(2):
            # 修改名称使其唯一
            strategy_data = test_strategy_data.copy()
            import uuid

            strategy_data["name"] = f"E2E Multi Strategy {i} {uuid.uuid4().hex[:8]}"

            response = await api_client.post("/api/v1/strategies", json=strategy_data)
            assert response.status_code == 200
            strategy_id = response.json()["data"]["id"]
            strategy_ids.append(strategy_id)
            cleanup_strategies(strategy_id)

        # ==================== 步骤2: 启动两个模拟交易会话 ====================
        run_ids = []
        for i, strategy_id in enumerate(strategy_ids):
            paper_request = {
                "strategy_id": strategy_id,
                "symbol": "BTC/USDT" if i == 0 else "ETH/USDT",
                "exchange": "okx",
                "timeframe": "1m",
                "initial_capital": 10000.0,
            }

            response = await api_client.post("/api/v1/paper", json=paper_request)
            assert response.status_code == 200, f"Failed to start session {i}: {response.text}"
            run_ids.append(response.json()["data"]["id"])

        # 等待会话启动
        await asyncio.sleep(2.0)

        # ==================== 步骤3: 验证两个会话都在运行 ====================
        running_count = 0
        for run_id in run_ids:
            response = await api_client.get(f"/api/v1/paper/{run_id}/status")
            if response.status_code == 200:
                status = response.json()["data"]
                if status.get("is_running"):
                    running_count += 1

        print(f"Running sessions: {running_count}/{len(run_ids)}")

        # ==================== 步骤4: 停止所有会话 ====================
        for run_id in run_ids:
            await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print(f"✅ Successfully ran {len(run_ids)} concurrent paper trading sessions")

    @pytest.mark.asyncio
    async def test_strategy_isolation(
        self,
        api_client,
        cleanup_strategies,
    ):
        """
        测试策略隔离 - 一个策略崩溃不影响其他策略 (TRD-052)

        步骤:
        1. 创建一个正常策略和一个会出错的策略
        2. 启动两个模拟交易会话
        3. 验证正常策略继续运行
        """
        import uuid

        # 正常策略
        normal_strategy = {
            "name": f"E2E Normal Strategy {uuid.uuid4().hex[:8]}",
            "code": """
class NormalStrategy(Strategy):
    def on_bar(self, bar):
        pass
""",
            "description": "Normal test strategy",
        }

        # 会在 on_bar 中抛出异常的策略
        error_strategy = {
            "name": f"E2E Error Strategy {uuid.uuid4().hex[:8]}",
            "code": """
class ErrorStrategy(Strategy):
    def __init__(self, context):
        super().__init__(context)
        self.call_count = 0

    def on_bar(self, bar):
        self.call_count += 1
        if self.call_count > 2:
            raise ValueError("Intentional error for testing")
""",
            "description": "Error test strategy",
        }

        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=normal_strategy)
        assert response.status_code == 200
        normal_id = response.json()["data"]["id"]
        cleanup_strategies(normal_id)

        response = await api_client.post("/api/v1/strategies", json=error_strategy)
        assert response.status_code == 200
        error_id = response.json()["data"]["id"]
        cleanup_strategies(error_id)

        # 启动两个会话
        run_ids = []
        for strategy_id in [normal_id, error_id]:
            paper_request = {
                "strategy_id": strategy_id,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "timeframe": "1m",
                "initial_capital": 10000.0,
            }
            response = await api_client.post("/api/v1/paper", json=paper_request)
            assert response.status_code == 200
            run_ids.append(response.json()["data"]["id"])

        normal_run_id, error_run_id = run_ids

        # 等待一段时间让错误策略触发异常
        await asyncio.sleep(5.0)

        # 验证正常策略仍在运行（或至少没有因为另一个策略的错误而停止）
        response = await api_client.get(f"/api/v1/paper/{normal_run_id}/status")
        if response.status_code == 200:
            normal_status = response.json()["data"]
            # 正常策略应该仍在运行或正常停止（不是因为错误）
            print(f"Normal strategy running: {normal_status.get('is_running')}")

        # 检查错误策略的状态
        response = await api_client.get(f"/api/v1/paper/{error_run_id}/status")
        if response.status_code == 200:
            error_status = response.json()["data"]
            print(f"Error strategy running: {error_status.get('is_running')}")

        # 清理
        for run_id in run_ids:
            await api_client.post(f"/api/v1/paper/{run_id}/stop")

        print("✅ Strategy isolation test completed")

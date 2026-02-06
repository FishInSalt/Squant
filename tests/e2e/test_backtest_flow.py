"""
回测流程端到端测试

测试从创建策略到查看回测结果的完整业务流程。
"""

import pytest

pytestmark = pytest.mark.e2e


class TestBacktestCompleteFlow:
    """测试完整的回测流程"""

    @pytest.mark.asyncio
    async def test_complete_backtest_workflow(
        self,
        api_client,
        test_strategy_data,
        test_backtest_config,
        cleanup_strategies,
        wait_for_backtest,
        assert_backtest_metrics,
    ):
        """
        测试完整的回测工作流

        步骤:
        1. 创建策略
        2. 配置回测参数
        3. 启动回测
        4. 等待回测完成
        5. 查看回测结果
        6. 验证指标合理性
        """
        # ==================== 步骤1: 创建策略 ====================
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200, f"Failed to create strategy: {response.text}"

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"

        strategy = response_data["data"]
        strategy_id = strategy["id"]
        cleanup_strategies(strategy_id)

        assert strategy["name"] == test_strategy_data["name"]
        assert strategy["status"] == "active"

        # ==================== 步骤2: 创建回测运行 ====================
        backtest_request = {
            **test_backtest_config,
            "strategy_id": strategy_id,
        }

        response = await api_client.post("/api/v1/backtest/async", json=backtest_request)
        assert response.status_code == 200, f"Failed to create backtest run: {response.text}"

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"

        backtest_run = response_data["data"]
        run_id = backtest_run["id"]

        assert backtest_run["strategy_id"] == strategy_id
        assert backtest_run["status"] == "pending"
        assert backtest_run["symbol"] == test_backtest_config["symbol"]

        # ==================== 步骤3: 启动回测 ====================
        response = await api_client.post(f"/api/v1/backtest/{run_id}/run")
        assert response.status_code == 200, f"Failed to start backtest: {response.text}"

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"

        started_run = response_data["data"]
        # Backtest may complete very quickly, so allow completed status
        assert started_run["status"] in ["running", "pending", "completed"]

        # ==================== 步骤4: 等待回测完成 ====================
        completed_run = await wait_for_backtest(api_client, run_id, timeout=120.0)

        assert completed_run["status"] == "completed", (
            f"Backtest failed with status: {completed_run['status']}"
        )

        # ==================== 步骤5: 获取回测结果 ====================
        response = await api_client.get(f"/api/v1/backtest/{run_id}/detail")
        assert response.status_code == 200, f"Failed to get results: {response.text}"

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"

        results = response_data["data"]

        # ==================== 步骤6: 验证回测结果 ====================
        # 验证结果包含必要的字段
        assert "run" in results, f"Missing 'run' field in results: {results}"
        assert "equity_curve" in results, f"Missing 'equity_curve' field in results: {results}"

        run = results["run"]
        assert "result" in run, f"Missing 'result' field in run: {run}"

        # 验证指标合理性
        metrics = run["result"]
        if metrics:  # Only validate if backtest completed with results
            assert_backtest_metrics(metrics)

        # 验证有权益曲线数据
        assert len(results["equity_curve"]) > 0, "Equity curve should not be empty"

        # 验证权益曲线数据结构
        if len(results["equity_curve"]) > 0:
            point = results["equity_curve"][0]
            assert "time" in point
            assert "equity" in point
            assert "cash" in point

        print("✅ Backtest completed successfully")
        if metrics:
            print(f"   Total Return: {metrics.get('total_return', 'N/A')}")
            print(f"   Total Trades: {metrics.get('total_trades', 'N/A')}")
            print(f"   Max Drawdown: {metrics.get('max_drawdown', 'N/A')}")
            print(f"   Sharpe Ratio: {metrics.get('sharpe_ratio', 'N/A')}")

    @pytest.mark.asyncio
    async def test_backtest_with_invalid_strategy(
        self,
        api_client,
        test_backtest_config,
    ):
        """
        测试使用无效策略ID创建回测

        预期: 返回404错误
        """
        backtest_request = {
            **test_backtest_config,
            "strategy_id": "00000000-0000-0000-0000-000000000000",  # 不存在的策略ID
        }

        response = await api_client.post("/api/v1/backtest/async", json=backtest_request)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_backtest_with_invalid_date_range(
        self,
        api_client,
        test_strategy_data,
    ):
        """
        测试无效的日期范围

        预期: 返回422验证错误
        """
        # 先创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        strategy_id = response_data["data"]["id"]

        # 创建回测，但结束时间早于开始时间
        backtest_request = {
            "strategy_id": strategy_id,
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "start_date": "2024-01-10T00:00:00Z",
            "end_date": "2024-01-01T00:00:00Z",  # 早于start_date
            "initial_capital": 10000.0,
        }

        response = await api_client.post("/api/v1/backtest/async", json=backtest_request)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_backtest_runs(
        self,
        api_client,
        test_strategy_data,
        test_backtest_config,
        cleanup_strategies,
    ):
        """
        测试列出回测运行

        步骤:
        1. 创建策略
        2. 创建多个回测运行
        3. 列出所有回测运行
        4. 验证返回的列表
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        strategy_id = response_data["data"]["id"]
        cleanup_strategies(strategy_id)

        # 创建3个回测运行
        run_ids = []
        for _i in range(3):
            backtest_request = {
                **test_backtest_config,
                "strategy_id": strategy_id,
            }

            response = await api_client.post("/api/v1/backtest/async", json=backtest_request)
            assert response.status_code == 200

            response_data = response.json()
            assert "data" in response_data, f"Response missing 'data' field: {response_data}"
            run_ids.append(response_data["data"]["id"])

        # 列出所有回测运行
        response = await api_client.get("/api/v1/backtest")
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"

        # API returns paginated data
        paginated_data = response_data["data"]
        assert "items" in paginated_data, (
            f"Missing 'items' field in paginated data: {paginated_data}"
        )
        runs = paginated_data["items"]
        assert isinstance(runs, list)
        assert len(runs) >= 3  # 至少包含我们创建的3个

        # 验证创建的运行都在列表中
        returned_ids = [run["id"] for run in runs]
        for run_id in run_ids:
            assert run_id in returned_ids

    @pytest.mark.asyncio
    async def test_delete_backtest_run(
        self,
        api_client,
        test_strategy_data,
        test_backtest_config,
        cleanup_strategies,
    ):
        """
        测试删除回测运行

        步骤:
        1. 创建策略和回测运行
        2. 删除回测运行
        3. 验证已被删除
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        strategy_id = response_data["data"]["id"]
        cleanup_strategies(strategy_id)

        # 创建回测运行
        backtest_request = {
            **test_backtest_config,
            "strategy_id": strategy_id,
        }

        response = await api_client.post("/api/v1/backtest/async", json=backtest_request)
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        run_id = response_data["data"]["id"]

        # 删除回测运行
        response = await api_client.delete(f"/api/v1/backtest/{run_id}")
        assert response.status_code == 200  # API returns 200 with ApiResponse, not 204

        # 验证已删除
        response = await api_client.get(f"/api/v1/backtest/{run_id}")
        assert response.status_code == 404


class TestBacktestCancellation:
    """测试回测取消功能"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cancel_running_backtest(
        self,
        api_client,
        test_strategy_data,
        test_backtest_config,
        cleanup_strategies,
    ):
        """
        测试取消回测端点

        回测可能在 cancel 请求前就已完成（策略简单时瞬间跑完），
        因此验证 cancel 返回 200（成功取消）或 400（已完成不可取消）。
        """
        # 创建策略
        response = await api_client.post("/api/v1/strategies", json=test_strategy_data)
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        strategy_id = response_data["data"]["id"]
        cleanup_strategies(strategy_id)

        backtest_request = {
            **test_backtest_config,
            "strategy_id": strategy_id,
        }

        response = await api_client.post("/api/v1/backtest/async", json=backtest_request)
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        run_id = response_data["data"]["id"]

        # 启动回测
        response = await api_client.post(f"/api/v1/backtest/{run_id}/run")
        assert response.status_code == 200

        # 尝试取消回测
        import asyncio

        await asyncio.sleep(0.5)

        response = await api_client.post(f"/api/v1/backtest/{run_id}/cancel")
        # 200 = successfully cancelled; 400 = already completed (not cancellable)
        assert response.status_code in (200, 400), (
            f"Unexpected cancel response: {response.status_code} {response.text}"
        )

        # 验证最终状态
        response = await api_client.get(f"/api/v1/backtest/{run_id}")
        assert response.status_code == 200

        response_data = response.json()
        assert "data" in response_data, f"Response missing 'data' field: {response_data}"
        run = response_data["data"]
        assert run["status"] in ["cancelled", "cancelling", "completed"]

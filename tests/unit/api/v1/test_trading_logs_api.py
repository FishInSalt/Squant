"""Tests for trading log API endpoints."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from squant.main import create_app


@pytest.fixture
def app():
    return create_app()


class TestLiveLogsEndpoint:
    async def test_returns_logs_from_file(self, app, tmp_path):
        run_id = "3f8e3b5b-423e-4d13-9bcd-630b2f2ea447"
        log_dir = tmp_path / run_id
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trading.log"
        log_file.write_text(
            "[2026-03-25 16:49:04] [INFO] [order] test line 1\n"
            "[2026-03-25 16:49:05] [ERROR] [order] test line 2\n"
        )
        with patch("squant.api.v1.live_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/live/{run_id}/logs")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["logs"]) == 2

    async def test_tail_parameter(self, app, tmp_path):
        run_id = "3f8e3b5b-423e-4d13-9bcd-630b2f2ea447"
        log_dir = tmp_path / run_id
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trading.log"
        lines = [f"[2026-03-25 16:49:{i:02d}] [INFO] [test] line {i}\n" for i in range(10)]
        log_file.write_text("".join(lines))
        with patch("squant.api.v1.live_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/live/{run_id}/logs?tail=3")
        data = resp.json()["data"]
        assert len(data["logs"]) == 3
        assert "line 9" in data["logs"][-1]

    async def test_no_log_file_returns_empty(self, app, tmp_path):
        run_id = "00000000-0000-0000-0000-000000000000"
        with patch("squant.api.v1.live_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/live/{run_id}/logs")
        data = resp.json()["data"]
        assert data["logs"] == []


class TestPaperLogsEndpoint:
    async def test_returns_logs_from_file(self, app, tmp_path):
        run_id = "3f8e3b5b-423e-4d13-9bcd-630b2f2ea447"
        log_dir = tmp_path / run_id
        log_dir.mkdir(parents=True)
        log_file = log_dir / "trading.log"
        log_file.write_text("[2026-03-25 16:49:04] [INFO] [strategy] test paper log\n")
        with patch("squant.api.v1.paper_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/paper/{run_id}/logs")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["logs"]) == 1
        assert "test paper log" in data["logs"][0]

    async def test_no_log_file_returns_empty(self, app, tmp_path):
        run_id = "00000000-0000-0000-0000-000000000000"
        with patch("squant.api.v1.paper_trading.TRADING_LOG_BASE", str(tmp_path)):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/v1/paper/{run_id}/logs")
        data = resp.json()["data"]
        assert data["logs"] == []

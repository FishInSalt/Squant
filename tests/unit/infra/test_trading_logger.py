"""Tests for per-session trading logger with timestamp-suffixed rotation."""

import pytest

from squant.infra.trading_logger import cleanup_trading_logs, create_trading_logger


@pytest.fixture
def log_dir(tmp_path):
    """Temporary log directory."""
    d = tmp_path / "logs" / "trading" / "test-run-id"
    d.mkdir(parents=True)
    return d


class TestCreateTradingLogger:
    def test_creates_logger_and_file(self, tmp_path):
        run_id = "test-run-001"
        logger = create_trading_logger(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        logger.info("test message")
        log_file = tmp_path / "logs" / "trading" / run_id / "trading.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "test message" in content

    def test_message_only_format(self, tmp_path):
        """Logger should write only the message, no extra metadata."""
        run_id = "test-run-002"
        logger = create_trading_logger(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        logger.info("[2026-03-25 16:49:04] [INFO] [order] test order")
        log_file = tmp_path / "logs" / "trading" / run_id / "trading.log"
        content = log_file.read_text().strip()
        assert content == "[2026-03-25 16:49:04] [INFO] [order] test order"

    def test_rotation_with_timestamp_suffix(self, tmp_path):
        """When file exceeds maxBytes, rotated file gets timestamp suffix."""
        run_id = "test-run-003"
        logger = create_trading_logger(
            run_id, base_dir=str(tmp_path / "logs" / "trading"), max_bytes=100
        )
        # Write enough to trigger rotation
        for i in range(20):
            logger.info(f"[2026-03-25 16:49:{i:02d}] [INFO] [test] message number {i} padding")
        log_dir = tmp_path / "logs" / "trading" / run_id
        files = list(log_dir.iterdir())
        assert len(files) > 1  # At least one rotated file
        rotated = [f for f in files if f.name != "trading.log"]
        # Rotated files should have timestamp suffix
        for f in rotated:
            assert f.name.startswith("trading.log.")
            # Format: trading.log.YYYY-MM-DD_HHMMSS
            suffix = f.name.replace("trading.log.", "")
            assert len(suffix) == 17  # 2026-03-25_164900

    def test_close_trading_logger(self, tmp_path):
        """close_trading_logger removes handlers."""
        run_id = "test-run-004"
        logger = create_trading_logger(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        from squant.infra.trading_logger import close_trading_logger

        close_trading_logger(logger)
        assert len(logger.handlers) == 0


class TestCleanupTradingLogs:
    def test_removes_log_directory(self, tmp_path):
        run_id = "test-run-005"
        log_dir = tmp_path / "logs" / "trading" / run_id
        log_dir.mkdir(parents=True)
        (log_dir / "trading.log").write_text("some logs")
        (log_dir / "trading.log.2026-03-25_120000").write_text("old logs")
        cleanup_trading_logs(run_id, base_dir=str(tmp_path / "logs" / "trading"))
        assert not log_dir.exists()

    def test_no_error_if_dir_missing(self, tmp_path):
        """Cleanup should not raise if directory doesn't exist."""
        cleanup_trading_logs("nonexistent", base_dir=str(tmp_path / "logs" / "trading"))

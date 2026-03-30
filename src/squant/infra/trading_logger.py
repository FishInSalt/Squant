"""Per-session trading logger with timestamp-suffixed rotation.

Each trading session (paper/live) gets its own log directory and file.
Log entries are written as-is (message only, no extra metadata from logging module).
When the log file exceeds max_bytes, it is rotated with a timestamp suffix.
"""

import logging
import os
import shutil
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_BASE = "logs/trading"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB


class TimestampRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that renames rotated files with timestamp suffix.

    Instead of .1, .2, ... suffixes, uses .YYYY-MM-DD_HHMMSS format.
    Does not delete old rotated files (backupCount is ignored).
    """

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None  # type: ignore[assignment]
        # Rename current file with timestamp suffix
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        rotated_name = f"{self.baseFilename}.{timestamp}"
        if os.path.exists(self.baseFilename):
            os.rename(self.baseFilename, rotated_name)
        # Open new file
        if not self.delay:
            self.stream = self._open()


def create_trading_logger(
    run_id: str,
    base_dir: str = DEFAULT_LOG_BASE,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> logging.Logger:
    """Create a per-session file logger.

    Args:
        run_id: Session run ID (used as directory name).
        base_dir: Base directory for trading logs.
        max_bytes: Max file size before rotation.

    Returns:
        Logger instance with file handler configured.
    """
    log_dir = Path(base_dir) / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "trading.log"

    logger = logging.getLogger(f"squant.trading.{run_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Don't propagate to root logger

    handler = TimestampRotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,
        backupCount=999,  # Effectively unlimited (doRollover ignores this)
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    return logger


def close_trading_logger(logger: logging.Logger) -> None:
    """Close and remove all handlers from a trading logger."""
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


def cleanup_trading_logs(run_id: str, base_dir: str = DEFAULT_LOG_BASE) -> None:
    """Remove all log files for a session.

    Args:
        run_id: Session run ID.
        base_dir: Base directory for trading logs.
    """
    log_dir = Path(base_dir) / run_id
    if log_dir.exists():
        shutil.rmtree(log_dir)

"""Unit tests for StrategyRun model properties (strategy_name, progress)."""

from squant.models.enums import RunStatus
from squant.models.strategy import Strategy, StrategyRun


class TestStrategyName:
    """Tests for StrategyRun.strategy_name property."""

    def test_returns_name_when_strategy_loaded(self):
        """Test strategy_name returns the strategy's name."""
        run = StrategyRun()
        strategy = Strategy(name="MA Crossover")
        run.strategy = strategy

        assert run.strategy_name == "MA Crossover"

    def test_returns_none_when_strategy_is_none(self):
        """Test strategy_name returns None when no strategy relationship."""
        run = StrategyRun()
        run.strategy = None

        assert run.strategy_name is None


class TestProgress:
    """Tests for StrategyRun.progress property."""

    def test_completed_returns_1(self):
        """Test COMPLETED status returns progress 1.0."""
        run = StrategyRun()
        run.status = RunStatus.COMPLETED
        assert run.progress == 1.0

    def test_error_returns_1(self):
        """Test ERROR status returns progress 1.0."""
        run = StrategyRun()
        run.status = RunStatus.ERROR
        assert run.progress == 1.0

    def test_cancelled_returns_1(self):
        """Test CANCELLED status returns progress 1.0."""
        run = StrategyRun()
        run.status = RunStatus.CANCELLED
        assert run.progress == 1.0

    def test_stopped_returns_1(self):
        """Test STOPPED status returns progress 1.0."""
        run = StrategyRun()
        run.status = RunStatus.STOPPED
        assert run.progress == 1.0

    def test_interrupted_returns_1(self):
        """Test INTERRUPTED status returns progress 1.0."""
        run = StrategyRun()
        run.status = RunStatus.INTERRUPTED
        assert run.progress == 1.0

    def test_pending_returns_0(self):
        """Test PENDING status returns progress 0.0."""
        run = StrategyRun()
        run.status = RunStatus.PENDING
        assert run.progress == 0.0

    def test_running_returns_0(self):
        """Test RUNNING status returns progress 0.0."""
        run = StrategyRun()
        run.status = RunStatus.RUNNING
        assert run.progress == 0.0

    def test_all_terminal_statuses_return_1(self):
        """Test all terminal statuses return 1.0."""
        terminal = [RunStatus.COMPLETED, RunStatus.ERROR, RunStatus.INTERRUPTED, RunStatus.CANCELLED, RunStatus.STOPPED]
        for status in terminal:
            run = StrategyRun()
            run.status = status
            assert run.progress == 1.0, f"Expected 1.0 for {status}"

    def test_all_non_terminal_statuses_return_0(self):
        """Test all non-terminal statuses return 0.0."""
        non_terminal = [RunStatus.PENDING, RunStatus.RUNNING]
        for status in non_terminal:
            run = StrategyRun()
            run.status = status
            assert run.progress == 0.0, f"Expected 0.0 for {status}"

"""Unit tests for get_account_available_balance service method."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest

from squant.models.enums import RunMode, RunStatus
from squant.models.strategy import StrategyRun
from squant.schemas.live_trading import AccountBalanceResponse, RunningSessionEquity
from squant.services.live_trading import LiveStrategyRunRepository, LiveTradingService

# --- Schema Tests ---


class TestAccountBalanceSchemas:
    """Tests for the account balance response schemas."""

    def test_running_session_equity_schema(self) -> None:
        """Test RunningSessionEquity serializes correctly."""
        run_id = uuid4()
        item = RunningSessionEquity(
            run_id=run_id,
            strategy_name="MyStrategy",
            symbol="BTC/USDT",
            equity=Decimal("5000.00"),
        )
        assert item.run_id == run_id
        assert item.strategy_name == "MyStrategy"
        assert item.symbol == "BTC/USDT"
        assert item.equity == Decimal("5000.00")

    def test_running_session_equity_optional_name(self) -> None:
        """Test RunningSessionEquity with no strategy name."""
        item = RunningSessionEquity(
            run_id=uuid4(),
            symbol="ETH/USDT",
            equity=Decimal("1000"),
        )
        assert item.strategy_name is None

    def test_account_balance_response_defaults(self) -> None:
        """Test AccountBalanceResponse has correct defaults."""
        resp = AccountBalanceResponse(
            account_total_value=Decimal("10000"),
            quote_currency="USDT",
        )
        assert resp.account_total_value == Decimal("10000")
        assert resp.quote_currency == "USDT"
        assert resp.running_sessions == []
        assert resp.sessions_total_equity == Decimal("0")
        assert resp.available == Decimal("0")

    def test_account_balance_response_full(self) -> None:
        """Test AccountBalanceResponse with all fields populated."""
        run_id = uuid4()
        resp = AccountBalanceResponse(
            account_total_value=Decimal("10000"),
            quote_currency="USDT",
            running_sessions=[
                RunningSessionEquity(
                    run_id=run_id,
                    strategy_name="TestStrat",
                    symbol="BTC/USDT",
                    equity=Decimal("3000"),
                )
            ],
            sessions_total_equity=Decimal("3000"),
            available=Decimal("7000"),
        )
        assert len(resp.running_sessions) == 1
        assert resp.sessions_total_equity == Decimal("3000")
        assert resp.available == Decimal("7000")


# --- Repository Tests ---


class TestListRunningByAccount:
    """Tests for LiveStrategyRunRepository.list_running_by_account."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.fixture
    def repo(self, mock_session: MagicMock) -> LiveStrategyRunRepository:
        """Create repository with mock session."""
        return LiveStrategyRunRepository(mock_session)

    async def test_returns_empty_when_no_running_sessions(
        self, repo: LiveStrategyRunRepository
    ) -> None:
        """Test returns empty list when no running sessions exist."""
        result = await repo.list_running_by_account("account-123")
        assert result == []
        repo.session.execute.assert_called_once()

    async def test_returns_running_sessions(
        self, repo: LiveStrategyRunRepository
    ) -> None:
        """Test returns only running live sessions for account."""
        mock_run = MagicMock(spec=StrategyRun)
        mock_run.id = str(uuid4())
        mock_run.account_id = "account-123"
        mock_run.status = RunStatus.RUNNING
        mock_run.mode = RunMode.LIVE

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_run]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        repo.session.execute = AsyncMock(return_value=mock_result)

        result = await repo.list_running_by_account("account-123")
        assert len(result) == 1
        assert result[0] == mock_run


# --- Service Tests ---


def _make_mock_run(
    run_id: UUID | None = None,
    account_id: str = "acc-1",
    strategy_id: str | None = None,
    symbol: str = "BTC/USDT",
    initial_capital: Decimal | None = Decimal("1000"),
    result: dict | None = None,
) -> MagicMock:
    """Create a mock StrategyRun for testing."""
    mock = MagicMock(spec=StrategyRun)
    mock.id = str(run_id or uuid4())
    mock.account_id = account_id
    mock.strategy_id = strategy_id or str(uuid4())
    mock.symbol = symbol
    mock.mode = RunMode.LIVE
    mock.status = RunStatus.RUNNING
    mock.initial_capital = initial_capital
    mock.result = result
    return mock


class TestGetAccountAvailableBalance:
    """Tests for LiveTradingService.get_account_available_balance."""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session: MagicMock) -> LiveTradingService:
        """Create service with mock session."""
        return LiveTradingService(mock_session)

    @pytest.fixture
    def mock_adapter(self) -> AsyncMock:
        """Create a mock exchange adapter."""
        adapter = AsyncMock()
        adapter.get_account_total_value = AsyncMock(
            return_value=(Decimal("10000"), [])
        )
        adapter.connect = AsyncMock()
        adapter.close = AsyncMock()
        return adapter

    async def test_no_running_sessions(
        self, service: LiveTradingService, mock_adapter: AsyncMock
    ) -> None:
        """Test available equals total when no running sessions."""
        account_id = str(uuid4())

        with (
            patch.object(
                service, "_create_adapter_for_account", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                service.run_repo,
                "list_running_by_account",
                new_callable=AsyncMock,
            ) as mock_list,
        ):
            mock_create.return_value = mock_adapter
            mock_list.return_value = []

            result = await service.get_account_available_balance(
                account_id, "USDT"
            )

        assert isinstance(result, AccountBalanceResponse)
        assert result.account_total_value == Decimal("10000")
        assert result.quote_currency == "USDT"
        assert result.running_sessions == []
        assert result.sessions_total_equity == Decimal("0")
        assert result.available == Decimal("10000")
        mock_adapter.close.assert_called_once()

    async def test_with_running_sessions_from_engine(
        self, service: LiveTradingService, mock_adapter: AsyncMock
    ) -> None:
        """Test deducts engine equity from total for running sessions."""
        account_id = str(uuid4())
        run_id = uuid4()
        strategy_id = str(uuid4())

        mock_run = _make_mock_run(
            run_id=run_id,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol="BTC/USDT",
        )

        # Mock engine with equity property
        mock_engine = MagicMock()
        mock_context = MagicMock()
        type(mock_context).equity = PropertyMock(return_value=Decimal("3000"))
        mock_engine.context = mock_context

        # Mock strategy lookup
        mock_strategy = MagicMock()
        mock_strategy.name = "TestStrategy"

        with (
            patch.object(
                service, "_create_adapter_for_account", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                service.run_repo,
                "list_running_by_account",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "squant.services.live_trading.get_live_session_manager"
            ) as mock_get_mgr,
            patch(
                "squant.services.strategy.StrategyRepository.get",
                new_callable=AsyncMock,
            ) as mock_strat_get,
        ):
            mock_create.return_value = mock_adapter
            mock_list.return_value = [mock_run]
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = mock_engine
            mock_get_mgr.return_value = mock_mgr
            mock_strat_get.return_value = mock_strategy

            result = await service.get_account_available_balance(
                account_id, "USDT"
            )

        assert result.account_total_value == Decimal("10000")
        assert result.sessions_total_equity == Decimal("3000")
        assert result.available == Decimal("7000")
        assert len(result.running_sessions) == 1
        assert result.running_sessions[0].run_id == run_id
        assert result.running_sessions[0].strategy_name == "TestStrategy"
        assert result.running_sessions[0].symbol == "BTC/USDT"
        assert result.running_sessions[0].equity == Decimal("3000")

    async def test_fallback_to_db_snapshot_equity(
        self, service: LiveTradingService, mock_adapter: AsyncMock
    ) -> None:
        """Test falls back to result JSONB when engine not in memory."""
        account_id = str(uuid4())
        run_id = uuid4()
        strategy_id = str(uuid4())

        mock_run = _make_mock_run(
            run_id=run_id,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol="ETH/USDT",
            result={"equity": "2500.50"},
        )

        mock_strategy = MagicMock()
        mock_strategy.name = "FallbackStrat"

        with (
            patch.object(
                service, "_create_adapter_for_account", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                service.run_repo,
                "list_running_by_account",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "squant.services.live_trading.get_live_session_manager"
            ) as mock_get_mgr,
            patch(
                "squant.services.strategy.StrategyRepository.get",
                new_callable=AsyncMock,
            ) as mock_strat_get,
        ):
            mock_create.return_value = mock_adapter
            mock_list.return_value = [mock_run]
            # Engine not in memory
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = None
            mock_get_mgr.return_value = mock_mgr
            mock_strat_get.return_value = mock_strategy

            result = await service.get_account_available_balance(
                account_id, "USDT"
            )

        assert result.sessions_total_equity == Decimal("2500.50")
        assert result.available == Decimal("10000") - Decimal("2500.50")
        assert len(result.running_sessions) == 1
        assert result.running_sessions[0].equity == Decimal("2500.50")
        assert result.running_sessions[0].strategy_name == "FallbackStrat"

    async def test_fallback_to_initial_capital(
        self, service: LiveTradingService, mock_adapter: AsyncMock
    ) -> None:
        """Test falls back to initial_capital when no engine and no result."""
        account_id = str(uuid4())
        run_id = uuid4()

        mock_run = _make_mock_run(
            run_id=run_id,
            account_id=account_id,
            symbol="SOL/USDT",
            initial_capital=Decimal("500"),
            result=None,
        )

        mock_strategy = MagicMock()
        mock_strategy.name = None

        with (
            patch.object(
                service, "_create_adapter_for_account", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                service.run_repo,
                "list_running_by_account",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "squant.services.live_trading.get_live_session_manager"
            ) as mock_get_mgr,
            patch(
                "squant.services.strategy.StrategyRepository.get",
                new_callable=AsyncMock,
            ) as mock_strat_get,
        ):
            mock_create.return_value = mock_adapter
            mock_list.return_value = [mock_run]
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = None
            mock_get_mgr.return_value = mock_mgr
            mock_strat_get.return_value = mock_strategy

            result = await service.get_account_available_balance(
                account_id, "USDT"
            )

        assert result.sessions_total_equity == Decimal("500")
        assert result.available == Decimal("9500")
        assert result.running_sessions[0].equity == Decimal("500")
        assert result.running_sessions[0].strategy_name is None

    async def test_adapter_closed_on_error(
        self, service: LiveTradingService, mock_adapter: AsyncMock
    ) -> None:
        """Test adapter is closed even when get_account_total_value raises."""
        account_id = str(uuid4())
        mock_adapter.get_account_total_value.side_effect = Exception("API error")

        with (
            patch.object(
                service, "_create_adapter_for_account", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_create.return_value = mock_adapter

            with pytest.raises(Exception, match="API error"):
                await service.get_account_available_balance(account_id, "USDT")

        mock_adapter.close.assert_called_once()

    async def test_multiple_running_sessions(
        self, service: LiveTradingService, mock_adapter: AsyncMock
    ) -> None:
        """Test correct aggregation of multiple running sessions."""
        account_id = str(uuid4())

        run1 = _make_mock_run(
            account_id=account_id,
            symbol="BTC/USDT",
            result={"equity": "3000"},
        )
        run2 = _make_mock_run(
            account_id=account_id,
            symbol="ETH/USDT",
            result={"equity": "2000"},
        )

        mock_strategy = MagicMock()
        mock_strategy.name = "Multi"

        with (
            patch.object(
                service, "_create_adapter_for_account", new_callable=AsyncMock
            ) as mock_create,
            patch.object(
                service.run_repo,
                "list_running_by_account",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "squant.services.live_trading.get_live_session_manager"
            ) as mock_get_mgr,
            patch(
                "squant.services.strategy.StrategyRepository.get",
                new_callable=AsyncMock,
            ) as mock_strat_get,
        ):
            mock_create.return_value = mock_adapter
            mock_list.return_value = [run1, run2]
            mock_mgr = MagicMock()
            mock_mgr.get.return_value = None
            mock_get_mgr.return_value = mock_mgr
            mock_strat_get.return_value = mock_strategy

            result = await service.get_account_available_balance(
                account_id, "USDT"
            )

        assert result.sessions_total_equity == Decimal("5000")
        assert result.available == Decimal("5000")
        assert len(result.running_sessions) == 2

# tests/unit/infra/exchange/test_get_order_trades.py
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from squant.infra.exchange.ccxt.rest_adapter import CCXTRestAdapter
from squant.infra.exchange.types import TradeInfo


class TestGetOrderTrades:
    @pytest.fixture
    def adapter(self):
        adapter = CCXTRestAdapter.__new__(CCXTRestAdapter)
        adapter._exchange = MagicMock()
        adapter._exchange.fetch_order_trades = AsyncMock()
        adapter._exchange_id = "okx"
        adapter._connected = True
        return adapter

    async def test_returns_trade_info_list(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = [
            {
                "id": "t001",
                "order": "o123",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 96500.0,
                "amount": 0.008,
                "fee": {"cost": 0.077, "currency": "USDT"},
                "takerOrMaker": "taker",
                "timestamp": 1711000215000,
            },
            {
                "id": "t002",
                "order": "o123",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 96480.0,
                "amount": 0.005,
                "fee": {"cost": 0.048, "currency": "USDT"},
                "takerOrMaker": "maker",
                "timestamp": 1711000217000,
            },
        ]
        result = await adapter._get_order_trades_impl("BTC/USDT", "o123")
        assert len(result) == 2
        assert isinstance(result[0], TradeInfo)
        assert result[0].trade_id == "t001"
        assert result[0].price == Decimal("96500.0")
        assert result[0].fee == Decimal("0.077")
        assert result[0].taker_or_maker == "taker"
        assert result[1].trade_id == "t002"

    async def test_empty_result(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = []
        result = await adapter._get_order_trades_impl("BTC/USDT", "o123")
        assert result == []

    async def test_handles_missing_fee(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = [
            {
                "id": "t001",
                "order": "o123",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 96500.0,
                "amount": 0.008,
                "fee": None,
                "takerOrMaker": None,
                "timestamp": 1711000215000,
            }
        ]
        result = await adapter._get_order_trades_impl("BTC/USDT", "o123")
        assert result[0].fee == Decimal("0")
        assert result[0].fee_currency == ""
        assert result[0].taker_or_maker is None

    async def test_sorted_by_timestamp(self, adapter):
        adapter._exchange.fetch_order_trades.return_value = [
            {
                "id": "t002",
                "order": "o1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 100,
                "amount": 1,
                "fee": None,
                "takerOrMaker": None,
                "timestamp": 1711000220000,
            },
            {
                "id": "t001",
                "order": "o1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "price": 100,
                "amount": 1,
                "fee": None,
                "takerOrMaker": None,
                "timestamp": 1711000210000,
            },
        ]
        result = await adapter._get_order_trades_impl("BTC/USDT", "o1")
        assert result[0].trade_id == "t001"  # earlier timestamp first
        assert result[1].trade_id == "t002"

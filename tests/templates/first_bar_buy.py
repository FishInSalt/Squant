"""Minimal test strategy: buys once on the first bar, then idles.
Used for Layer 3 engine integration testing."""
from decimal import Decimal
from squant.engine.backtest.strategy_base import Strategy


class FirstBarBuyStrategy(Strategy):
    def on_init(self):
        self.bought = False

    def on_bar(self, bar):
        if not self.bought:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
            self.bought = True

    def on_stop(self):
        pass

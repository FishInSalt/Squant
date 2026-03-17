"""Deterministic test strategy: buys on bar 3, sells on bar 8, repeats.
Guarantees at least one buy+sell cycle within 10 minutes on 1m timeframe.
Used for Layer 4 full lifecycle verification."""
from decimal import Decimal


class BarCountStrategy:
    def on_init(self):
        self.bar_count = 0

    def on_bar(self, bar):
        self.bar_count += 1
        pos = self.ctx.get_position(bar.symbol)
        if self.bar_count == 3 and not pos:
            self.ctx.buy(bar.symbol, Decimal("0.01"))
        elif self.bar_count == 8 and pos:
            self.ctx.sell(bar.symbol, Decimal("0.01"))
            self.bar_count = 0

    def on_stop(self):
        pass

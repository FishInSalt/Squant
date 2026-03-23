"""Test strategy for fill sync verification.

Phase 1 (bar 3-8): Small market order (0.001 BTC) — single fill, verify basic watchMyTrades flow
Phase 2 (bar 3-8): Large market order (0.1 BTC) — likely partial fills, verify per-fill handling
Resets after each phase regardless of whether orders succeeded.
"""
from decimal import Decimal

from squant.engine.backtest.strategy_base import Strategy


class FillSyncTestStrategy(Strategy):
    def on_init(self):
        self.bar_count = 0
        self.phase = 1  # 1=small order, 2=large order

    def on_bar(self, bar):
        self.bar_count = self.bar_count + 1
        pos = self.ctx.get_position(bar.symbol)

        if self.bar_count == 3 and not pos:
            if self.phase == 1:
                self.ctx.buy(bar.symbol, Decimal("0.001"))
            elif self.phase == 2:
                self.ctx.buy(bar.symbol, Decimal("0.1"))

        elif self.bar_count == 8:
            if pos:
                self.ctx.sell(bar.symbol, pos.amount)
            # Always reset and advance phase regardless of position
            if self.phase == 1:
                self.phase = 2
            else:
                self.phase = 1
            self.bar_count = 0

    def on_stop(self):
        pass

"""Strategy base class for backtest engine.

This module provides the abstract base class that all user strategies must inherit from.
The Strategy class is injected into the restricted execution environment.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from squant.engine.backtest.context import BacktestContext
    from squant.engine.backtest.types import Bar, Fill, SimulatedOrder


class Strategy(ABC):
    """Abstract base class for trading strategies.

    All user-defined strategies must inherit from this class and implement
    the on_bar method. The strategy receives market data through on_bar calls
    and can interact with the backtest context through self.ctx.

    Example:
        class DualMA(Strategy):
            def on_init(self):
                self.fast_period = self.ctx.params.get("fast", 5)
                self.slow_period = self.ctx.params.get("slow", 20)

            def on_bar(self, bar):
                closes = self.ctx.get_closes(self.slow_period)
                if len(closes) < self.slow_period:
                    return

                fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
                slow_ma = sum(closes) / self.slow_period

                pos = self.ctx.get_position(bar.symbol)

                if fast_ma > slow_ma and not pos:
                    self.ctx.buy(bar.symbol, Decimal("0.1"))
                elif fast_ma < slow_ma and pos:
                    self.ctx.sell(bar.symbol, pos.amount)
    """

    # Context is injected by the backtest runner
    ctx: "BacktestContext"

    def on_init(self) -> None:
        """Called once before the backtest starts.

        Override this method to initialize strategy state, parameters,
        or any pre-computation needed before processing bars.

        The context (self.ctx) is available and can be used to read
        parameters via self.ctx.params.
        """
        pass

    @abstractmethod
    def on_bar(self, bar: "Bar") -> None:
        """Called for each bar during the backtest.

        This is the main strategy logic method. Override this to implement
        your trading logic. Use self.ctx to access market data, place orders,
        and query positions.

        Args:
            bar: The current OHLCV bar being processed.

        Note:
            Orders placed in on_bar are executed on the NEXT bar's open price
            (for market orders) to prevent look-ahead bias.
        """
        pass

    def on_fill(self, fill: "Fill") -> None:
        """Called when an order is filled (fully or partially).

        Override this method to react to fill events — e.g., place a
        stop-loss after a buy fill, or cancel the other side of an
        OCO pair. Called once per fill, before on_bar() on the same bar.

        Orders placed in on_fill are executed on the NEXT bar, same as
        orders placed in on_bar.

        Args:
            fill: The fill event with price, amount, fee, etc.
        """
        pass

    def on_order_done(self, order: "SimulatedOrder") -> None:
        """Called when an order reaches a terminal state (FILLED or CANCELLED).

        Override this method to react to order completion — e.g., cancel
        the other leg of an OCO pair when one side fills. Called once per
        completed order, before on_bar() on the same bar.

        Args:
            order: The completed order with final status, fill price, etc.
        """
        pass

    def on_stop(self) -> None:
        """Called once after the backtest ends.

        Override this method to perform cleanup, final calculations,
        or logging at the end of the backtest.

        Note:
            Any open positions at this point will be valued at the
            last bar's close price in the final equity calculation.
        """
        pass

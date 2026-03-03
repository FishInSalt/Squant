"""Built-in technical indicators for strategy sandbox.

All functions accept lists of Decimal values (compatible with ctx.get_closes())
and return Decimal results. Stateless, pure functions — safe for sandbox execution.

Injected into the strategy sandbox as the `ta` module.
Usage in strategies: ta.sma(closes, 20), ta.rsi(closes, 14), etc.
"""

from decimal import Decimal


def sma(data: list[Decimal], period: int) -> Decimal | None:
    """Simple Moving Average.

    Args:
        data: Price series (most recent last).
        period: Lookback period.

    Returns:
        SMA value, or None if insufficient data.
    """
    if len(data) < period or period <= 0:
        return None
    return sum(data[-period:]) / Decimal(str(period))


def ema(data: list[Decimal], period: int) -> Decimal | None:
    """Exponential Moving Average.

    Uses SMA as seed for the first `period` values, then applies
    the standard EMA formula: EMA = price * k + EMA_prev * (1 - k)
    where k = 2 / (period + 1).

    Args:
        data: Price series (most recent last).
        period: Lookback period.

    Returns:
        EMA value, or None if insufficient data.
    """
    if len(data) < period or period <= 0:
        return None
    k = Decimal("2") / Decimal(str(period + 1))
    # Seed with SMA of first `period` values
    result = sum(data[:period]) / Decimal(str(period))
    for price in data[period:]:
        result = price * k + result * (Decimal("1") - k)
    return result


def rsi(data: list[Decimal], period: int = 14) -> Decimal | None:
    """Relative Strength Index (Wilder's smoothing).

    Args:
        data: Price series (most recent last).
        period: Lookback period (default 14).

    Returns:
        RSI value (0-100), or None if insufficient data.
    """
    if len(data) < period + 1 or period <= 0:
        return None

    # Calculate price changes
    changes = [data[i] - data[i - 1] for i in range(1, len(data))]

    # Initial average gain/loss from first `period` changes
    gains = [max(c, Decimal("0")) for c in changes[:period]]
    losses = [max(-c, Decimal("0")) for c in changes[:period]]
    avg_gain = sum(gains) / Decimal(str(period))
    avg_loss = sum(losses) / Decimal(str(period))

    # Wilder's smoothing for remaining changes
    for change in changes[period:]:
        gain = max(change, Decimal("0"))
        loss = max(-change, Decimal("0"))
        avg_gain = (avg_gain * Decimal(str(period - 1)) + gain) / Decimal(str(period))
        avg_loss = (avg_loss * Decimal(str(period - 1)) + loss) / Decimal(str(period))

    if avg_loss == Decimal("0"):
        return Decimal("100")

    rs = avg_gain / avg_loss
    return Decimal("100") - Decimal("100") / (Decimal("1") + rs)


def macd(
    data: list[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Moving Average Convergence/Divergence.

    Args:
        data: Price series (most recent last).
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal line EMA period (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram), or None if insufficient data.
    """
    if len(data) < slow + signal - 1:
        return None

    # Calculate MACD line values for enough history to compute signal EMA
    macd_values = []
    for i in range(slow, len(data) + 1):
        subset = data[:i]
        fast_ema = ema(subset, fast)
        slow_ema = ema(subset, slow)
        if fast_ema is not None and slow_ema is not None:
            macd_values.append(fast_ema - slow_ema)

    if len(macd_values) < signal:
        return None

    macd_line = macd_values[-1]
    signal_line = ema(macd_values, signal)
    if signal_line is None:
        return None

    histogram = macd_line - signal_line
    return (macd_line, signal_line, histogram)


def bollinger_bands(
    data: list[Decimal], period: int = 20, num_std: Decimal = Decimal("2"),
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Bollinger Bands.

    Args:
        data: Price series (most recent last).
        period: SMA period (default 20).
        num_std: Number of standard deviations (default 2).

    Returns:
        Tuple of (upper, middle, lower), or None if insufficient data.
    """
    middle = sma(data, period)
    if middle is None:
        return None

    std = stdev(data, period)
    if std is None:
        return None

    upper = middle + num_std * std
    lower = middle - num_std * std
    return (upper, middle, lower)


def atr(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    period: int = 14,
) -> Decimal | None:
    """Average True Range.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        period: Lookback period (default 14).

    Returns:
        ATR value, or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1 or period <= 0:
        return None

    # Calculate true ranges
    true_ranges = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Initial ATR is SMA of first `period` true ranges
    result = sum(true_ranges[:period]) / Decimal(str(period))

    # Wilder's smoothing for remaining
    for tr in true_ranges[period:]:
        result = (result * Decimal(str(period - 1)) + tr) / Decimal(str(period))

    return result


def stdev(data: list[Decimal], period: int) -> Decimal | None:
    """Population standard deviation of the last `period` values.

    Args:
        data: Price series.
        period: Number of values to use.

    Returns:
        Standard deviation, or None if insufficient data.
    """
    if len(data) < period or period <= 0:
        return None

    subset = data[-period:]
    mean = sum(subset) / Decimal(str(period))
    variance = sum((x - mean) ** 2 for x in subset) / Decimal(str(period))

    # Newton's method for square root (Decimal doesn't have sqrt)
    if variance == Decimal("0"):
        return Decimal("0")
    # Use float sqrt as seed, then refine with Decimal
    import math

    guess = Decimal(str(math.sqrt(float(variance))))
    # Two iterations of Newton's method for precision
    for _ in range(2):
        guess = (guess + variance / guess) / Decimal("2")
    return guess


def highest(data: list[Decimal], period: int) -> Decimal | None:
    """Highest value in the last `period` values.

    Args:
        data: Price series.
        period: Lookback period.

    Returns:
        Maximum value, or None if insufficient data.
    """
    if len(data) < period or period <= 0:
        return None
    return max(data[-period:])


def lowest(data: list[Decimal], period: int) -> Decimal | None:
    """Lowest value in the last `period` values.

    Args:
        data: Price series.
        period: Lookback period.

    Returns:
        Minimum value, or None if insufficient data.
    """
    if len(data) < period or period <= 0:
        return None
    return min(data[-period:])


def crossover(fast: list[Decimal], slow: list[Decimal]) -> bool:
    """Check if fast series just crossed above slow series.

    Args:
        fast: Fast-moving series (at least 2 values).
        slow: Slow-moving series (at least 2 values).

    Returns:
        True if fast crossed above slow on the last bar.
    """
    if len(fast) < 2 or len(slow) < 2:
        return False
    return fast[-2] <= slow[-2] and fast[-1] > slow[-1]


def crossunder(fast: list[Decimal], slow: list[Decimal]) -> bool:
    """Check if fast series just crossed below slow series.

    Args:
        fast: Fast-moving series (at least 2 values).
        slow: Slow-moving series (at least 2 values).

    Returns:
        True if fast crossed below slow on the last bar.
    """
    if len(fast) < 2 or len(slow) < 2:
        return False
    return fast[-2] >= slow[-2] and fast[-1] < slow[-1]

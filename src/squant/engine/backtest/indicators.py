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

    Uses single-pass O(n) computation: fast and slow EMAs are advanced
    incrementally, then the signal EMA is computed over the MACD line series.

    Args:
        data: Price series (most recent last).
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal line EMA period (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram), or None if insufficient data.
    """
    if len(data) < slow + signal - 1 or fast <= 0 or slow <= 0 or signal <= 0:
        return None

    k_fast = Decimal("2") / Decimal(str(fast + 1))
    k_slow = Decimal("2") / Decimal(str(slow + 1))
    k_signal = Decimal("2") / Decimal(str(signal + 1))
    one = Decimal("1")

    # Seed fast EMA with SMA of first `fast` values, then advance to data[slow-1]
    fast_ema = sum(data[:fast]) / Decimal(str(fast))
    for i in range(fast, slow):
        fast_ema = data[i] * k_fast + fast_ema * (one - k_fast)

    # Seed slow EMA with SMA of first `slow` values
    slow_ema = sum(data[:slow]) / Decimal(str(slow))

    # First MACD value at index slow-1 (both EMAs now seeded)
    macd_values: list[Decimal] = [fast_ema - slow_ema]

    # Advance both EMAs from data[slow] onward, collecting MACD line series
    for i in range(slow, len(data)):
        fast_ema = data[i] * k_fast + fast_ema * (one - k_fast)
        slow_ema = data[i] * k_slow + slow_ema * (one - k_slow)
        macd_values.append(fast_ema - slow_ema)

    if len(macd_values) < signal:
        return None

    # Compute signal line as EMA of MACD values
    signal_ema = sum(macd_values[:signal]) / Decimal(str(signal))
    for mv in macd_values[signal:]:
        signal_ema = mv * k_signal + signal_ema * (one - k_signal)

    macd_line = macd_values[-1]
    histogram = macd_line - signal_ema
    return (macd_line, signal_ema, histogram)


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


def vwap(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    volumes: list[Decimal],
    period: int | None = None,
) -> Decimal | None:
    """Volume Weighted Average Price.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        volumes: Volume series.
        period: Lookback period. If None, uses all available data.

    Returns:
        VWAP value, or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n == 0:
        return None
    if period is not None:
        if period <= 0 or n < period:
            return None
        highs = highs[-period:]
        lows = lows[-period:]
        closes = closes[-period:]
        volumes = volumes[-period:]
        n = period

    total_volume = Decimal("0")
    total_tp_volume = Decimal("0")
    for i in range(n):
        typical_price = (highs[i] + lows[i] + closes[i]) / Decimal("3")
        total_tp_volume += typical_price * volumes[i]
        total_volume += volumes[i]

    if total_volume == Decimal("0"):
        return None
    return total_tp_volume / total_volume


def stochastic(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[Decimal, Decimal] | None:
    """Stochastic Oscillator (%K and %D).

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        k_period: %K lookback period (default 14).
        d_period: %D smoothing period (default 3).

    Returns:
        Tuple of (%K, %D), or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < k_period + d_period - 1 or k_period <= 0 or d_period <= 0:
        return None

    # Calculate raw %K values for the last d_period bars
    k_values: list[Decimal] = []
    for i in range(d_period):
        idx = n - d_period + i
        high_val = max(highs[idx - k_period + 1 : idx + 1])
        low_val = min(lows[idx - k_period + 1 : idx + 1])
        if high_val == low_val:
            k_values.append(Decimal("50"))
        else:
            k_values.append((closes[idx] - low_val) / (high_val - low_val) * Decimal("100"))

    k = k_values[-1]
    d = sum(k_values) / Decimal(str(d_period))
    return (k, d)


def williams_r(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    period: int = 14,
) -> Decimal | None:
    """Williams %R.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        period: Lookback period (default 14).

    Returns:
        Williams %R value (-100 to 0), or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < period or period <= 0:
        return None

    high_val = max(highs[-period:])
    low_val = min(lows[-period:])
    if high_val == low_val:
        return Decimal("-50")
    return (high_val - closes[-1]) / (high_val - low_val) * Decimal("-100")


def roc(data: list[Decimal], period: int = 12) -> Decimal | None:
    """Rate of Change.

    Args:
        data: Price series (most recent last).
        period: Lookback period (default 12).

    Returns:
        ROC as percentage, or None if insufficient data.
    """
    if len(data) < period + 1 or period <= 0:
        return None
    prev = data[-period - 1]
    if prev == Decimal("0"):
        return None
    return (data[-1] - prev) / prev * Decimal("100")


def obv(closes: list[Decimal], volumes: list[Decimal]) -> Decimal | None:
    """On-Balance Volume.

    Args:
        closes: Close price series.
        volumes: Volume series.

    Returns:
        OBV value, or None if insufficient data.
    """
    n = min(len(closes), len(volumes))
    if n < 2:
        return None

    result = Decimal("0")
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            result += volumes[i]
        elif closes[i] < closes[i - 1]:
            result -= volumes[i]
    return result


def keltner_channels(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: Decimal = Decimal("1.5"),
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Keltner Channels.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        ema_period: EMA period for middle line (default 20).
        atr_period: ATR period (default 10).
        multiplier: ATR multiplier (default 1.5).

    Returns:
        Tuple of (upper, middle, lower), or None if insufficient data.
    """
    middle = ema(closes, ema_period)
    if middle is None:
        return None

    atr_val = atr(highs, lows, closes, atr_period)
    if atr_val is None:
        return None

    upper = middle + multiplier * atr_val
    lower = middle - multiplier * atr_val
    return (upper, middle, lower)


def adx(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    period: int = 14,
) -> Decimal | None:
    """Average Directional Index.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        period: Lookback period (default 14).

    Returns:
        ADX value (0-100), or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < 2 * period + 1 or period <= 0:
        return None

    zero = Decimal("0")
    p = Decimal(str(period))

    # Calculate +DM, -DM, TR series
    plus_dm_list: list[Decimal] = []
    minus_dm_list: list[Decimal] = []
    tr_list: list[Decimal] = []

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm_list.append(up_move if up_move > down_move and up_move > zero else zero)
        minus_dm_list.append(down_move if down_move > up_move and down_move > zero else zero)
        tr_list.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    if len(tr_list) < 2 * period:
        return None

    # Initial smoothed values (SMA seed)
    smoothed_plus_dm = sum(plus_dm_list[:period]) / p
    smoothed_minus_dm = sum(minus_dm_list[:period]) / p
    smoothed_tr = sum(tr_list[:period]) / p

    # Wilder's smoothing and collect DX values
    dx_values: list[Decimal] = []
    for i in range(period, len(tr_list)):
        smoothed_plus_dm = (smoothed_plus_dm * (p - Decimal("1")) + plus_dm_list[i]) / p
        smoothed_minus_dm = (smoothed_minus_dm * (p - Decimal("1")) + minus_dm_list[i]) / p
        smoothed_tr = (smoothed_tr * (p - Decimal("1")) + tr_list[i]) / p

        if smoothed_tr == zero:
            dx_values.append(zero)
            continue

        plus_di = smoothed_plus_dm / smoothed_tr * Decimal("100")
        minus_di = smoothed_minus_dm / smoothed_tr * Decimal("100")
        di_sum = plus_di + minus_di
        if di_sum == zero:
            dx_values.append(zero)
        else:
            dx_values.append(abs(plus_di - minus_di) / di_sum * Decimal("100"))

    if len(dx_values) < period:
        return None

    # ADX = Wilder's smoothed average of DX
    adx_val = sum(dx_values[:period]) / p
    for dx in dx_values[period:]:
        adx_val = (adx_val * (p - Decimal("1")) + dx) / p

    return adx_val


def cci(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    period: int = 20,
) -> Decimal | None:
    """Commodity Channel Index.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        period: Lookback period (default 20).

    Returns:
        CCI value, or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes))
    if n < period or period <= 0:
        return None

    # Typical prices for last `period` bars
    tp_list = [
        (highs[n - period + i] + lows[n - period + i] + closes[n - period + i]) / Decimal("3")
        for i in range(period)
    ]

    tp_mean = sum(tp_list) / Decimal(str(period))

    # Mean absolute deviation
    mad = sum(abs(tp - tp_mean) for tp in tp_list) / Decimal(str(period))
    if mad == Decimal("0"):
        return Decimal("0")

    return (tp_list[-1] - tp_mean) / (Decimal("0.015") * mad)


def mfi(
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    volumes: list[Decimal],
    period: int = 14,
) -> Decimal | None:
    """Money Flow Index.

    Args:
        highs: High price series.
        lows: Low price series.
        closes: Close price series.
        volumes: Volume series.
        period: Lookback period (default 14).

    Returns:
        MFI value (0-100), or None if insufficient data.
    """
    n = min(len(highs), len(lows), len(closes), len(volumes))
    if n < period + 1 or period <= 0:
        return None

    positive_flow = Decimal("0")
    negative_flow = Decimal("0")

    for i in range(n - period, n):
        tp = (highs[i] + lows[i] + closes[i]) / Decimal("3")
        prev_tp = (highs[i - 1] + lows[i - 1] + closes[i - 1]) / Decimal("3")
        raw_flow = tp * volumes[i]

        if tp > prev_tp:
            positive_flow += raw_flow
        elif tp < prev_tp:
            negative_flow += raw_flow

    if negative_flow == Decimal("0"):
        return Decimal("100")

    money_ratio = positive_flow / negative_flow
    return Decimal("100") - Decimal("100") / (Decimal("1") + money_ratio)


def donchian_channels(
    highs: list[Decimal],
    lows: list[Decimal],
    period: int = 20,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Donchian Channels.

    Args:
        highs: High price series.
        lows: Low price series.
        period: Lookback period (default 20).

    Returns:
        Tuple of (upper, middle, lower), or None if insufficient data.
    """
    n = min(len(highs), len(lows))
    if n < period or period <= 0:
        return None

    upper = max(highs[-period:])
    lower = min(lows[-period:])
    middle = (upper + lower) / Decimal("2")
    return (upper, middle, lower)

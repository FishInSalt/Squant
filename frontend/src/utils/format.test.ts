import {
  formatNumber,
  formatPrice,
  formatPercent,
  formatLargeNumber,
  formatVolume,
  formatDateTime,
  formatDate,
  formatTime,
  formatRelativeTime,
  formatDuration,
  formatFileSize,
  formatOrderSide,
  formatOrderType,
  formatOrderStatus,
  formatSessionStatus,
  formatExchangeName,
} from './format'

describe('formatNumber', () => {
  it('formats with thousand separators and default 2 decimals', () => {
    const result = formatNumber(1234567.89)
    expect(result).toContain('1')
    expect(result).toContain('234')
    expect(result).toContain('567')
    expect(result).toContain('89')
  })

  it('respects custom decimals', () => {
    expect(formatNumber(1.23456, 4)).toContain('1.2346')
  })

  it('returns "-" for null/undefined/NaN', () => {
    expect(formatNumber(null as unknown as number)).toBe('-')
    expect(formatNumber(undefined as unknown as number)).toBe('-')
    expect(formatNumber(NaN)).toBe('-')
  })

  it('formats zero', () => {
    expect(formatNumber(0)).toContain('0.00')
  })

  it('formats negative numbers', () => {
    const result = formatNumber(-1234.56)
    expect(result).toContain('1')
    expect(result).toContain('234')
    expect(result).toContain('56')
  })
})

describe('formatPrice', () => {
  it('uses 2 decimals for values >= 1000', () => {
    const result = formatPrice(50000.123)
    expect(result).toContain('50')
    expect(result).toContain('000')
    expect(result).toContain('12')
  })

  it('uses 4 decimals for values >= 1', () => {
    const result = formatPrice(12.34567)
    expect(result).toContain('12.3457')
  })

  it('uses 6 decimals for values >= 0.01', () => {
    const result = formatPrice(0.05)
    expect(result).toContain('0.050000')
  })

  it('uses 8 decimals for values < 0.01', () => {
    const result = formatPrice(0.001234)
    expect(result).toContain('0.00123400')
  })

  it('returns "-" for NaN', () => {
    expect(formatPrice(NaN)).toBe('-')
  })
})

describe('formatPercent', () => {
  it('adds + sign for positive values', () => {
    expect(formatPercent(5.12)).toMatch(/^\+.*5.*12.*%$/)
  })

  it('no + sign for negative values', () => {
    const result = formatPercent(-3.45)
    expect(result).not.toMatch(/^\+/)
    expect(result).toContain('3.45')
    expect(result).toContain('%')
  })

  it('handles zero', () => {
    expect(formatPercent(0)).toContain('0.00%')
  })

  it('returns "-" for NaN', () => {
    expect(formatPercent(NaN)).toBe('-')
  })
})

describe('formatLargeNumber', () => {
  it('formats billions', () => {
    expect(formatLargeNumber(1500000000)).toBe('1.50B')
  })

  it('formats millions', () => {
    expect(formatLargeNumber(2500000)).toBe('2.50M')
  })

  it('formats thousands', () => {
    expect(formatLargeNumber(12500)).toBe('12.50K')
  })

  it('formats small numbers with formatNumber', () => {
    const result = formatLargeNumber(999)
    expect(result).toContain('999')
  })

  it('handles negative large numbers', () => {
    expect(formatLargeNumber(-2500000)).toBe('-2.50M')
  })

  it('returns "-" for NaN', () => {
    expect(formatLargeNumber(NaN)).toBe('-')
  })
})

describe('formatVolume', () => {
  it('delegates to formatLargeNumber', () => {
    expect(formatVolume(1500000)).toBe(formatLargeNumber(1500000))
  })
})

describe('formatDateTime', () => {
  it('formats ISO string to default format', () => {
    const result = formatDateTime('2024-06-15T10:30:00Z')
    expect(result).toMatch(/2024-06-15/)
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('formats with custom format', () => {
    const result = formatDateTime('2024-06-15T10:30:00Z', 'YYYY/MM/DD')
    expect(result).toBe('2024/06/15')
  })

  it('formats number timestamp', () => {
    const ts = new Date('2024-06-15T00:00:00Z').getTime()
    const result = formatDateTime(ts)
    expect(result).toContain('2024-06-15')
  })

  it('returns "-" for falsy value', () => {
    expect(formatDateTime('')).toBe('-')
    expect(formatDateTime(0)).toBe('-')
  })
})

describe('formatDate', () => {
  it('returns YYYY-MM-DD', () => {
    expect(formatDate('2024-06-15T10:30:00Z')).toMatch(/2024-06-15/)
  })

  it('returns "-" for falsy', () => {
    expect(formatDate('')).toBe('-')
  })
})

describe('formatTime', () => {
  it('returns HH:mm:ss', () => {
    const result = formatTime('2024-06-15T10:30:45Z')
    expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('returns "-" for falsy', () => {
    expect(formatTime('')).toBe('-')
  })
})

describe('formatRelativeTime', () => {
  it('returns a relative time string', () => {
    const recent = new Date(Date.now() - 60000).toISOString()
    const result = formatRelativeTime(recent)
    expect(result).toBeTruthy()
    expect(result).not.toBe('-')
  })

  it('returns "-" for falsy', () => {
    expect(formatRelativeTime('')).toBe('-')
  })
})

describe('formatDuration', () => {
  it('formats days, hours, minutes, seconds', () => {
    expect(formatDuration(90061)).toBe('1天1小时1分1秒')
  })

  it('formats hours and minutes', () => {
    expect(formatDuration(3660)).toBe('1小时1分')
  })

  it('formats seconds only', () => {
    expect(formatDuration(45)).toBe('45秒')
  })

  it('formats zero', () => {
    expect(formatDuration(0)).toBe('0秒')
  })

  it('handles large values', () => {
    expect(formatDuration(172800)).toBe('2天')
  })

  it('returns "-" for NaN', () => {
    expect(formatDuration(NaN)).toBe('-')
  })
})

describe('formatFileSize', () => {
  it('formats bytes', () => {
    expect(formatFileSize(500)).toBe('500.00 B')
  })

  it('formats kilobytes', () => {
    expect(formatFileSize(1536)).toBe('1.50 KB')
  })

  it('formats megabytes', () => {
    expect(formatFileSize(1048576)).toBe('1.00 MB')
  })

  it('formats gigabytes', () => {
    expect(formatFileSize(1073741824)).toBe('1.00 GB')
  })

  it('returns "-" for NaN', () => {
    expect(formatFileSize(NaN)).toBe('-')
  })
})

describe('formatOrderSide', () => {
  it('formats buy', () => {
    expect(formatOrderSide('buy')).toBe('买入')
  })

  it('formats sell', () => {
    expect(formatOrderSide('sell')).toBe('卖出')
  })
})

describe('formatOrderType', () => {
  it('formats market', () => {
    expect(formatOrderType('market')).toBe('市价')
  })

  it('formats limit', () => {
    expect(formatOrderType('limit')).toBe('限价')
  })

  it('formats stop', () => {
    expect(formatOrderType('stop')).toBe('止损')
  })

  it('formats stop_limit', () => {
    expect(formatOrderType('stop_limit')).toBe('止损限价')
  })

  it('returns raw value for unknown type', () => {
    expect(formatOrderType('trailing_stop')).toBe('trailing_stop')
  })
})

describe('formatOrderStatus', () => {
  it.each([
    ['pending', '待处理'],
    ['open', '挂单中'],
    ['partial', '部分成交'],
    ['filled', '已成交'],
    ['cancelled', '已取消'],
    ['rejected', '已拒绝'],
  ])('formats %s to %s', (input, expected) => {
    expect(formatOrderStatus(input)).toBe(expected)
  })

  it('returns raw value for unknown status', () => {
    expect(formatOrderStatus('unknown')).toBe('unknown')
  })
})

describe('formatSessionStatus', () => {
  it.each([
    ['pending', '待启动'],
    ['running', '运行中'],
    ['completed', '已完成'],
    ['failed', '已失败'],
    ['stopped', '已停止'],
  ])('formats %s to %s', (input, expected) => {
    expect(formatSessionStatus(input)).toBe(expected)
  })

  it('returns raw value for unknown status', () => {
    expect(formatSessionStatus('cancelled')).toBe('cancelled')
  })
})

describe('formatExchangeName', () => {
  it.each([
    ['binance', 'Binance'],
    ['okx', 'OKX'],
    ['bybit', 'Bybit'],
    ['huobi', 'Huobi'],
    ['gate', 'Gate.io'],
  ])('formats %s to %s', (input, expected) => {
    expect(formatExchangeName(input)).toBe(expected)
  })

  it('returns raw value for unknown exchange', () => {
    expect(formatExchangeName('kraken')).toBe('kraken')
  })
})

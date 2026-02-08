import {
  getTheme,
  saveTheme,
  getLastExchange,
  saveLastExchange,
  getRecentSymbols,
  addRecentSymbol,
  getItem,
  setItem,
  removeItem,
} from './storage'

beforeEach(() => {
  localStorage.clear()
})

describe('getTheme / saveTheme', () => {
  it('returns "light" by default', () => {
    expect(getTheme()).toBe('light')
  })

  it('returns saved theme', () => {
    saveTheme('dark')
    expect(getTheme()).toBe('dark')
  })

  it('returns "light" for invalid stored value', () => {
    localStorage.setItem('squant_theme', 'invalid')
    expect(getTheme()).toBe('light')
  })
})

describe('getLastExchange / saveLastExchange', () => {
  it('returns "binance" by default', () => {
    expect(getLastExchange()).toBe('binance')
  })

  it('returns saved exchange', () => {
    saveLastExchange('okx')
    expect(getLastExchange()).toBe('okx')
  })

  it('round-trips correctly', () => {
    saveLastExchange('bybit')
    expect(getLastExchange()).toBe('bybit')
  })
})

describe('getRecentSymbols / addRecentSymbol', () => {
  it('returns empty array by default', () => {
    expect(getRecentSymbols()).toEqual([])
  })

  it('adds and retrieves symbols', () => {
    addRecentSymbol('okx', 'BTC/USDT')
    addRecentSymbol('okx', 'ETH/USDT')
    const symbols = getRecentSymbols()
    expect(symbols).toHaveLength(2)
    expect(symbols[0]).toEqual({ exchange: 'okx', symbol: 'ETH/USDT' })
    expect(symbols[1]).toEqual({ exchange: 'okx', symbol: 'BTC/USDT' })
  })

  it('deduplicates by moving to front', () => {
    addRecentSymbol('okx', 'BTC/USDT')
    addRecentSymbol('okx', 'ETH/USDT')
    addRecentSymbol('okx', 'BTC/USDT')
    const symbols = getRecentSymbols()
    expect(symbols).toHaveLength(2)
    expect(symbols[0]).toEqual({ exchange: 'okx', symbol: 'BTC/USDT' })
  })

  it('enforces limit', () => {
    for (let i = 0; i < 15; i++) {
      addRecentSymbol('okx', `SYM${i}/USDT`)
    }
    expect(getRecentSymbols()).toHaveLength(10)
  })

  it('respects custom limit parameter', () => {
    for (let i = 0; i < 8; i++) {
      addRecentSymbol('okx', `SYM${i}/USDT`, 5)
    }
    expect(getRecentSymbols(5)).toHaveLength(5)
  })

  it('handles corrupted data gracefully', () => {
    localStorage.setItem('squant_recent_symbols', 'not-json')
    expect(getRecentSymbols()).toEqual([])
  })
})

describe('getItem / setItem / removeItem', () => {
  it('round-trips an object', () => {
    setItem('test_key', { a: 1, b: 'two' })
    expect(getItem('test_key', null)).toEqual({ a: 1, b: 'two' })
  })

  it('returns default value when key not found', () => {
    expect(getItem('missing', 'default')).toBe('default')
  })

  it('returns default value on parse error', () => {
    localStorage.setItem('bad_json', 'not-valid-json')
    expect(getItem('bad_json', 42)).toBe(42)
  })

  it('removes item', () => {
    setItem('to_remove', 'value')
    removeItem('to_remove')
    expect(getItem('to_remove', null)).toBeNull()
  })

  it('handles arrays', () => {
    setItem('arr', [1, 2, 3])
    expect(getItem('arr', [])).toEqual([1, 2, 3])
  })

  it('handles primitive values', () => {
    setItem('num', 42)
    expect(getItem('num', 0)).toBe(42)
  })
})

const STORAGE_KEYS = {
  THEME: 'squant_theme',
  LAST_EXCHANGE: 'squant_last_exchange',
  RECENT_SYMBOLS: 'squant_recent_symbols',
} as const

// 主题
export function getTheme(): 'light' | 'dark' {
  try {
    const theme = localStorage.getItem(STORAGE_KEYS.THEME)
    return theme === 'dark' ? 'dark' : 'light'
  } catch (error) {
    console.error('Failed to load theme:', error)
    return 'light'
  }
}

export function saveTheme(theme: 'light' | 'dark'): void {
  try {
    localStorage.setItem(STORAGE_KEYS.THEME, theme)
  } catch (error) {
    console.error('Failed to save theme:', error)
  }
}

// 上次选择的交易所
export function getLastExchange(): string {
  try {
    return localStorage.getItem(STORAGE_KEYS.LAST_EXCHANGE) || 'okx'
  } catch (error) {
    console.error('Failed to load last exchange:', error)
    return 'okx'
  }
}

export function saveLastExchange(exchange: string): void {
  try {
    localStorage.setItem(STORAGE_KEYS.LAST_EXCHANGE, exchange)
  } catch (error) {
    console.error('Failed to save last exchange:', error)
  }
}

// 最近访问的交易对
export function getRecentSymbols(limit = 10): { exchange: string; symbol: string }[] {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.RECENT_SYMBOLS)
    const symbols = data ? JSON.parse(data) : []
    return symbols.slice(0, limit)
  } catch (error) {
    console.error('Failed to load recent symbols:', error)
    return []
  }
}

export function addRecentSymbol(exchange: string, symbol: string, limit = 10): void {
  try {
    const symbols = getRecentSymbols(limit)
    const index = symbols.findIndex((s) => s.exchange === exchange && s.symbol === symbol)

    if (index !== -1) {
      symbols.splice(index, 1)
    }

    symbols.unshift({ exchange, symbol })

    localStorage.setItem(
      STORAGE_KEYS.RECENT_SYMBOLS,
      JSON.stringify(symbols.slice(0, limit))
    )
  } catch (error) {
    console.error('Failed to add recent symbol:', error)
  }
}

// 通用存储方法
export function getItem<T>(key: string, defaultValue: T): T {
  try {
    const data = localStorage.getItem(key)
    return data ? JSON.parse(data) : defaultValue
  } catch (error) {
    console.error(`Failed to load ${key}:`, error)
    return defaultValue
  }
}

export function setItem<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (error) {
    console.error(`Failed to save ${key}:`, error)
  }
}

export function removeItem(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch (error) {
    console.error(`Failed to remove ${key}:`, error)
  }
}

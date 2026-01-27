// 市场数据 Store

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Ticker, KLine, WatchlistItem, TickerResponse, CandleResponse } from '@/types/market'
import { convertTickerResponse, convertCandleResponse } from '@/types/market'
import * as marketApi from '@/api/market'

// ========== 配置常量 ==========

/**
 * Store 配置
 */
const STORE_CONFIG = {
  // K线数据最大缓存条目数（LRU缓存）
  MAX_KLINE_CACHE_SIZE: 100,  // 最多缓存100个 {symbol}_{interval} 组合
  // Ticker数据过期时间（毫秒）
  TICKER_EXPIRY_TIME: 35 * 1000,  // 35秒（30秒刷新间隔 + 5秒缓冲）
  // K线数据过期时间（毫秒）
  KLINE_EXPIRY_TIME: 5 * 60 * 1000,  // 5分钟
  // 是否启用开发模式日志
  DEV_MODE: import.meta.env.MODE === 'development'
}

/**
 * LRU缓存项接口
 */
interface CacheItem<T> {
  data: T
  timestamp: number  // 数据更新时间戳
}

/**
 * 扩展的 KLine 缓存项（带时间戳）
 */
interface KLineCacheItem extends CacheItem<KLine[]> {
  symbol: string
  interval: string
}

/**
 * 扩展的 Ticker 缓存项（带时间戳）
 */
interface TickerCacheItem extends CacheItem<Ticker> {
  symbol: string
}

/**
 * 数据验证结果接口
 */
interface ValidationResult {
  valid: boolean
  errors: string[]
}

// ========== LRU缓存实现 ==========

/**
 * 简单的 LRU 缓存实现
 * @template K - 键类型
 * @template V - 值类型
 */
class LRUCache<K, V> {
  private cache: Map<K, V>
  private maxSize: number

  constructor(maxSize: number) {
    this.cache = new Map()
    this.maxSize = maxSize
  }

  /**
   * 获取值（访问后更新为最近使用）
   */
  get(key: K): V | undefined {
    if (!this.cache.has(key)) {
      return undefined
    }

    // 重新插入以更新为最近使用
    const value = this.cache.get(key)!
    this.cache.delete(key)
    this.cache.set(key, value)
    return value
  }

  /**
   * 设置值
   */
  set(key: K, value: V): void {
    // 如果已存在，先删除
    if (this.cache.has(key)) {
      this.cache.delete(key)
    }
    // 如果达到最大值，删除最旧的项
    else if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value
      this.cache.delete(firstKey)
    }

    this.cache.set(key, value)
  }

  /**
   * 删除值
   */
  delete(key: K): boolean {
    return this.cache.delete(key)
  }

  /**
   * 清空缓存
   */
  clear(): void {
    this.cache.clear()
  }

  /**
   * 获取大小
   */
  get size(): number {
    return this.cache.size
  }

  /**
   * 检查是否包含某个键
   */
  has(key: K): boolean {
    return this.cache.has(key)
  }

  /**
   * 获取所有键
   */
  keys(): IterableIterator<K> {
    return this.cache.keys()
  }

  /**
   * 获取所有值
   */
  values(): IterableIterator<V> {
    return this.cache.values()
  }

  /**
   * 遍历缓存
   */
  forEach(callbackfn: (value: V, key: K, map: Map<K, V>) => void): void {
    this.cache.forEach(callbackfn)
  }
}

// ========== 数据验证函数 ==========

/**
 * 验证 Ticker 数据
 */
function validateTicker(data: any): ValidationResult {
  const errors: string[] = []

  if (!data || typeof data !== 'object') {
    return { valid: false, errors: ['Ticker data is not an object'] }
  }

  // 必填字段验证
  if (typeof data.symbol !== 'string' || data.symbol.trim() === '') {
    errors.push('Ticker symbol is missing or invalid')
  }

  if (typeof data.lastPrice !== 'number' || isNaN(data.lastPrice)) {
    errors.push('Ticker lastPrice is missing or invalid')
  }

  if (typeof data.priceChangePercent !== 'number' || isNaN(data.priceChangePercent)) {
    errors.push('Ticker priceChangePercent is missing or invalid')
  }

  if (typeof data.volume !== 'number' || isNaN(data.volume)) {
    errors.push('Ticker volume is missing or invalid')
  }

  return {
    valid: errors.length === 0,
    errors
  }
}

/**
 * 验证 KLine 数据
 */
function validateKLine(data: any): ValidationResult {
  const errors: string[] = []

  if (!Array.isArray(data)) {
    return { valid: false, errors: ['KLine data is not an array'] }
  }

  // 验证数组中的每个元素
  for (let i = 0; i < data.length; i++) {
    const kline = data[i]
    if (!kline || typeof kline !== 'object') {
      errors.push(`KLine[${i}] is not an object`)
      continue
    }

    if (typeof kline.time !== 'number' || isNaN(kline.time)) {
      errors.push(`KLine[${i}] time is missing or invalid`)
    }

    if (typeof kline.open !== 'number' || isNaN(kline.open)) {
      errors.push(`KLine[${i}] open is missing or invalid`)
    }

    if (typeof kline.high !== 'number' || isNaN(kline.high)) {
      errors.push(`KLine[${i}] high is missing or invalid`)
    }

    if (typeof kline.low !== 'number' || isNaN(kline.low)) {
      errors.push(`KLine[${i}] low is missing or invalid`)
    }

    if (typeof kline.close !== 'number' || isNaN(kline.close)) {
      errors.push(`KLine[${i}] close is missing or invalid`)
    }
  }

  return {
    valid: errors.length === 0,
    errors
  }
}

/**
 * 验证 WatchlistItem 数据
 */
function validateWatchlistItem(data: any): ValidationResult {
  const errors: string[] = []

  if (!data || typeof data !== 'object') {
    return { valid: false, errors: ['WatchlistItem is not an object'] }
  }

  if (typeof data.id !== 'number' || isNaN(data.id)) {
    errors.push('WatchlistItem id is missing or invalid')
  }

  if (typeof data.symbol !== 'string' || data.symbol.trim() === '') {
    errors.push('WatchlistItem symbol is missing or invalid')
  }

  return {
    valid: errors.length === 0,
    errors
  }
}

/**
 * 安全转换 Ticker 数据（带验证）
 */
function safeConvertTicker(response: TickerResponse | any): Ticker | null {
  try {
    const ticker = convertTickerResponse(response)
    const validation = validateTicker(ticker)

    if (!validation.valid) {
      console.error('[MarketStore] Ticker validation failed:', validation.errors, response)
      return null
    }

    return ticker
  } catch (error) {
    console.error('[MarketStore] Failed to convert ticker:', error, response)
    return null
  }
}

/**
 * 安全转换 KLine 数据（带验证）
 */
function safeConvertKLine(response: CandleResponse[] | any): KLine[] | null {
  try {
    const klines = response.map(convertCandleResponse)
    const validation = validateKLine(klines)

    if (!validation.valid) {
      console.error('[MarketStore] KLine validation failed:', validation.errors, response)
      return null
    }

    return klines
  } catch (error) {
    console.error('[MarketStore] Failed to convert klines:', error, response)
    return null
  }
}

/**
 * 安全转换 Watchlist 数据（带验证）
 */
function safeConvertWatchlistItem(response: any): WatchlistItem | null {
  try {
    const item = response  // 假设已经转换
    const validation = validateWatchlistItem(item)

    if (!validation.valid) {
      console.error('[MarketStore] WatchlistItem validation failed:', validation.errors, response)
      return null
    }

    return item
  } catch (error) {
    console.error('[MarketStore] Failed to convert watchlist item:', error, response)
    return null
  }
}

export const useMarketStore = defineStore('market', () => {
  // ========== State ==========
  const tickers = ref<LRUCache<string, TickerCacheItem>>(new LRUCache(1000))  // 最多1000个ticker
  const kLines = ref<LRUCache<string, KLineCacheItem>>(new LRUCache(STORE_CONFIG.MAX_KLINE_CACHE_SIZE))
  const watchlist = ref<WatchlistItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // ========== Getters ==========
  const getTicker = computed(() => (symbol: string): Ticker | undefined => {
    const cacheItem = tickers.value.get(symbol)

    // 检查是否过期
    if (cacheItem) {
      const age = Date.now() - cacheItem.timestamp
      if (age > STORE_CONFIG.TICKER_EXPIRY_TIME) {
        if (STORE_CONFIG.DEV_MODE) {
          console.log(`[MarketStore] Ticker expired: ${symbol} (age: ${Math.floor(age / 1000)}s)`)
        }
        // 过期数据不返回
        return undefined
      }
      return cacheItem.data
    }

    return undefined
  })

  const getKLines = computed(() => (symbol: string, interval: string): KLine[] => {
    const key = `${symbol}_${interval}`
    const cacheItem = kLines.value.get(key)

    // 检查是否过期
    if (cacheItem) {
      const age = Date.now() - cacheItem.timestamp
      if (age > STORE_CONFIG.KLINE_EXPIRY_TIME) {
        if (STORE_CONFIG.DEV_MODE) {
          console.log(`[MarketStore] KLine expired: ${key} (age: ${Math.floor(age / 1000)}s)`)
        }
        // 过期数据返回空数组，不删除（由清理机制处理）
        return []
      }
      return cacheItem.data
    }

    return []
  })

  const allTickers = computed(() => {
    const items: Ticker[] = []
    tickers.value.forEach((item) => {
      const age = Date.now() - item.timestamp
      if (age <= STORE_CONFIG.TICKER_EXPIRY_TIME) {
        items.push(item.data)
      }
    })
    return items
  })

  const watchlistSymbols = computed(() => {
    return watchlist.value.map(item => item.symbol)
  })

  // 统计信息（用于监控）
  const stats = computed(() => ({
    tickerCount: tickers.value.size,
    klineCount: kLines.value.size,
    watchlistCount: watchlist.value.length,
    isLoading: loading.value,
    error: error.value
  }))

  // ========== Actions ==========

  /**
   * 清理过期的数据
   * @param force - 是否强制清理所有过期数据（默认false）
   */
  const cleanupExpiredData = (force = false): void => {
    const now = Date.now()
    let removedTickers = 0
    let removedKLines = 0

    // 清理过期的 Ticker
    const expiredTickerKeys: string[] = []
    tickers.value.forEach((item, key) => {
      const age = now - item.timestamp
      if (force || age > STORE_CONFIG.TICKER_EXPIRY_TIME) {
        expiredTickerKeys.push(key)
      }
    })

    expiredTickerKeys.forEach(key => {
      tickers.value.delete(key)
      removedTickers++
    })

    // 清理过期的 KLine
    const expiredKLineKeys: string[] = []
    kLines.value.forEach((item, key) => {
      const age = now - item.timestamp
      if (force || age > STORE_CONFIG.KLINE_EXPIRY_TIME) {
        expiredKLineKeys.push(key)
      }
    })

    expiredKLineKeys.forEach(key => {
      kLines.value.delete(key)
      removedKLines++
    })

    if (STORE_CONFIG.DEV_MODE && (removedTickers > 0 || removedKLines > 0)) {
      console.log(`[MarketStore] Cleanup completed: ${removedTickers} tickers, ${removedKLines} klines removed`)
    }
  }

  /**
   * 获取热门币种
   */
  const fetchTickers = async (): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      // 先清理过期数据
      cleanupExpiredData()

      const data = await marketApi.getTickers()

      // 验证并转换数据
      let validCount = 0
      let invalidCount = 0

      data.forEach((tickerResponse) => {
        const ticker = safeConvertTicker(tickerResponse)
        if (ticker) {
          tickers.value.set(ticker.symbol, {
            data: ticker,
            timestamp: Date.now(),
            symbol: ticker.symbol
          })
          validCount++
        } else {
          invalidCount++
        }
      })

      if (STORE_CONFIG.DEV_MODE && invalidCount > 0) {
        console.warn(`[MarketStore] ${invalidCount} invalid tickers filtered out`)
      }

      if (validCount === 0) {
        throw new Error('No valid tickers received from API')
      }

    } catch (err: any) {
      const errorMsg = err.message || 'Failed to fetch tickers'
      error.value = errorMsg
      console.error('[MarketStore] Failed to fetch tickers:', err)

      // 错误恢复：保留旧数据，但标记为错误状态
      if (STORE_CONFIG.DEV_MODE) {
        console.log('[MarketStore] Error recovery: keeping old ticker data')
      }

      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取K线数据
   */
  const fetchKLines = async (symbol: string, interval: string, limit = 100): Promise<void> => {
    error.value = null

    try {
      const data = await marketApi.getCandles(symbol, interval, limit)

      // 验证并转换数据
      const klines = safeConvertKLine(data)

      if (!klines) {
        throw new Error('Invalid KLine data received from API')
      }

      const key = `${symbol}_${interval}`
      kLines.value.set(key, {
        data: klines,
        timestamp: Date.now(),
        symbol,
        interval
      })

      if (STORE_CONFIG.DEV_MODE) {
        console.log(`[MarketStore] Fetched ${klines.length} klines for ${key}`)
      }

    } catch (err: any) {
      const errorMsg = err.message || 'Failed to fetch klines'
      error.value = errorMsg
      console.error('[MarketStore] Failed to fetch klines:', err)

      // 错误恢复：删除旧数据，让组件重新请求
      const key = `${symbol}_${interval}`
      kLines.value.delete(key)

      throw err
    }
  }

  /**
   * 获取自选列表
   */
  const fetchWatchlist = async (): Promise<void> => {
    error.value = null

    try {
      const data = await marketApi.getWatchlist()

      // 验证数据
      const validItems: WatchlistItem[] = []
      let invalidCount = 0

      data.forEach((item: any) => {
        const validItem = safeConvertWatchlistItem(item)
        if (validItem) {
          validItems.push(validItem)
        } else {
          invalidCount++
        }
      })

      if (STORE_CONFIG.DEV_MODE && invalidCount > 0) {
        console.warn(`[MarketStore] ${invalidCount} invalid watchlist items filtered out`)
      }

      watchlist.value = validItems

    } catch (err: any) {
      const errorMsg = err.message || 'Failed to fetch watchlist'
      error.value = errorMsg
      console.error('[MarketStore] Failed to fetch watchlist:', err)
      throw err
    }
  }

  /**
   * 添加到自选
   */
  const addToWatchlist = async (symbol: string, notes?: string): Promise<void> => {
    error.value = null

    try {
      const item = await marketApi.addToWatchlist(symbol, notes)

      // 验证数据
      const validItem = safeConvertWatchlistItem(item)
      if (!validItem) {
        throw new Error('Invalid watchlist item received from API')
      }

      watchlist.value.push(validItem)

    } catch (err: any) {
      const errorMsg = err.message || 'Failed to add to watchlist'
      error.value = errorMsg
      console.error('[MarketStore] Failed to add to watchlist:', err)
      throw err
    }
  }

  /**
   * 更新自选
   */
  const updateWatchlist = async (id: number, notes?: string): Promise<void> => {
    error.value = null

    try {
      const item = await marketApi.updateWatchlist(id, notes)

      // 验证数据
      const validItem = safeConvertWatchlistItem(item)
      if (!validItem) {
        throw new Error('Invalid watchlist item received from API')
      }

      const index = watchlist.value.findIndex(w => w.id === id)
      if (index !== -1) {
        watchlist.value[index] = validItem
      } else {
        console.warn(`[MarketStore] Watchlist item ${id} not found, adding it`)
        watchlist.value.push(validItem)
      }

    } catch (err: any) {
      const errorMsg = err.message || 'Failed to update watchlist'
      error.value = errorMsg
      console.error('[MarketStore] Failed to update watchlist:', err)
      throw err
    }
  }

  /**
   * 从自选删除
   */
  const removeFromWatchlist = async (id: number): Promise<void> => {
    error.value = null

    try {
      await marketApi.removeFromWatchlist(id)
      watchlist.value = watchlist.value.filter(w => w.id !== id)

    } catch (err: any) {
      const errorMsg = err.message || 'Failed to remove from watchlist'
      error.value = errorMsg
      console.error('[MarketStore] Failed to remove from watchlist:', err)
      throw err
    }
  }

  /**
   * 更新行情数据（从 WebSocket）
   */
  const updateTicker = (data: any): void => {
    const ticker = safeConvertTicker(data)
    if (ticker) {
      tickers.value.set(ticker.symbol, {
        data: ticker,
        timestamp: Date.now(),
        symbol: ticker.symbol
      })
    } else {
      console.warn('[MarketStore] Invalid ticker data received from WebSocket:', data)
    }
  }

  /**
   * 清除数据
   */
  const clear = (): void => {
    tickers.value.clear()
    kLines.value.clear()
    watchlist.value = []
    error.value = null

    if (STORE_CONFIG.DEV_MODE) {
      console.log('[MarketStore] All data cleared')
    }
  }

  /**
   * 重置错误状态
   */
  const clearError = (): void => {
    error.value = null
  }

  /**
   * 获取缓存的 KLine keys（用于调试）
   */
  const getKLineKeys = (): string[] => {
    return Array.from(kLines.value.keys())
  }

  /**
   * 获取缓存的 Ticker symbols（用于调试）
   */
  const getTickerSymbols = (): string[] => {
    return Array.from(tickers.value.keys())
  }

  // ========== 自动清理机制 ==========

  /**
   * 定时清理过期数据
   * 每30秒执行一次
   */
  let cleanupTimer: ReturnType<typeof setInterval> | null = null

  const startAutoCleanup = (): void => {
    if (cleanupTimer) {
      return // 已经启动
    }

    if (STORE_CONFIG.DEV_MODE) {
      console.log('[MarketStore] Starting auto cleanup (30s interval)')
    }

    cleanupTimer = setInterval(() => {
      cleanupExpiredData(true)
    }, 30 * 1000)  // 30秒
  }

  const stopAutoCleanup = (): void => {
    if (cleanupTimer) {
      clearInterval(cleanupTimer)
      cleanupTimer = null

      if (STORE_CONFIG.DEV_MODE) {
        console.log('[MarketStore] Stopped auto cleanup')
      }
    }
  }

  // ========== Store 生命周期 ==========

  // 监听 watchlist 变化，自动验证
  watch(() => watchlist.value, (newWatchlist) => {
    // 可以在这里添加额外的验证逻辑
    if (STORE_CONFIG.DEV_MODE && newWatchlist.length > 0) {
      console.log(`[MarketStore] Watchlist updated: ${newWatchlist.length} items`)
    }
  }, { deep: true })

  return {
    // State
    tickers,
    kLines,
    watchlist,
    loading,
    error,

    // Getters
    getTicker,
    getKLines,
    allTickers,
    watchlistSymbols,
    stats,

    // Actions
    fetchTickers,
    fetchKLines,
    fetchWatchlist,
    addToWatchlist,
    updateWatchlist,
    removeFromWatchlist,
    updateTicker,
    clear,
    clearError,
    cleanupExpiredData,

    // 调试工具
    getKLineKeys,
    getTickerSymbols,

    // 生命周期管理
    startAutoCleanup,
    stopAutoCleanup
  }
})

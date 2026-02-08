import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ticker, Timeframe } from '@/types'
import type { WatchlistItemResponse } from '@/types/generated'
import * as marketApi from '@/api/market'

export const useMarketStore = defineStore('market', () => {
  // State
  const exchanges = ref<string[]>(['okx', 'binance', 'bybit'])
  const currentExchange = ref<string>('okx')
  const supportedExchanges = ref<string[]>(['okx', 'binance', 'bybit'])
  const tickers = ref<Map<string, Ticker>>(new Map())
  const watchlist = ref<WatchlistItemResponse[]>([])
  const watchlistLoading = ref(false)
  const timeframes = ref<Timeframe[]>(['1m', '5m', '15m', '30m', '1h', '4h', '1d'])
  const loading = ref(false)
  const exchangeSwitching = ref(false)

  // REST API polling fallback for infrequent WebSocket updates
  let pollingTimer: ReturnType<typeof setInterval> | null = null
  const POLLING_INTERVAL = 10000  // 10 seconds - fallback refresh rate

  // Getters
  const tickerList = computed(() => Array.from(tickers.value.values()))

  const watchlistTickers = computed(() => {
    return watchlist.value
      .map((item) => {
        const key = `${item.exchange}:${item.symbol}`
        return tickers.value.get(key)
      })
      .filter((t): t is Ticker => t !== undefined)
  })

  const isInWatchlist = computed(() => (exchange: string, symbol: string) => {
    return watchlist.value.some((item) => item.exchange === exchange && item.symbol === symbol)
  })

  // 获取单个 ticker
  function getTicker(exchange: string, symbol: string): Ticker | undefined {
    const key = `${exchange}:${symbol}`
    return tickers.value.get(key)
  }

  // Actions
  async function loadExchanges() {
    try {
      const response = await marketApi.getExchanges()
      exchanges.value = response.data
      supportedExchanges.value = response.data
      if (exchanges.value.length > 0 && !exchanges.value.includes(currentExchange.value)) {
        currentExchange.value = exchanges.value[0]
      }
    } catch (error) {
      console.error('Failed to load exchanges:', error)
    }
  }

  async function loadCurrentExchange() {
    try {
      const response = await marketApi.getExchangeConfig()
      currentExchange.value = response.data.current
      supportedExchanges.value = response.data.supported
      exchanges.value = response.data.supported
    } catch (error) {
      console.error('Failed to load current exchange:', error)
    }
  }

  async function switchExchange(exchange: string) {
    if (exchange === currentExchange.value) {
      return
    }

    exchangeSwitching.value = true
    try {
      // Call backend to switch exchange
      await marketApi.setExchange(exchange)
      currentExchange.value = exchange

      // Clear old ticker data
      tickers.value.clear()

      // Reload all tickers from new exchange
      await loadAllTickers()
    } catch (error) {
      console.error('Failed to switch exchange:', error)
      throw error
    } finally {
      exchangeSwitching.value = false
    }
  }

  async function loadTickers(symbols?: string[]) {
    loading.value = true
    try {
      const response = await marketApi.getTickers(symbols)
      response.data.forEach((ticker) => {
        const key = `${ticker.exchange}:${ticker.symbol}`
        tickers.value.set(key, ticker)
      })
      return response.data
    } catch (error) {
      console.error('Failed to load tickers:', error)
      return []
    } finally {
      loading.value = false
    }
  }

  async function loadAllTickers() {
    loading.value = true
    try {
      // 获取全部行情数据，由前端进行排序和分页
      const response = await marketApi.getAllTickers()
      // 清空旧数据，重新填充
      tickers.value.clear()
      response.data.forEach((ticker) => {
        const key = `${ticker.exchange}:${ticker.symbol}`
        tickers.value.set(key, ticker)
      })
      return response.data
    } catch (error) {
      console.error('Failed to load tickers:', error)
      return []
    } finally {
      loading.value = false
    }
  }

  function updateTicker(ticker: Ticker) {
    const key = `${ticker.exchange}:${ticker.symbol}`
    tickers.value.set(key, ticker)
  }

  /**
   * Update only price-related fields from WebSocket, preserve volume data
   * This is needed because OKX WebSocket volume data appears to be unreliable
   */
  function updateTickerPrice(ticker: Ticker) {
    const key = `${ticker.exchange}:${ticker.symbol}`
    const existing = tickers.value.get(key)

    if (existing) {
      // Only update price-related fields, preserve volume data from REST API
      tickers.value.set(key, {
        ...existing,
        last_price: ticker.last_price,
        bid_price: ticker.bid_price,
        ask_price: ticker.ask_price,
        high_24h: ticker.high_24h,
        low_24h: ticker.low_24h,
        change_24h: ticker.change_24h,
        change_percent_24h: ticker.change_percent_24h,
        timestamp: ticker.timestamp,
        // Preserve volume fields from initial REST API load:
        // volume_24h: existing.volume_24h,
        // quote_volume_24h: existing.quote_volume_24h,
      })
    } else {
      // If ticker doesn't exist, set it completely
      tickers.value.set(key, ticker)
    }
  }

  // 从后端加载自选列表
  async function loadWatchlist() {
    watchlistLoading.value = true
    try {
      const response = await marketApi.getWatchlistApi()
      watchlist.value = response.data
    } catch (error) {
      console.error('Failed to load watchlist:', error)
    } finally {
      watchlistLoading.value = false
    }
  }

  // 添加到自选列表
  async function addToWatchlist(exchange: string, symbol: string) {
    if (isInWatchlist.value(exchange, symbol)) {
      return
    }
    try {
      const response = await marketApi.addWatchlistItem(exchange, symbol)
      watchlist.value.push(response.data)
    } catch (error) {
      console.error('Failed to add to watchlist:', error)
      throw error
    }
  }

  // 从自选列表移除
  async function removeFromWatchlist(exchange: string, symbol: string) {
    const item = watchlist.value.find(
      (item) => item.exchange === exchange && item.symbol === symbol
    )
    if (!item) {
      return
    }
    try {
      await marketApi.removeWatchlistItem(item.id)
      const index = watchlist.value.findIndex((i) => i.id === item.id)
      if (index !== -1) {
        watchlist.value.splice(index, 1)
      }
    } catch (error) {
      console.error('Failed to remove from watchlist:', error)
      throw error
    }
  }

  // 重新排序自选列表
  async function reorderWatchlist(fromIndex: number, toIndex: number) {
    // 先在本地更新顺序以提供即时反馈
    const item = watchlist.value.splice(fromIndex, 1)[0]
    watchlist.value.splice(toIndex, 0, item)

    // 计算新的 sort_order 并同步到后端
    const reorderItems = watchlist.value.map((item, index) => ({
      id: item.id,
      sort_order: index,
    }))

    try {
      const response = await marketApi.reorderWatchlistApi(reorderItems)
      watchlist.value = response.data
    } catch (error) {
      console.error('Failed to reorder watchlist:', error)
      // 回滚本地更改 - 重新加载
      await loadWatchlist()
      throw error
    }
  }

  function setCurrentExchange(exchange: string) {
    currentExchange.value = exchange
  }

  async function loadTimeframes(exchange: string) {
    try {
      const response = await marketApi.getTimeframes(exchange)
      timeframes.value = response.data
    } catch (error) {
      console.error('Failed to load timeframes:', error)
    }
  }

  /**
   * Start REST API polling as fallback for infrequent WebSocket updates.
   * This ensures tickers are refreshed even when OKX doesn't send WebSocket updates.
   */
  function startPolling() {
    if (pollingTimer) {
      return  // Already polling
    }
    console.debug('Starting REST API polling fallback')
    pollingTimer = setInterval(async () => {
      try {
        // Only refresh if we have tickers loaded
        if (tickers.value.size > 0) {
          const response = await marketApi.getAllTickers()
          response.data.forEach((ticker) => {
            const key = `${ticker.exchange}:${ticker.symbol}`
            const existing = tickers.value.get(key)
            // Only update if the REST data is newer
            if (!existing || ticker.timestamp > existing.timestamp) {
              tickers.value.set(key, ticker)
            }
          })
        }
      } catch (error) {
        // Silent fail - WebSocket is primary, this is just fallback
        console.debug('REST API polling refresh failed:', error)
      }
    }, POLLING_INTERVAL)
  }

  /**
   * Stop REST API polling.
   */
  function stopPolling() {
    if (pollingTimer) {
      console.debug('Stopping REST API polling fallback')
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  return {
    // State
    exchanges,
    currentExchange,
    supportedExchanges,
    tickers,
    watchlist,
    watchlistLoading,
    timeframes,
    loading,
    exchangeSwitching,
    // Getters
    tickerList,
    watchlistTickers,
    isInWatchlist,
    getTicker,
    // Actions
    loadExchanges,
    loadCurrentExchange,
    loadTickers,
    loadAllTickers,
    loadWatchlist,
    updateTicker,
    updateTickerPrice,
    addToWatchlist,
    removeFromWatchlist,
    reorderWatchlist,
    setCurrentExchange,
    switchExchange,
    loadTimeframes,
    startPolling,
    stopPolling,
  }
})

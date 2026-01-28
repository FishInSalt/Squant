import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Ticker, WatchlistItem, Timeframe } from '@/types'
import * as marketApi from '@/api/market'
import { getWatchlist, saveWatchlist } from '@/utils/storage'

export const useMarketStore = defineStore('market', () => {
  // State
  const exchanges = ref<string[]>([])
  const currentExchange = ref<string>('binance')
  const tickers = ref<Map<string, Ticker>>(new Map())
  const watchlist = ref<WatchlistItem[]>(getWatchlist())
  const timeframes = ref<Timeframe[]>(['1m', '5m', '15m', '30m', '1h', '4h', '1d'])
  const loading = ref(false)

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

  // Actions
  async function loadExchanges() {
    try {
      const response = await marketApi.getExchanges()
      exchanges.value = response.data
      if (exchanges.value.length > 0 && !exchanges.value.includes(currentExchange.value)) {
        currentExchange.value = exchanges.value[0]
      }
    } catch (error) {
      console.error('Failed to load exchanges:', error)
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
    } catch (error) {
      console.error('Failed to load tickers:', error)
    } finally {
      loading.value = false
    }
  }

  async function loadHotTickers(exchange?: string, limit?: number) {
    loading.value = true
    try {
      const response = await marketApi.getHotTickers(exchange, limit)
      response.data.forEach((ticker) => {
        const key = `${ticker.exchange}:${ticker.symbol}`
        tickers.value.set(key, ticker)
      })
      return response.data
    } catch (error) {
      console.error('Failed to load hot tickers:', error)
      return []
    } finally {
      loading.value = false
    }
  }

  function updateTicker(ticker: Ticker) {
    const key = `${ticker.exchange}:${ticker.symbol}`
    tickers.value.set(key, ticker)
  }

  function addToWatchlist(exchange: string, symbol: string) {
    if (!isInWatchlist.value(exchange, symbol)) {
      watchlist.value.push({
        exchange,
        symbol,
        addedAt: Date.now(),
      })
      saveWatchlist(watchlist.value)
    }
  }

  function removeFromWatchlist(exchange: string, symbol: string) {
    const index = watchlist.value.findIndex(
      (item) => item.exchange === exchange && item.symbol === symbol
    )
    if (index !== -1) {
      watchlist.value.splice(index, 1)
      saveWatchlist(watchlist.value)
    }
  }

  function reorderWatchlist(fromIndex: number, toIndex: number) {
    const item = watchlist.value.splice(fromIndex, 1)[0]
    watchlist.value.splice(toIndex, 0, item)
    saveWatchlist(watchlist.value)
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

  return {
    // State
    exchanges,
    currentExchange,
    tickers,
    watchlist,
    timeframes,
    loading,
    // Getters
    tickerList,
    watchlistTickers,
    isInWatchlist,
    // Actions
    loadExchanges,
    loadTickers,
    loadHotTickers,
    updateTicker,
    addToWatchlist,
    removeFromWatchlist,
    reorderWatchlist,
    setCurrentExchange,
    loadTimeframes,
  }
})

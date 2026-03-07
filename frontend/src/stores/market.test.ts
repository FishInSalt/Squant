import { setActivePinia, createPinia } from 'pinia'
import { useMarketStore } from './market'
import { createMockTicker, createMockWatchlistItem, wrapApiResponse } from '@/__tests__/fixtures'
import * as marketApi from '@/api/market'

vi.mock('@/api/market')

const mockedApi = vi.mocked(marketApi)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useMarketStore', () => {
  describe('initial state', () => {
    it('has default values', () => {
      const store = useMarketStore()
      expect(store.exchanges).toEqual(['okx', 'binance', 'bybit'])
      expect(store.currentExchange).toBe('okx')
      expect(store.tickers.size).toBe(0)
      expect(store.watchlist).toEqual([])
      expect(store.loading).toBe(false)
    })
  })

  describe('tickerList', () => {
    it('returns array from Map', () => {
      const store = useMarketStore()
      const ticker = createMockTicker()
      store.tickers.set('okx:BTC/USDT', ticker)
      expect(store.tickerList).toHaveLength(1)
      expect(store.tickerList[0]).toStrictEqual(ticker)
    })

    it('returns empty array when no tickers', () => {
      const store = useMarketStore()
      expect(store.tickerList).toEqual([])
    })
  })

  describe('watchlistTickers', () => {
    it('returns tickers matching watchlist items', () => {
      const store = useMarketStore()
      const ticker = createMockTicker({ exchange: 'okx', symbol: 'BTC/USDT' })
      store.tickers.set('okx:BTC/USDT', ticker)
      store.watchlist = [createMockWatchlistItem({ exchange: 'okx', symbol: 'BTC/USDT' })]
      expect(store.watchlistTickers).toHaveLength(1)
      expect(store.watchlistTickers[0].symbol).toBe('BTC/USDT')
    })

    it('filters out items without matching ticker', () => {
      const store = useMarketStore()
      store.watchlist = [createMockWatchlistItem({ exchange: 'okx', symbol: 'XRP/USDT' })]
      expect(store.watchlistTickers).toHaveLength(0)
    })
  })

  describe('isInWatchlist', () => {
    it('returns true when item exists', () => {
      const store = useMarketStore()
      store.watchlist = [createMockWatchlistItem({ exchange: 'okx', symbol: 'BTC/USDT' })]
      expect(store.isInWatchlist('okx', 'BTC/USDT')).toBe(true)
    })

    it('returns false when not in watchlist', () => {
      const store = useMarketStore()
      expect(store.isInWatchlist('okx', 'ETH/USDT')).toBe(false)
    })
  })

  describe('getTicker', () => {
    it('finds ticker by exchange:symbol key', () => {
      const store = useMarketStore()
      const ticker = createMockTicker()
      store.tickers.set('okx:BTC/USDT', ticker)
      expect(store.getTicker('okx', 'BTC/USDT')).toStrictEqual(ticker)
    })

    it('returns undefined when not found', () => {
      const store = useMarketStore()
      expect(store.getTicker('okx', 'UNKNOWN')).toBeUndefined()
    })
  })

  describe('updateTicker', () => {
    it('sets ticker in Map', () => {
      const store = useMarketStore()
      const ticker = createMockTicker()
      store.updateTicker(ticker)
      expect(store.tickers.get('okx:BTC/USDT')).toStrictEqual(ticker)
    })
  })

  describe('updateTickerPrice', () => {
    it('updates only price fields when existing', () => {
      const store = useMarketStore()
      const original = createMockTicker({ volume_24h: 9999 })
      store.tickers.set('okx:BTC/USDT', original)
      const update = createMockTicker({ last_price: 55000, volume_24h: 0 })
      store.updateTickerPrice(update)
      const result = store.tickers.get('okx:BTC/USDT')!
      expect(result.last_price).toBe(55000)
      // Volume preserved from original
      expect(result.volume_24h).toBe(9999)
    })

    it('sets fully when ticker does not exist', () => {
      const store = useMarketStore()
      const ticker = createMockTicker({ last_price: 55000 })
      store.updateTickerPrice(ticker)
      expect(store.tickers.get('okx:BTC/USDT')!.last_price).toBe(55000)
    })
  })

  describe('loadExchanges', () => {
    it('sets exchanges from API', async () => {
      const store = useMarketStore()
      mockedApi.getExchanges.mockResolvedValue({ data: ['binance', 'okx'], code: 0, message: 'success' })
      await store.loadExchanges()
      expect(store.exchanges).toEqual(['binance', 'okx'])
    })

    it('handles error gracefully', async () => {
      const store = useMarketStore()
      mockedApi.getExchanges.mockRejectedValue(new Error('Network error'))
      await store.loadExchanges()
      // Should not throw, keeps default
      expect(store.exchanges).toBeTruthy()
    })
  })

  describe('switchExchange', () => {
    it('clears tickers and reloads', async () => {
      const store = useMarketStore()
      store.tickers.set('okx:BTC/USDT', createMockTicker())
      mockedApi.setExchange.mockResolvedValue(wrapApiResponse({ current: 'binance', previous: 'okx' }))
      mockedApi.getAllTickers.mockResolvedValue({ ...wrapApiResponse([]), data: [] })
      await store.switchExchange('binance')
      expect(store.currentExchange).toBe('binance')
      expect(store.tickers.size).toBe(0)
    })

    it('no-op when same exchange', async () => {
      const store = useMarketStore()
      await store.switchExchange('okx')
      expect(mockedApi.setExchange).not.toHaveBeenCalled()
    })
  })

  describe('loadWatchlist', () => {
    it('sets watchlist from API', async () => {
      const store = useMarketStore()
      const items = [createMockWatchlistItem()]
      mockedApi.getWatchlistApi.mockResolvedValue(wrapApiResponse(items))
      await store.loadWatchlist()
      expect(store.watchlist).toEqual(items)
    })
  })

  describe('addToWatchlist', () => {
    it('adds item from API response', async () => {
      const store = useMarketStore()
      const item = createMockWatchlistItem()
      mockedApi.addWatchlistItem.mockResolvedValue(wrapApiResponse(item))
      await store.addToWatchlist('okx', 'BTC/USDT')
      expect(store.watchlist).toHaveLength(1)
    })

    it('skips if already in watchlist', async () => {
      const store = useMarketStore()
      store.watchlist = [createMockWatchlistItem({ exchange: 'okx', symbol: 'BTC/USDT' })]
      await store.addToWatchlist('okx', 'BTC/USDT')
      expect(mockedApi.addWatchlistItem).not.toHaveBeenCalled()
    })
  })

  describe('removeFromWatchlist', () => {
    it('removes item and calls API', async () => {
      const store = useMarketStore()
      store.watchlist = [createMockWatchlistItem({ id: 'wl-1', exchange: 'okx', symbol: 'BTC/USDT' })]
      mockedApi.removeWatchlistItem.mockResolvedValue(wrapApiResponse(undefined as unknown as void))
      await store.removeFromWatchlist('okx', 'BTC/USDT')
      expect(store.watchlist).toHaveLength(0)
    })

    it('no-op when item not found', async () => {
      const store = useMarketStore()
      await store.removeFromWatchlist('okx', 'UNKNOWN')
      expect(mockedApi.removeWatchlistItem).not.toHaveBeenCalled()
    })
  })
})

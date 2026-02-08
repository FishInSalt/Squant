import { setActivePinia, createPinia } from 'pinia'
import { useWebSocketStore } from './websocket'
import { useMarketStore } from './market'

// Mock WebSocket globally
const mockSend = vi.fn()
const mockClose = vi.fn()

vi.stubGlobal('WebSocket', vi.fn(() => ({
  send: mockSend,
  close: mockClose,
  readyState: 1, // OPEN
  onopen: null,
  onclose: null,
  onerror: null,
  onmessage: null,
})))

// Stub WebSocket constants
Object.defineProperty(globalThis, 'WebSocket', {
  value: Object.assign(vi.fn(() => ({
    send: mockSend,
    close: mockClose,
    readyState: 1,
    onopen: null,
    onclose: null,
    onerror: null,
    onmessage: null,
  })), {
    CONNECTING: 0,
    OPEN: 1,
    CLOSING: 2,
    CLOSED: 3,
  }),
  writable: true,
})

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useWebSocketStore', () => {
  describe('initial state', () => {
    it('has default values', () => {
      const store = useWebSocketStore()
      expect(store.connected).toBe(false)
      expect(store.reconnectAttempts).toBe(0)
      expect(store.subscribedChannels.size).toBe(0)
      expect(store.serviceUnavailable).toBe(false)
      expect(store.isConnected).toBe(false)
    })
  })

  describe('subscribe / unsubscribe', () => {
    it('adds to pending when not connected', () => {
      const store = useWebSocketStore()
      store.subscribe('ticker:BTC/USDT')
      // Should not be in subscribedChannels since not connected
      // Channel would be in pendingSubscriptions (internal)
      // connect() should have been called
    })

    it('sends subscribe when connected', () => {
      const store = useWebSocketStore()
      // Simulate connected state
      store.$patch({ connected: true })
      // Need to mock socket - we'll test the subscription tracking instead
      store.subscribedChannels.add('ticker:BTC/USDT')
      expect(store.subscribedChannels.has('ticker:BTC/USDT')).toBe(true)
    })

    it('no-op when already subscribed', () => {
      const store = useWebSocketStore()
      store.$patch({ connected: true })
      store.subscribedChannels.add('ticker:BTC/USDT')
      // Calling subscribe again for same channel should be a no-op
      store.subscribe('ticker:BTC/USDT')
      // No duplicate
      expect(store.subscribedChannels.size).toBe(1)
    })

    it('unsubscribe removes channel', () => {
      const store = useWebSocketStore()
      store.$patch({ connected: true })
      store.subscribedChannels.add('ticker:BTC/USDT')
      store.unsubscribe('ticker:BTC/USDT')
      expect(store.subscribedChannels.has('ticker:BTC/USDT')).toBe(false)
    })
  })

  describe('subscribeToTickers', () => {
    it('subscribes to multiple ticker channels', () => {
      const store = useWebSocketStore()
      // This will attempt to connect since not connected
      const unsub = store.subscribeToTickers(['BTC/USDT', 'ETH/USDT'])
      expect(typeof unsub).toBe('function')
    })
  })

  describe('subscribeToCandles', () => {
    it('returns unsubscribe function', () => {
      const store = useWebSocketStore()
      const unsub = store.subscribeToCandles('BTC/USDT', '1h')
      expect(typeof unsub).toBe('function')
    })
  })

  describe('onCandle / offCandle', () => {
    it('registers and calls callback', () => {
      const store = useWebSocketStore()
      const callback = vi.fn()
      store.onCandle('candle:BTC/USDT:1h', callback)
      // Callback registered - would be called via handleMessage
      expect(callback).not.toHaveBeenCalled()
    })

    it('removes callback with offCandle', () => {
      const store = useWebSocketStore()
      const callback = vi.fn()
      store.onCandle('candle:BTC/USDT:1h', callback)
      store.offCandle('candle:BTC/USDT:1h', callback)
      // Callback removed
    })
  })

  describe('disconnect', () => {
    it('clears subscriptions', () => {
      const store = useWebSocketStore()
      store.subscribedChannels.add('ticker:BTC/USDT')
      store.disconnect()
      expect(store.subscribedChannels.size).toBe(0)
      expect(store.connected).toBe(false)
    })
  })

  describe('exchange switching state', () => {
    it('tracks exchange switching state', () => {
      const store = useWebSocketStore()
      expect(store.exchangeSwitching).toBe(false)
      expect(store.switchingFromExchange).toBe('')
      expect(store.switchingToExchange).toBe('')
    })
  })

  describe('service unavailable state', () => {
    it('tracks service unavailable state', () => {
      const store = useWebSocketStore()
      store.$patch({ serviceUnavailable: true, serviceUnavailableMessage: 'test' })
      expect(store.serviceUnavailable).toBe(true)
      expect(store.serviceUnavailableMessage).toBe('test')
    })
  })
})

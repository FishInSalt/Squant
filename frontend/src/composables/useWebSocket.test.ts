import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createTestingPinia } from '@pinia/testing'
import { useWebSocket, useTickerSubscription, useCandleSubscription } from './useWebSocket'
import { useWebSocketStore } from '@/stores/websocket'

// Helper to mount a composable with testing pinia
function withSetup<T>(composableFn: () => T): { result: T; wrapper: ReturnType<typeof mount> } {
  let result!: T
  const pinia = createTestingPinia({ createSpy: vi.fn })
  const Comp = defineComponent({
    setup() {
      result = composableFn()
      return () => null
    },
  })
  const wrapper = mount(Comp, { global: { plugins: [pinia] } })
  return { result, wrapper }
}

describe('useWebSocket', () => {
  it('calls wsStore.connect on mount', () => {
    const { result } = withSetup(() => useWebSocket())
    // After mount, store.connect should have been called
    const store = useWebSocketStore()
    expect(store.connect).toHaveBeenCalledOnce()
  })

  it('returns connected ref from store', () => {
    const { result } = withSetup(() => useWebSocket())
    expect(result.connected).toBeDefined()
  })

  it('returns subscribe and unsubscribe functions', () => {
    const { result } = withSetup(() => useWebSocket())
    expect(typeof result.subscribe).toBe('function')
    expect(typeof result.unsubscribe).toBe('function')
  })
})

describe('useTickerSubscription', () => {
  it('calls connect and subscribeToTickers on mount', () => {
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToTickers as ReturnType<typeof vi.fn>).mockReturnValue(vi.fn())

    const Comp = defineComponent({
      setup() {
        useTickerSubscription(['BTC/USDT', 'ETH/USDT'])
        return () => null
      },
    })
    mount(Comp, { global: { plugins: [pinia] } })

    expect(store.connect).toHaveBeenCalledOnce()
    expect(store.subscribeToTickers).toHaveBeenCalledWith(['BTC/USDT', 'ETH/USDT'])
  })

  it('accepts a single symbol string', () => {
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToTickers as ReturnType<typeof vi.fn>).mockReturnValue(vi.fn())

    const Comp = defineComponent({
      setup() {
        useTickerSubscription('BTC/USDT')
        return () => null
      },
    })
    mount(Comp, { global: { plugins: [pinia] } })

    expect(store.subscribeToTickers).toHaveBeenCalledWith(['BTC/USDT'])
  })

  it('calls unsubscribe on unmount', () => {
    const unsubFn = vi.fn()
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToTickers as ReturnType<typeof vi.fn>).mockReturnValue(unsubFn)

    const Comp = defineComponent({
      setup() {
        useTickerSubscription('BTC/USDT')
        return () => null
      },
    })
    const wrapper = mount(Comp, { global: { plugins: [pinia] } })
    wrapper.unmount()

    expect(unsubFn).toHaveBeenCalledOnce()
  })

  it('does not connect when autoConnect is false', () => {
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToTickers as ReturnType<typeof vi.fn>).mockReturnValue(vi.fn())

    const Comp = defineComponent({
      setup() {
        useTickerSubscription('BTC/USDT', false)
        return () => null
      },
    })
    mount(Comp, { global: { plugins: [pinia] } })

    expect(store.connect).not.toHaveBeenCalled()
  })
})

describe('useCandleSubscription', () => {
  it('calls connect and subscribeToCandles on mount', () => {
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToCandles as ReturnType<typeof vi.fn>).mockReturnValue(vi.fn())

    const Comp = defineComponent({
      setup() {
        useCandleSubscription('BTC/USDT', '1h')
        return () => null
      },
    })
    mount(Comp, { global: { plugins: [pinia] } })

    expect(store.connect).toHaveBeenCalledOnce()
    expect(store.subscribeToCandles).toHaveBeenCalledWith('BTC/USDT', '1h')
  })

  it('calls unsubscribe on unmount', () => {
    const unsubFn = vi.fn()
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToCandles as ReturnType<typeof vi.fn>).mockReturnValue(unsubFn)

    const Comp = defineComponent({
      setup() {
        useCandleSubscription('BTC/USDT', '1h')
        return () => null
      },
    })
    const wrapper = mount(Comp, { global: { plugins: [pinia] } })
    wrapper.unmount()

    expect(unsubFn).toHaveBeenCalledOnce()
  })

  it('does not connect when autoConnect is false', () => {
    const pinia = createTestingPinia({ createSpy: vi.fn })
    const store = useWebSocketStore()
    ;(store.subscribeToCandles as ReturnType<typeof vi.fn>).mockReturnValue(vi.fn())

    const Comp = defineComponent({
      setup() {
        useCandleSubscription('BTC/USDT', '1h', false)
        return () => null
      },
    })
    mount(Comp, { global: { plugins: [pinia] } })

    expect(store.connect).not.toHaveBeenCalled()
  })
})

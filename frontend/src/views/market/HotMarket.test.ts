import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import HotMarket from './HotMarket.vue'
import { useMarketStore } from '@/stores/market'
import { useWebSocketStore } from '@/stores/websocket'

describe('HotMarket', () => {
  it('renders page title', async () => {
    const wrapper = mountView(HotMarket)
    await flushPromises()
    expect(wrapper.text()).toContain('热门行情')
  })

  it('calls store to load data on mount', async () => {
    mountView(HotMarket)
    await flushPromises()
    const marketStore = useMarketStore()
    expect(marketStore.loadCurrentExchange).toHaveBeenCalled()
    expect(marketStore.loadAllTickers).toHaveBeenCalled()
  })

  it('connects websocket on mount', async () => {
    mountView(HotMarket)
    await flushPromises()
    const wsStore = useWebSocketStore()
    expect(wsStore.connect).toHaveBeenCalled()
  })

  it('shows table column headers', async () => {
    const wrapper = mountView(HotMarket)
    await flushPromises()
    expect(wrapper.text()).toContain('交易对')
    expect(wrapper.text()).toContain('最新价')
    expect(wrapper.text()).toContain('24h涨跌')
    expect(wrapper.text()).toContain('24h成交量')
  })

  it('shows search input', async () => {
    const wrapper = mountView(HotMarket)
    await flushPromises()
    expect(wrapper.find('input[placeholder="搜索交易对..."]').exists()).toBe(true)
  })

  it('shows WS connection status tag', async () => {
    // Use `connected` (the actual ref) instead of `isConnected` (computed)
    const wrapper = mountView(HotMarket, {
      initialState: {
        websocket: { connected: true, serviceUnavailable: false, exchangeSwitching: false },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('实时')
  })

  it('shows offline status when WS disconnected', async () => {
    const wrapper = mountView(HotMarket)
    await flushPromises()
    expect(wrapper.text()).toContain('离线')
  })

  it('shows operation column header', async () => {
    const wrapper = mountView(HotMarket)
    await flushPromises()
    expect(wrapper.text()).toContain('操作')
  })
})

import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import Watchlist from './Watchlist.vue'
import { useWebSocketStore } from '@/stores/websocket'

const mockWatchlist = [
  { id: 'wl-1', exchange: 'okx', symbol: 'BTC/USDT', sort_order: 0, created_at: '2024-01-01T00:00:00Z' },
  { id: 'wl-2', exchange: 'okx', symbol: 'ETH/USDT', sort_order: 1, created_at: '2024-01-01T00:00:00Z' },
]

describe('Watchlist', () => {
  it('renders page title', async () => {
    const wrapper = mountView(Watchlist)
    await flushPromises()
    expect(wrapper.text()).toContain('自选行情')
  })

  it('shows empty state when no watchlist items', async () => {
    const wrapper = mountView(Watchlist)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无自选交易对')
    expect(wrapper.text()).toContain('去添加')
  })

  it('shows table when watchlist has items', async () => {
    const wrapper = mountView(Watchlist, {
      initialState: {
        market: { watchlist: mockWatchlist },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('交易对')
    expect(wrapper.text()).toContain('最新价')
    expect(wrapper.text()).toContain('24h涨跌')
  })

  it('shows operation column with action links', async () => {
    const wrapper = mountView(Watchlist, {
      initialState: {
        market: { watchlist: mockWatchlist },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('操作')
  })

  it('connects websocket on mount with watchlist items', async () => {
    mountView(Watchlist, {
      initialState: {
        market: { watchlist: mockWatchlist },
      },
    })
    await flushPromises()
    const wsStore = useWebSocketStore()
    expect(wsStore.connect).toHaveBeenCalled()
  })
})

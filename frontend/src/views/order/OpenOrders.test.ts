import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import OpenOrders from './OpenOrders.vue'
import * as orderApi from '@/api/order'
import { wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/order', () => ({
  getOpenOrders: vi.fn(),
  cancelOrder: vi.fn(),
  cancelOrders: vi.fn(),
  cancelAllOrders: vi.fn(),
}))

const mockOrders = [
  {
    id: 'order-1',
    exchange: 'okx',
    symbol: 'BTC/USDT',
    side: 'buy' as const,
    type: 'limit' as const,
    price: 50000,
    amount: 0.1,
    filled: 0,
    remaining_amount: 0.1,
    status: 'open' as const,
    strategy_name: 'TestStrategy',
    created_at: '2024-06-15T10:00:00Z',
    updated_at: '2024-06-15T10:00:00Z',
  },
  {
    id: 'order-2',
    exchange: 'okx',
    symbol: 'ETH/USDT',
    side: 'sell' as const,
    type: 'limit' as const,
    price: 3000,
    amount: 1.0,
    filled: 0.5,
    remaining_amount: 0.5,
    status: 'open' as const,
    created_at: '2024-06-15T11:00:00Z',
    updated_at: '2024-06-15T11:00:00Z',
  },
]

beforeEach(() => {
  vi.mocked(orderApi.getOpenOrders).mockResolvedValue(wrapApiResponse(mockOrders))
})

describe('OpenOrders', () => {
  it('renders page title', async () => {
    const wrapper = mountView(OpenOrders)
    await flushPromises()
    expect(wrapper.text()).toContain('当前挂单')
  })

  it('loads and displays orders on mount', async () => {
    const wrapper = mountView(OpenOrders)
    await flushPromises()
    expect(orderApi.getOpenOrders).toHaveBeenCalled()
    expect(wrapper.text()).toContain('BTC/USDT')
    expect(wrapper.text()).toContain('ETH/USDT')
  })

  it('shows cancel all button', async () => {
    const wrapper = mountView(OpenOrders)
    await flushPromises()
    expect(wrapper.text()).toContain('取消全部')
  })

  it('shows filter form', async () => {
    const wrapper = mountView(OpenOrders)
    await flushPromises()
    expect(wrapper.text()).toContain('交易所')
    expect(wrapper.text()).toContain('交易对')
    expect(wrapper.text()).toContain('方向')
    expect(wrapper.text()).toContain('查询')
  })

  it('shows strategy name or dash', async () => {
    const wrapper = mountView(OpenOrders)
    await flushPromises()
    expect(wrapper.text()).toContain('TestStrategy')
  })

  it('shows cancel button for each order', async () => {
    const wrapper = mountView(OpenOrders)
    await flushPromises()
    const cancelLinks = wrapper.findAll('.el-button').filter((b) => b.text() === '取消')
    // At least the per-row cancel buttons
    expect(cancelLinks.length).toBeGreaterThanOrEqual(2)
  })
})

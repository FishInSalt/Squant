import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import OrderHistory from './OrderHistory.vue'
import * as orderApi from '@/api/order'
import { wrapPaginatedResponse } from '@/__tests__/fixtures'

vi.mock('@/api/order', () => ({
  getOrderHistory: vi.fn(),
  exportOrders: vi.fn(),
}))

const mockOrders = [
  {
    id: 'order-1',
    account_id: 'acc-1',
    exchange: 'okx',
    symbol: 'BTC/USDT',
    side: 'buy' as const,
    type: 'limit' as const,
    price: 50000,
    avg_price: 49990,
    amount: 0.1,
    filled: 0.1,
    remaining_amount: 0,
    commission: 0.00005,
    status: 'filled' as const,
    strategy_name: 'TestStrategy',
    created_at: '2024-06-15T10:00:00Z',
    updated_at: '2024-06-15T10:01:00Z',
  },
  {
    id: 'order-2',
    account_id: 'acc-1',
    exchange: 'okx',
    symbol: 'ETH/USDT',
    side: 'sell' as const,
    type: 'market' as const,
    avg_price: 3000,
    amount: 1.0,
    filled: 1.0,
    remaining_amount: 0,
    commission: 0.001,
    status: 'filled' as const,
    created_at: '2024-06-15T11:00:00Z',
    updated_at: '2024-06-15T11:00:01Z',
  },
]

beforeEach(() => {
  vi.mocked(orderApi.getOrderHistory).mockResolvedValue(wrapPaginatedResponse(mockOrders, 2))
})

describe('OrderHistory', () => {
  it('renders page title', async () => {
    const wrapper = mountView(OrderHistory)
    await flushPromises()
    expect(wrapper.text()).toContain('历史订单')
  })

  it('loads and displays orders on mount', async () => {
    const wrapper = mountView(OrderHistory)
    await flushPromises()
    expect(orderApi.getOrderHistory).toHaveBeenCalled()
    expect(wrapper.text()).toContain('BTC/USDT')
    expect(wrapper.text()).toContain('ETH/USDT')
  })

  it('shows export button', async () => {
    const wrapper = mountView(OrderHistory)
    await flushPromises()
    expect(wrapper.text()).toContain('导出')
  })

  it('shows filter form with status filter', async () => {
    const wrapper = mountView(OrderHistory)
    await flushPromises()
    expect(wrapper.text()).toContain('交易所')
    expect(wrapper.text()).toContain('状态')
    expect(wrapper.text()).toContain('查询')
  })

  it('shows commission column', async () => {
    const wrapper = mountView(OrderHistory)
    await flushPromises()
    expect(wrapper.text()).toContain('手续费')
  })

  it('shows pagination', async () => {
    const wrapper = mountView(OrderHistory)
    await flushPromises()
    expect(wrapper.find('.el-pagination').exists()).toBe(true)
  })
})

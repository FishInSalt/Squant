import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import Backtest from './Backtest.vue'
import * as backtestApi from '@/api/backtest'
import * as marketApi from '@/api/market'
import { createMockBacktestRun, wrapApiResponse, wrapPaginatedResponse } from '@/__tests__/fixtures'

vi.mock('@/api/backtest', () => ({
  startBacktest: vi.fn(),
  getBacktests: vi.fn(),
}))

vi.mock('@/api/market', () => ({
  getSymbols: vi.fn(),
  getTickers: vi.fn(),
  getExchanges: vi.fn(),
}))

const mockHistory = [
  createMockBacktestRun({ id: 'bt-1', strategy_name: 'MA Cross', status: 'completed', symbol: 'BTC/USDT' }),
  createMockBacktestRun({ id: 'bt-2', strategy_name: 'RSI', status: 'running', progress: 50, symbol: 'ETH/USDT' }),
]

beforeEach(() => {
  vi.mocked(backtestApi.getBacktests).mockResolvedValue(wrapPaginatedResponse(mockHistory, 2))
  vi.mocked(marketApi.getSymbols).mockResolvedValue(wrapApiResponse(['BTC/USDT', 'ETH/USDT']))
})

describe('Backtest', () => {
  it('renders page title', async () => {
    const wrapper = mountView(Backtest)
    await flushPromises()
    expect(wrapper.text()).toContain('回测')
  })

  it('shows config panel', async () => {
    const wrapper = mountView(Backtest)
    await flushPromises()
    expect(wrapper.text()).toContain('回测配置')
  })

  it('shows history panel', async () => {
    const wrapper = mountView(Backtest)
    await flushPromises()
    expect(wrapper.text()).toContain('回测历史')
  })

  it('loads backtest history', async () => {
    const wrapper = mountView(Backtest)
    await flushPromises()
    expect(backtestApi.getBacktests).toHaveBeenCalled()
    expect(wrapper.text()).toContain('MA Cross')
    expect(wrapper.text()).toContain('RSI')
  })

  it('shows submit button', async () => {
    const wrapper = mountView(Backtest)
    await flushPromises()
    expect(wrapper.text()).toContain('开始回测')
  })

  it('shows form fields', async () => {
    const wrapper = mountView(Backtest)
    await flushPromises()
    expect(wrapper.text()).toContain('策略')
    expect(wrapper.text()).toContain('交易所')
    expect(wrapper.text()).toContain('交易对')
    expect(wrapper.text()).toContain('时间周期')
    expect(wrapper.text()).toContain('初始资金')
  })
})

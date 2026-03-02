import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import BacktestResult from './BacktestResult.vue'
import * as backtestApi from '@/api/backtest'
import { createMockBacktestRun, wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/backtest', () => ({
  getBacktestStatus: vi.fn(),
  getBacktestResult: vi.fn(),
  exportBacktestResult: vi.fn(),
}))

const completedBacktest = createMockBacktestRun({ status: 'completed', progress: 1 })
const runningBacktest = createMockBacktestRun({ status: 'running', progress: 50 })
const errorBacktest = createMockBacktestRun({ status: 'error', error_message: '策略执行出错' })

const mockResult = {
  run: completedBacktest,
  metrics: {
    total_return: 15.5,
    total_return_pct: 15.5,
    annualized_return: 45.2,
    max_drawdown: -8.3,
    max_drawdown_pct: -8.3,
    max_drawdown_duration_hours: 48,
    sharpe_ratio: 1.85,
    win_rate: 62.5,
    profit_factor: 2.1,
    total_trades: 120,
    total_fees: 24.5,
    sortino_ratio: 2.3,
    calmar_ratio: 5.45,
    volatility: 0.15,
    winning_trades: 75,
    losing_trades: 45,
    avg_trade_return: 0.13,
    avg_win: 0.85,
    avg_loss: -0.42,
    largest_win: 5.2,
    largest_loss: -2.1,
    max_consecutive_losses: 5,
    avg_trade_duration_hours: 12,
    total_duration_days: 150,
  },
  equity_curve: [],
  trades: [
    {
      symbol: 'BTC/USDT',
      entry_time: '2024-01-15T10:00:00Z',
      side: 'buy' as const,
      entry_price: 42000,
      exit_price: 43000,
      amount: 0.1,
      fees: 0.01,
      pnl: 100,
      pnl_pct: 2.38,
    },
  ],
  fills: [],
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('BacktestResult', () => {
  it('renders completed backtest with metrics', async () => {
    vi.mocked(backtestApi.getBacktestStatus).mockResolvedValue(wrapApiResponse(completedBacktest))
    vi.mocked(backtestApi.getBacktestResult).mockResolvedValue(wrapApiResponse(mockResult))
    const wrapper = mountView(BacktestResult, { props: { id: 'bt-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('总收益')
    expect(wrapper.text()).toContain('夏普比率')
    expect(wrapper.text()).toContain('胜率')
    expect(wrapper.text()).toContain('交易记录')
  })

  it('shows running status with progress', async () => {
    vi.mocked(backtestApi.getBacktestStatus).mockResolvedValue(wrapApiResponse(runningBacktest))
    const wrapper = mountView(BacktestResult, { props: { id: 'bt-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('正在回测中')
  })

  it('shows error status with message', async () => {
    vi.mocked(backtestApi.getBacktestStatus).mockResolvedValue(wrapApiResponse(errorBacktest))
    const wrapper = mountView(BacktestResult, { props: { id: 'bt-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('策略执行出错')
    expect(wrapper.text()).toContain('重新回测')
  })

  it('shows export button for completed backtest', async () => {
    vi.mocked(backtestApi.getBacktestStatus).mockResolvedValue(wrapApiResponse(completedBacktest))
    vi.mocked(backtestApi.getBacktestResult).mockResolvedValue(wrapApiResponse(mockResult))
    const wrapper = mountView(BacktestResult, { props: { id: 'bt-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('导出')
  })

  it('shows detailed metrics section', async () => {
    vi.mocked(backtestApi.getBacktestStatus).mockResolvedValue(wrapApiResponse(completedBacktest))
    vi.mocked(backtestApi.getBacktestResult).mockResolvedValue(wrapApiResponse(mockResult))
    const wrapper = mountView(BacktestResult, { props: { id: 'bt-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('详细指标')
    expect(wrapper.text()).toContain('索提诺比率')
    expect(wrapper.text()).toContain('盈利交易数')
    expect(wrapper.text()).toContain('最大连亏')
  })

  it('shows back button', async () => {
    vi.mocked(backtestApi.getBacktestStatus).mockResolvedValue(wrapApiResponse(completedBacktest))
    vi.mocked(backtestApi.getBacktestResult).mockResolvedValue(wrapApiResponse(mockResult))
    const wrapper = mountView(BacktestResult, { props: { id: 'bt-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('返回')
  })
})

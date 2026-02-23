import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import SessionDetail from './SessionDetail.vue'
import * as paperApi from '@/api/paper'
import * as liveApi from '@/api/live'
import { createMockPaperSession, createMockLiveSession, wrapApiResponse } from '@/__tests__/fixtures'
import type { PaperTradingStatus, LiveTradingStatus } from '@/types'

vi.mock('@/api/paper', () => ({
  getPaperSession: vi.fn(),
  getPaperSessionStatus: vi.fn(),
  stopPaperTrading: vi.fn(),
  getPaperEquityCurve: vi.fn(),
}))

vi.mock('@/api/live', () => ({
  getLiveSession: vi.fn(),
  getLiveSessionStatus: vi.fn(),
  stopLiveTrading: vi.fn(),
  emergencyClosePositions: vi.fn(),
  getLiveEquityCurve: vi.fn(),
}))

vi.mock('@/composables/useTradingConfirm', () => ({
  confirmStopLive: vi.fn().mockResolvedValue({ confirmed: true, cancelOrders: false }),
  confirmEmergencyClose: vi.fn().mockResolvedValue(true),
  toPositionRows: vi.fn().mockReturnValue([]),
}))

const mockPaperSession = createMockPaperSession({
  id: 'p-1',
  strategy_name: 'MA Cross',
  exchange: 'okx',
  symbol: 'BTC/USDT',
  timeframe: '1h',
  initial_capital: 10000,
  commission_rate: 0.001,
  slippage: 0.0005,
  status: 'running',
  started_at: '2024-01-01T00:01:00Z',
  params: { fast_period: 5, slow_period: 20 },
})

const mockPaperStatus: PaperTradingStatus = {
  run_id: 'p-1',
  symbol: 'BTC/USDT',
  timeframe: '1h',
  is_running: true,
  bar_count: 100,
  cash: 9500,
  equity: 10200,
  initial_capital: 10000,
  total_fees: 15,
  unrealized_pnl: 200,
  realized_pnl: 500,
  positions: {
    'BTC/USDT': { amount: 0.1, avg_entry_price: 50000, current_price: 52000, unrealized_pnl: 200 },
  },
  pending_orders: [],
  completed_orders_count: 5,
  trades_count: 3,
  trades: [
    {
      symbol: 'BTC/USDT',
      side: 'buy',
      entry_time: '2024-01-15T10:00:00Z',
      entry_price: 50000,
      exit_time: '2024-01-16T10:00:00Z',
      exit_price: 51000,
      amount: 0.1,
      pnl: 100,
      pnl_pct: 2,
      fees: 5,
    },
  ],
  logs: ['[2024-01-15 10:00:00] Strategy started', '[2024-01-15 10:05:00] Buy signal detected'],
}

const mockLiveStatus: LiveTradingStatus = {
  run_id: 'l-1',
  symbol: 'BTC/USDT',
  timeframe: '1h',
  is_running: true,
  bar_count: 50,
  cash: 9000,
  equity: 10100,
  initial_capital: 10000,
  total_fees: 10,
  unrealized_pnl: 100,
  realized_pnl: 0,
  positions: {
    'BTC/USDT': { amount: 0.05, avg_entry_price: 50000, current_price: 52000, unrealized_pnl: 100 },
  },
  pending_orders: [],
  live_orders: [],
  completed_orders_count: 2,
  trades_count: 1,
  risk_state: {
    daily_pnl: 100,
    daily_trade_count: 3,
    consecutive_losses: 0,
    circuit_breaker_active: false,
    max_position_size: 1,
    max_order_size: 0.5,
    daily_trade_limit: 50,
    daily_loss_limit: 1000,
  },
}

describe('SessionDetail', () => {
  describe('Paper session', () => {
    beforeEach(() => {
      vi.mocked(paperApi.getPaperSession).mockResolvedValue(wrapApiResponse(mockPaperSession))
      vi.mocked(paperApi.getPaperSessionStatus).mockResolvedValue(wrapApiResponse(mockPaperStatus))
      vi.mocked(paperApi.getPaperEquityCurve).mockResolvedValue(
        wrapApiResponse([
          { time: '2024-01-15T10:00:00Z', equity: 10000, cash: 10000 },
          { time: '2024-01-15T11:00:00Z', equity: 10200, cash: 9500 },
        ] as any)
      )
    })

    function mountPaper() {
      return mountView(SessionDetail, {
        props: { type: 'paper', id: 'p-1' },
      })
    }

    it('renders strategy name and paper tag', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('MA Cross')
      expect(wrapper.text()).toContain('模拟')
    })

    it('shows config section with session details', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('会话配置')
      // Config is collapsed by default, so summary is visible
      expect(wrapper.text()).toContain('OKX')
      expect(wrapper.text()).toContain('BTC/USDT')
      expect(wrapper.text()).toContain('1h')
    })

    it('config is collapsed by default, expandable on click', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      // Collapsed: config-body has v-show=false → display: none
      const body = wrapper.find('.config-body')
      expect(body.exists()).toBe(true)
      expect((body.element as HTMLElement).style.display).toBe('none')
      // Click to expand
      await wrapper.find('.config-header').trigger('click')
      expect((body.element as HTMLElement).style.display).not.toBe('none')
      expect(wrapper.text()).toContain('fast_period')
      expect(wrapper.text()).toContain('slow_period')
    })

    it('shows total return percentage', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      // (10200 - 10000) / 10000 * 100 = 2%
      expect(wrapper.text()).toContain('总收益率')
      expect(wrapper.text()).toContain('2.00%')
    })

    it('shows core metrics', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('当前权益')
      expect(wrapper.text()).toContain('可用资金')
      expect(wrapper.text()).toContain('已实现盈亏')
      expect(wrapper.text()).toContain('未实现盈亏')
      expect(wrapper.text()).toContain('总手续费')
    })

    it('shows win rate', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      // 1 closed trade with positive pnl → 100%
      expect(wrapper.text()).toContain('胜率')
      expect(wrapper.text()).toContain('100.0%')
    })

    it('shows running duration', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('已运行')
    })

    it('shows K-line chart stub', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.find('.trading-kline-chart-stub').exists()).toBe(true)
    })

    it('shows equity curve (always rendered)', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('收益曲线')
      expect(wrapper.find('.equity-curve-stub').exists()).toBe(true)
    })

    it('shows equity curve even without data (fallback)', async () => {
      vi.mocked(paperApi.getPaperEquityCurve).mockResolvedValue(wrapApiResponse([] as any))
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.find('.equity-curve-stub').exists()).toBe(true)
    })

    it('renders tabs for positions, orders, trades, logs', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      const tabLabels = wrapper.findAll('.el-tabs__item')
      const texts = tabLabels.map(el => el.text())
      expect(texts.some(t => t.includes('持仓'))).toBe(true)
      expect(texts.some(t => t.includes('挂单'))).toBe(true)
      expect(texts.some(t => t.includes('交易记录'))).toBe(true)
      expect(texts.some(t => t.includes('日志'))).toBe(true)
    })

    it('shows positions table in default tab', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      // Positions tab is default
      expect(wrapper.text()).toContain('BTC/USDT')
    })

    it('shows waiting hint when bar_count is 0', async () => {
      vi.mocked(paperApi.getPaperSessionStatus).mockResolvedValue(
        wrapApiResponse({ ...mockPaperStatus, bar_count: 0 })
      )
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('等待第一根K线数据')
    })

    it('shows stop button for running session', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.find('.header-right').exists()).toBe(true)
    })

    it('hides stop button for stopped session', async () => {
      vi.mocked(paperApi.getPaperSession).mockResolvedValue(
        wrapApiResponse(createMockPaperSession({ id: 'p-1', status: 'stopped' }))
      )
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.find('.header-right').exists()).toBe(false)
    })

    it('shows error bar', async () => {
      vi.mocked(paperApi.getPaperSession).mockResolvedValue(
        wrapApiResponse(
          createMockPaperSession({
            id: 'p-1',
            status: 'error',
            error_message: 'Strategy execution failed',
          })
        )
      )
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('Strategy execution failed')
    })

    it('shows empty positions message', async () => {
      vi.mocked(paperApi.getPaperSessionStatus).mockResolvedValue(
        wrapApiResponse({ ...mockPaperStatus, positions: {} })
      )
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('暂无持仓')
    })

    it('shows position market value and pnl%', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      // market_value = 0.1 * 52000 = 5200
      expect(wrapper.text()).toContain('市值')
      expect(wrapper.text()).toContain('5,200')
      // pnl% = 200 / (50000 * 0.1) * 100 = 4%
      expect(wrapper.text()).toContain('盈亏%')
      expect(wrapper.text()).toMatch(/4\.0+%/)
    })

    it('shows symbol column in trades table', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      // Switch to trades tab
      const tradesTab = wrapper.findAll('.el-tabs__item').find(el => el.text().includes('交易记录'))
      await tradesTab!.trigger('click')
      await flushPromises()
      // Trade record should show BTC/USDT symbol
      expect(wrapper.text()).toContain('BTC/USDT')
    })

    it('shows max drawdown from equity curve', async () => {
      vi.mocked(paperApi.getPaperEquityCurve).mockResolvedValue(
        wrapApiResponse([
          { time: '2024-01-15T10:00:00Z', equity: 10000, cash: 10000 },
          { time: '2024-01-15T11:00:00Z', equity: 10500, cash: 9500 },
          { time: '2024-01-15T12:00:00Z', equity: 10200, cash: 9200 },
        ] as any)
      )
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('最大回撤')
      // peak=10500, trough=10200, dd = (10500-10200)/10500*100 = 2.857%
      // displayed as -2.86%
      expect(wrapper.text()).toContain('-2.86%')
    })
  })

  describe('Live session', () => {
    beforeEach(() => {
      vi.mocked(liveApi.getLiveSession).mockResolvedValue(
        wrapApiResponse(
          createMockLiveSession({
            id: 'l-1',
            strategy_name: 'Grid Bot',
            status: 'running',
          })
        )
      )
      vi.mocked(liveApi.getLiveSessionStatus).mockResolvedValue(wrapApiResponse(mockLiveStatus))
      vi.mocked(liveApi.getLiveEquityCurve).mockResolvedValue(wrapApiResponse([]))
    })

    function mountLive() {
      return mountView(SessionDetail, {
        props: { type: 'live', id: 'l-1' },
      })
    }

    it('renders strategy name and live tag', async () => {
      const wrapper = mountLive()
      await flushPromises()
      expect(wrapper.text()).toContain('Grid Bot')
      expect(wrapper.text()).toContain('实盘')
    })

    it('shows emergency close button', async () => {
      const wrapper = mountLive()
      await flushPromises()
      expect(wrapper.text()).toContain('紧急平仓')
    })

    it('shows risk state in risk tab', async () => {
      const wrapper = mountLive()
      await flushPromises()
      // Risk tab exists
      const tabLabels = wrapper.findAll('.el-tabs__item')
      expect(tabLabels.some(el => el.text().includes('风控'))).toBe(true)
    })

    it('does not show trades or logs tabs for live', async () => {
      const wrapper = mountLive()
      await flushPromises()
      const tabLabels = wrapper.findAll('.el-tabs__item')
      expect(tabLabels.some(el => el.text().includes('交易记录'))).toBe(false)
      expect(tabLabels.some(el => el.text().includes('日志'))).toBe(false)
    })

    it('win rate is hidden for live session', async () => {
      const wrapper = mountLive()
      await flushPromises()
      // Win rate should show '-' since it's live
      expect(wrapper.text()).toContain('胜率')
      // The value should be '-' (null → '-')
    })
  })
})

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

    it('shows config panel with session parameters', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('会话配置')
      expect(wrapper.text()).toContain('OKX')
      expect(wrapper.text()).toContain('BTC/USDT')
      expect(wrapper.text()).toContain('1h')
    })

    it('shows strategy params in config panel', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('fast_period')
      expect(wrapper.text()).toContain('5')
      expect(wrapper.text()).toContain('slow_period')
      expect(wrapper.text()).toContain('20')
    })

    it('shows metrics grid', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('当前权益')
      expect(wrapper.text()).toContain('可用资金')
      expect(wrapper.text()).toContain('已实现盈亏')
      expect(wrapper.text()).toContain('未实现盈亏')
    })

    it('shows positions table', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('当前持仓')
      expect(wrapper.text()).toContain('共 1 项')
    })

    it('shows trades table', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('交易记录')
      expect(wrapper.text()).toContain('共 1 笔')
    })

    it('shows logs panel with entries', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('运行日志')
      expect(wrapper.text()).toContain('Strategy started')
      expect(wrapper.text()).toContain('Buy signal detected')
    })

    it('shows equity curve section', async () => {
      const wrapper = mountPaper()
      await flushPromises()
      expect(wrapper.text()).toContain('收益曲线')
      expect(wrapper.find('.equity-curve-stub').exists()).toBe(true)
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

    it('shows error message', async () => {
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

    it('shows risk state section', async () => {
      const wrapper = mountLive()
      await flushPromises()
      expect(wrapper.text()).toContain('风控状态')
      expect(wrapper.text()).toContain('日盈亏')
      expect(wrapper.text()).toContain('连续亏损')
    })
  })
})

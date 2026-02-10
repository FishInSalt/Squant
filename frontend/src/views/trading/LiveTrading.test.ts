import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import LiveTrading from './LiveTrading.vue'
import * as liveApi from '@/api/live'
import * as marketApi from '@/api/market'
import * as accountApi from '@/api/account'
import * as riskApi from '@/api/risk'
import { createMockLiveSession, wrapApiResponse, wrapPaginatedResponse } from '@/__tests__/fixtures'

vi.mock('@/api/live', () => ({
  startLiveTrading: vi.fn(),
  getLiveSessions: vi.fn(),
  getLiveSessionStatus: vi.fn(),
  stopLiveTrading: vi.fn(),
  emergencyClosePositions: vi.fn(),
}))

vi.mock('@/api/market', () => ({
  getSymbols: vi.fn(),
  getTickers: vi.fn(),
  getExchanges: vi.fn(),
}))

vi.mock('@/api/account', () => ({
  getAccounts: vi.fn(),
}))

vi.mock('@/api/risk', () => ({
  getRiskRules: vi.fn(),
}))

const mockSessions = [
  createMockLiveSession({ id: 'l-1', strategy_name: 'Momentum', status: 'running' }),
  createMockLiveSession({ id: 'l-2', strategy_name: 'Mean Revert', status: 'stopped' }),
]

const mockAccounts = [
  { id: 'acc-1', name: 'Main OKX', exchange: 'okx', is_active: true, testnet: false, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
  { id: 'acc-2', name: 'Testnet', exchange: 'okx', is_active: true, testnet: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
]

beforeEach(() => {
  vi.mocked(liveApi.getLiveSessions).mockResolvedValue(wrapPaginatedResponse(mockSessions, 2))
  vi.mocked(marketApi.getSymbols).mockResolvedValue(wrapApiResponse(['BTC/USDT']))
  vi.mocked(accountApi.getAccounts).mockResolvedValue(wrapApiResponse(mockAccounts))
  vi.mocked(riskApi.getRiskRules).mockResolvedValue(wrapPaginatedResponse([], 0))
})

describe('LiveTrading', () => {
  it('renders page title', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('实盘交易')
  })

  it('shows risk warning', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('风险提示')
    expect(wrapper.text()).toContain('实盘交易涉及真实资金')
  })

  it('shows risk control settings', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('风控设置')
    expect(wrapper.text()).toContain('最大持仓比例')
    expect(wrapper.text()).toContain('日最大亏损比例')
  })

  it('loads and displays sessions', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(liveApi.getLiveSessions).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Momentum')
    expect(wrapper.text()).toContain('Mean Revert')
  })

  it('shows stop and emergency close for running sessions', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('停止')
    expect(wrapper.text()).toContain('紧急平仓')
  })

  it('shows sessions panel', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('实盘交易会话')
  })

  it('shows empty state when no sessions', async () => {
    vi.mocked(liveApi.getLiveSessions).mockResolvedValue(wrapPaginatedResponse([]))
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无实盘交易会话')
  })

  it('shows submit button', async () => {
    const wrapper = mountView(LiveTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('启动实盘交易')
  })
})

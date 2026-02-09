import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import PaperTrading from './PaperTrading.vue'
import * as paperApi from '@/api/paper'
import * as marketApi from '@/api/market'
import { createMockPaperSession, wrapApiResponse, wrapPaginatedResponse } from '@/__tests__/fixtures'

vi.mock('@/api/paper', () => ({
  startPaperTrading: vi.fn(),
  getPaperSessions: vi.fn(),
  stopPaperTrading: vi.fn(),
}))

vi.mock('@/api/market', () => ({
  getSymbols: vi.fn(),
  getTickers: vi.fn(),
  getExchanges: vi.fn(),
}))

const mockSessions = [
  createMockPaperSession({ id: 'p-1', strategy_name: 'MA Cross', status: 'running' }),
  createMockPaperSession({ id: 'p-2', strategy_name: 'RSI', status: 'stopped' }),
]

beforeEach(() => {
  vi.mocked(paperApi.getPaperSessions).mockResolvedValue(wrapPaginatedResponse(mockSessions, 2))
  vi.mocked(marketApi.getSymbols).mockResolvedValue(wrapApiResponse(['BTC/USDT', 'ETH/USDT']))
})

describe('PaperTrading', () => {
  it('renders page title', async () => {
    const wrapper = mountView(PaperTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('模拟交易')
  })

  it('shows config panel', async () => {
    const wrapper = mountView(PaperTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('启动模拟交易')
  })

  it('shows sessions panel', async () => {
    const wrapper = mountView(PaperTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('模拟交易会话')
  })

  it('loads and displays sessions', async () => {
    const wrapper = mountView(PaperTrading)
    await flushPromises()
    expect(paperApi.getPaperSessions).toHaveBeenCalled()
    expect(wrapper.text()).toContain('MA Cross')
    expect(wrapper.text()).toContain('RSI')
  })

  it('shows stop button for running sessions', async () => {
    const wrapper = mountView(PaperTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('停止')
  })

  it('shows empty state when no sessions', async () => {
    vi.mocked(paperApi.getPaperSessions).mockResolvedValue(wrapPaginatedResponse([]))
    const wrapper = mountView(PaperTrading)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无模拟交易会话')
  })
})

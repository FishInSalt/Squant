import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import Monitor from './Monitor.vue'
import * as paperApi from '@/api/paper'
import { createMockPaperSession, createMockLiveSession, wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/paper', () => ({
  stopPaperTrading: vi.fn(),
  stopAllPaperTrading: vi.fn(),
}))

vi.mock('@/api/live', () => ({
  stopLiveTrading: vi.fn(),
  emergencyClosePositions: vi.fn(),
  getLiveSessionStatus: vi.fn(),
}))

vi.mock('@/composables/useTradingConfirm', () => ({
  confirmStopLive: vi.fn().mockResolvedValue({ confirmed: true, cancelOrders: false }),
  confirmEmergencyClose: vi.fn().mockResolvedValue(true),
  toPositionRows: vi.fn().mockReturnValue([]),
}))

const mockPaperSessions = [
  createMockPaperSession({ id: 'p-1', strategy_name: 'MA Cross', status: 'running' }),
  createMockPaperSession({ id: 'p-2', strategy_name: 'RSI Strategy', status: 'running' }),
]

describe('Monitor', () => {
  it('renders page title', async () => {
    const wrapper = mountView(Monitor)
    await flushPromises()
    expect(wrapper.text()).toContain('运行监控')
  })

  it('shows session cards from store', async () => {
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: mockPaperSessions,
          runningLiveSessions: [],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('MA Cross')
    expect(wrapper.text()).toContain('RSI Strategy')
  })

  it('shows empty state when no sessions', async () => {
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: [],
          runningLiveSessions: [],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无运行中的交易会话')
  })

  it('shows stop-all button when multiple running paper sessions', async () => {
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: mockPaperSessions,
          runningLiveSessions: [],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('停止全部')
  })

  it('does not show stop-all with single running paper session', async () => {
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: [mockPaperSessions[0]],
          runningLiveSessions: [],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).not.toContain('停止全部')
  })

  it('shows paper session type tag', async () => {
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: [mockPaperSessions[0]],
          runningLiveSessions: [],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('模拟')
  })

  it('shows live session type tag', async () => {
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: [],
          runningLiveSessions: [createMockLiveSession({ id: 'l-1', status: 'running' })],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('实盘')
  })

  it('calls stopAllPaperTrading on stop-all click', async () => {
    vi.mocked(paperApi.stopAllPaperTrading).mockResolvedValue(wrapApiResponse({ stopped_count: 2 }))
    const wrapper = mountView(Monitor, {
      initialState: {
        trading: {
          runningPaperSessions: mockPaperSessions,
          runningLiveSessions: [],
          runningBacktests: [],
        },
      },
    })
    await flushPromises()

    const stopAllBtn = wrapper.find('.tab-actions button')
    await stopAllBtn.trigger('click')
    await flushPromises()

    expect(paperApi.stopAllPaperTrading).toHaveBeenCalled()
  })
})

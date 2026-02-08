import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import CircuitBreaker from './CircuitBreaker.vue'
import * as riskApi from '@/api/risk'
import { wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/risk', () => ({
  getCircuitBreakerStatus: vi.fn(),
  executeCircuitBreakerAction: vi.fn(),
  triggerCircuitBreaker: vi.fn(),
  resetCircuitBreaker: vi.fn(),
  closeAllPositions: vi.fn(),
}))

const normalStatus = {
  is_active: false,
  active_live_sessions: 2,
  active_paper_sessions: 1,
}

const haltedStatus = {
  is_active: true,
  trigger_reason: '日亏损超限',
  triggered_at: '2024-06-15T10:00:00Z',
  trigger_type: 'max_daily_loss',
  cooldown_until: '2024-06-15T11:00:00Z',
  active_live_sessions: 0,
  active_paper_sessions: 0,
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('CircuitBreaker', () => {
  it('renders page title', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(normalStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    expect(wrapper.text()).toContain('熔断控制')
  })

  it('shows normal status when not halted', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(normalStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    expect(wrapper.text()).toContain('系统运行正常')
    expect(wrapper.text()).toContain('一键熔断')
  })

  it('shows halted status when active', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(haltedStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    expect(wrapper.text()).toContain('系统已熔断')
    expect(wrapper.text()).toContain('日亏损超限')
    expect(wrapper.text()).toContain('恢复交易')
  })

  it('shows running session count', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(normalStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    // 2 live + 1 paper = 3
    expect(wrapper.find('.stat .value').text()).toBe('3')
    expect(wrapper.text()).toContain('运行中策略')
  })

  it('shows halt reason and time when halted', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(haltedStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    expect(wrapper.text()).toContain('日亏损超限')
    expect(wrapper.text()).toContain('max_daily_loss')
  })

  it('applies halted class when active', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(haltedStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    expect(wrapper.find('.status-panel.halted').exists()).toBe(true)
  })

  it('does not apply halted class when normal', async () => {
    vi.mocked(riskApi.getCircuitBreakerStatus).mockResolvedValue(wrapApiResponse(normalStatus))
    const wrapper = mountView(CircuitBreaker)
    await flushPromises()
    expect(wrapper.find('.status-panel.halted').exists()).toBe(false)
  })
})

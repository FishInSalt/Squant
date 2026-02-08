import { flushPromises, mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { createRouter, createMemoryHistory } from 'vue-router'
import StrategyDetail from './StrategyDetail.vue'
import { useStrategyStore } from '@/stores/strategy'
import * as backtestApi from '@/api/backtest'
import { createMockStrategy, createMockBacktestRun, wrapPaginatedResponse } from '@/__tests__/fixtures'
import type { ComponentMountingOptions } from '@vue/test-utils'

vi.mock('@/api/backtest', () => ({
  getBacktests: vi.fn(),
}))

const mockStrategy = createMockStrategy({
  id: 's-1',
  name: 'MA Cross',
  description: '均线交叉策略',
  code: 'class MACross:\n  def on_bar(self, bar): pass',
  version: '2.0.0',
  params_schema: {
    type: 'object',
    properties: {
      fast_period: { title: '快线周期', type: 'integer', default: 5 },
      slow_period: { title: '慢线周期', type: 'integer', default: 20 },
    },
  },
})

const mockBacktests = [
  createMockBacktestRun({ id: 'bt-1', status: 'completed', created_at: '2024-06-01T00:00:00Z' }),
]

/**
 * Mount StrategyDetail with store action mocked BEFORE component setup runs.
 * This is necessary because onMounted calls loadStrategy immediately.
 */
function mountDetail(strategy: ReturnType<typeof createMockStrategy> | null = mockStrategy) {
  const pinia = createTestingPinia({ createSpy: vi.fn })
  const store = useStrategyStore()
  ;(store.loadStrategy as ReturnType<typeof vi.fn>).mockResolvedValue(strategy)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', name: 'Catchall', component: { template: '<div />' } }],
  })

  return mount(StrategyDetail, {
    global: {
      plugins: [pinia, router],
      stubs: {
        EquityCurve: { template: '<div />' },
        KLineChart: { template: '<div />' },
        PieChart: { template: '<div />' },
        ElDatePicker: { template: '<div />' },
      },
    },
    props: { id: strategy?.id || 's-1' },
  } as ComponentMountingOptions<any>)
}

describe('StrategyDetail', () => {
  beforeEach(() => {
    vi.mocked(backtestApi.getBacktests).mockResolvedValue(wrapPaginatedResponse(mockBacktests, 1))
  })

  it('shows back button', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('返回')
  })

  it('displays strategy name after loading', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('MA Cross')
  })

  it('shows basic info section', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('基本信息')
    expect(wrapper.text()).toContain('策略名称')
    expect(wrapper.text()).toContain('版本')
  })

  it('shows strategy code section', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('策略代码')
    expect(wrapper.text()).toContain('class MACross')
  })

  it('shows params section with schema properties', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('参数配置')
    expect(wrapper.text()).toContain('快线周期')
    expect(wrapper.text()).toContain('慢线周期')
  })

  it('shows empty params message when no schema', async () => {
    const noParamsStrategy = createMockStrategy({ id: 's-2', params_schema: { type: 'object' } as any })
    const wrapper = mountDetail(noParamsStrategy)
    await flushPromises()
    expect(wrapper.text()).toContain('该策略没有可配置的参数')
  })

  it('shows action buttons', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('回测')
    expect(wrapper.text()).toContain('模拟交易')
    expect(wrapper.text()).toContain('实盘交易')
    expect(wrapper.text()).toContain('删除')
  })

  it('shows backtest history section', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('回测历史')
  })

  it('shows empty backtest history message', async () => {
    vi.mocked(backtestApi.getBacktests).mockResolvedValue(wrapPaginatedResponse([]))
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.text()).toContain('暂无回测记录')
  })
})

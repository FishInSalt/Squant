import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { mountView } from '@/__tests__/test-utils'
import StrategyList from './StrategyList.vue'
import { useStrategyStore } from '@/stores/strategy'
import { createMockStrategy } from '@/__tests__/fixtures'

const mockStrategies = [
  createMockStrategy({ id: 's-1', name: 'MA Cross', status: 'active', description: '均线交叉策略' }),
  createMockStrategy({ id: 's-2', name: 'RSI Reversal', status: 'active', description: '' }),
]

describe('StrategyList', () => {
  it('renders page title', async () => {
    const wrapper = mountView(StrategyList)
    await flushPromises()
    expect(wrapper.text()).toContain('策略库')
  })

  it('shows upload button', async () => {
    const wrapper = mountView(StrategyList)
    await flushPromises()
    expect(wrapper.text()).toContain('上传策略')
  })

  it('calls loadStrategies on mount', async () => {
    mountView(StrategyList)
    await flushPromises()
    const store = useStrategyStore()
    expect(store.loadStrategies).toHaveBeenCalled()
  })

  it('displays strategy cards when strategies exist', async () => {
    const wrapper = mountView(StrategyList)
    await flushPromises()
    const store = useStrategyStore()
    store.$patch((state) => { state.strategies = mockStrategies })
    await nextTick()
    expect(wrapper.text()).toContain('MA Cross')
    expect(wrapper.text()).toContain('RSI Reversal')
  })

  it('shows action buttons on strategy cards', async () => {
    const wrapper = mountView(StrategyList)
    await flushPromises()
    const store = useStrategyStore()
    store.$patch((state) => { state.strategies = mockStrategies })
    await nextTick()
    expect(wrapper.text()).toContain('回测')
    expect(wrapper.text()).toContain('模拟')
    expect(wrapper.text()).toContain('实盘')
    expect(wrapper.text()).toContain('删除')
  })

  it('shows empty state when no strategies', async () => {
    const wrapper = mountView(StrategyList)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无策略')
  })

  it('shows description or fallback text', async () => {
    const wrapper = mountView(StrategyList)
    await flushPromises()
    const store = useStrategyStore()
    store.$patch((state) => { state.strategies = mockStrategies })
    await nextTick()
    expect(wrapper.text()).toContain('均线交叉策略')
    expect(wrapper.text()).toContain('暂无描述')
  })
})

import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import StrategyUpload from './StrategyUpload.vue'

vi.mock('@/api/strategy', () => ({
  createStrategy: vi.fn(),
  validateStrategy: vi.fn(),
}))

describe('StrategyUpload', () => {
  it('renders page title', async () => {
    const wrapper = mountView(StrategyUpload)
    await flushPromises()
    expect(wrapper.text()).toContain('上传策略')
  })

  it('shows upload area with instructions', async () => {
    const wrapper = mountView(StrategyUpload)
    await flushPromises()
    expect(wrapper.text()).toContain('点击上传')
    expect(wrapper.text()).toContain('.py')
  })

  it('shows upload button disabled by default', async () => {
    const wrapper = mountView(StrategyUpload)
    await flushPromises()
    expect(wrapper.text()).toContain('上传并验证')
  })

  it('shows file size limit info', async () => {
    const wrapper = mountView(StrategyUpload)
    await flushPromises()
    expect(wrapper.text()).toContain('1MB')
  })
})

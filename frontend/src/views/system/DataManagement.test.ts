import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import DataManagement from './DataManagement.vue'

describe('DataManagement', () => {
  it('renders page title', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('数据管理')
  })

  it('shows coming soon message', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('功能开发中')
  })

  it('shows feature description', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('历史数据下载与管理功能将在后续版本中提供')
  })
})

import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import DataManagement from './DataManagement.vue'

describe('DataManagement', () => {
  it('renders page title', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('数据管理')
  })

  it('renders download form section', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('下载历史数据')
    expect(wrapper.text()).toContain('开始下载')
  })

  it('renders historical data table section', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('已下载数据')
  })
})

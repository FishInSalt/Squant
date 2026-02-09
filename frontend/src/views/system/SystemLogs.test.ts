import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import SystemLogs from './SystemLogs.vue'

describe('SystemLogs', () => {
  it('renders page title', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('系统日志')
  })

  it('shows coming soon message', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('功能开发中')
  })

  it('shows feature description', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('系统日志查看与导出功能将在后续版本中提供')
  })
})

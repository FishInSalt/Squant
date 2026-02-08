import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import SystemLogs from './SystemLogs.vue'
import * as systemApi from '@/api/system'
import { wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/system', () => ({
  getSystemLogs: vi.fn(),
  exportSystemLogs: vi.fn(),
}))

beforeEach(() => {
  vi.mocked(systemApi.getSystemLogs).mockResolvedValue(
    wrapApiResponse({ items: [], total: 0, page: 1, page_size: 100 })
  )
})

describe('SystemLogs', () => {
  it('renders page title', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('系统日志')
  })

  it('shows export button', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('导出日志')
  })

  it('shows filter bar with level and module filters', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('日志级别')
    expect(wrapper.text()).toContain('模块')
    expect(wrapper.text()).toContain('搜索')
  })

  it('shows query and reset buttons', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('查询')
    expect(wrapper.text()).toContain('重置')
  })

  it('shows auto-refresh checkbox', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('自动刷新')
  })

  it('shows log table column headers', async () => {
    const wrapper = mountView(SystemLogs)
    await flushPromises()
    expect(wrapper.text()).toContain('时间')
    expect(wrapper.text()).toContain('级别')
    expect(wrapper.text()).toContain('模块')
    expect(wrapper.text()).toContain('消息')
  })

  it('calls getSystemLogs on mount', async () => {
    mountView(SystemLogs)
    await flushPromises()
    expect(systemApi.getSystemLogs).toHaveBeenCalled()
  })
})

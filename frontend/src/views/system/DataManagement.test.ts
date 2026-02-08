import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import DataManagement from './DataManagement.vue'
import * as systemApi from '@/api/system'
import { wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/system', () => ({
  getDownloadTasks: vi.fn(),
  startDownload: vi.fn(),
  cancelDownload: vi.fn(),
  getDownloadedData: vi.fn(),
  deleteDownloadedData: vi.fn(),
  searchSymbols: vi.fn(),
}))

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(systemApi.getDownloadTasks).mockResolvedValue(wrapApiResponse([]))
  vi.mocked(systemApi.getDownloadedData).mockResolvedValue(wrapApiResponse([]))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('DataManagement', () => {
  it('renders page title', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('数据管理')
  })

  it('shows download form section', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('下载历史数据')
    expect(wrapper.text()).toContain('交易所')
    expect(wrapper.text()).toContain('交易对')
    expect(wrapper.text()).toContain('时间周期')
  })

  it('shows download button', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('开始下载')
  })

  it('shows task list section', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('下载任务')
    expect(wrapper.text()).toContain('刷新')
  })

  it('shows downloaded data section', async () => {
    const wrapper = mountView(DataManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('已下载数据')
  })

  it('calls APIs on mount', async () => {
    mountView(DataManagement)
    await flushPromises()
    expect(systemApi.getDownloadTasks).toHaveBeenCalled()
    expect(systemApi.getDownloadedData).toHaveBeenCalled()
  })
})

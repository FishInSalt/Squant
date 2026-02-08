import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import ExchangeConfig from './ExchangeConfig.vue'
import * as accountApi from '@/api/account'
import { wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/account', () => ({
  getAccounts: vi.fn(),
  createAccount: vi.fn(),
  updateAccount: vi.fn(),
  deleteAccount: vi.fn(),
  testConnection: vi.fn(),
}))

const mockAccounts = [
  {
    id: 'acc-1',
    name: 'Main OKX',
    exchange: 'okx',
    is_active: true,
    testnet: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'acc-2',
    name: 'Testnet Binance',
    exchange: 'binance',
    is_active: false,
    testnet: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
]

beforeEach(() => {
  vi.mocked(accountApi.getAccounts).mockResolvedValue(wrapApiResponse(mockAccounts))
})

describe('ExchangeConfig', () => {
  it('renders page title', async () => {
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('交易所配置')
  })

  it('shows add account button', async () => {
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('添加账户')
  })

  it('calls getAccounts on mount', async () => {
    mountView(ExchangeConfig)
    await flushPromises()
    expect(accountApi.getAccounts).toHaveBeenCalled()
  })

  it('displays account cards', async () => {
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('Main OKX')
    expect(wrapper.text()).toContain('Testnet Binance')
  })

  it('shows active/inactive status tags', async () => {
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('已启用')
    expect(wrapper.text()).toContain('已禁用')
  })

  it('shows testnet tag for testnet accounts', async () => {
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('测试网')
  })

  it('shows action buttons on cards', async () => {
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('测试连接')
    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).toContain('删除')
  })

  it('shows empty state when no accounts', async () => {
    vi.mocked(accountApi.getAccounts).mockResolvedValue(wrapApiResponse([]))
    const wrapper = mountView(ExchangeConfig)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无交易所账户')
  })
})

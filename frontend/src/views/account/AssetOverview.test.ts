import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import AssetOverview from './AssetOverview.vue'
import * as accountApi from '@/api/account'
import { wrapApiResponse } from '@/__tests__/fixtures'

vi.mock('@/api/account', () => ({
  getAssetOverview: vi.fn(),
}))

const mockOverview = {
  total_usd_value: 125000.5,
  asset_distribution: [
    { asset: 'BTC', total_amount: 2.0, usd_value: 100000, percentage: 79.98 },
    { asset: 'ETH', total_amount: 10.0, usd_value: 25000.5, percentage: 20.02 },
  ],
  accounts: [
    {
      account_id: 'acc-1',
      account_name: 'Main OKX',
      exchange: 'okx' as const,
      total_usd_value: 125000.5,
      updated_at: '2024-01-01T00:00:00Z',
      balances: [
        { currency: 'BTC', available: 1.5, frozen: 0.5, total: 2.0, usd_value: 100000 },
        { currency: 'USDT', available: 25000, frozen: 0.5, total: 25000.5, usd_value: 25000.5 },
      ],
    },
  ],
}

beforeEach(() => {
  vi.mocked(accountApi.getAssetOverview).mockResolvedValue(wrapApiResponse(mockOverview))
})

describe('AssetOverview', () => {
  it('renders page title', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('资产概览')
  })

  it('shows refresh button', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('刷新')
  })

  it('calls getAssetOverview on mount', async () => {
    mountView(AssetOverview)
    await flushPromises()
    expect(accountApi.getAssetOverview).toHaveBeenCalled()
  })

  it('shows total USD value label', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('总资产估值 (USD)')
  })

  it('shows distribution and accounts panels', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('资产分布')
    expect(wrapper.text()).toContain('账户资产')
  })

  it('shows details table headers', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('资产明细')
    expect(wrapper.text()).toContain('可用')
    expect(wrapper.text()).toContain('冻结')
    expect(wrapper.text()).toContain('USD估值')
  })
})

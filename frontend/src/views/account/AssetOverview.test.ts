import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import AssetOverview from './AssetOverview.vue'

describe('AssetOverview', () => {
  it('renders page title', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('资产概览')
  })

  it('shows coming soon message', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('功能开发中')
  })

  it('shows link to account management', async () => {
    const wrapper = mountView(AssetOverview)
    await flushPromises()
    expect(wrapper.text()).toContain('前往账户管理')
  })
})

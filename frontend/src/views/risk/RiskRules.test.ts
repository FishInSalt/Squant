import { flushPromises } from '@vue/test-utils'
import { mountView } from '@/__tests__/test-utils'
import RiskRules from './RiskRules.vue'
import * as riskApi from '@/api/risk'
import { wrapPaginatedResponse } from '@/__tests__/fixtures'

vi.mock('@/api/risk', () => ({
  getRiskRules: vi.fn(),
  createRiskRule: vi.fn(),
  updateRiskRule: vi.fn(),
  deleteRiskRule: vi.fn(),
  toggleRiskRule: vi.fn(),
}))

import type { RiskRuleType } from '@/types/risk'

const mockRules = [
  {
    id: 'rule-1',
    name: '最大持仓限制',
    type: 'max_position_size' as RiskRuleType,
    description: '限制最大持仓比例',
    params: { max_percent: 50 },
    enabled: true,
    last_triggered: '2024-06-01T00:00:00Z',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'rule-2',
    name: '日亏损限制',
    type: 'max_daily_loss' as RiskRuleType,
    description: '限制日最大亏损',
    params: { max_percent: 5 },
    enabled: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
]

beforeEach(() => {
  vi.mocked(riskApi.getRiskRules).mockResolvedValue(wrapPaginatedResponse(mockRules))
})

describe('RiskRules', () => {
  it('renders page title', async () => {
    const wrapper = mountView(RiskRules)
    await flushPromises()
    expect(wrapper.text()).toContain('风控规则')
  })

  it('loads and displays rules', async () => {
    const wrapper = mountView(RiskRules)
    await flushPromises()
    expect(riskApi.getRiskRules).toHaveBeenCalled()
    expect(wrapper.text()).toContain('最大持仓限制')
    expect(wrapper.text()).toContain('日亏损限制')
  })

  it('shows rule descriptions', async () => {
    const wrapper = mountView(RiskRules)
    await flushPromises()
    expect(wrapper.text()).toContain('限制最大持仓比例')
    expect(wrapper.text()).toContain('限制日最大亏损')
  })

  it('shows empty state when no rules', async () => {
    vi.mocked(riskApi.getRiskRules).mockResolvedValue(wrapPaginatedResponse([]))
    const wrapper = mountView(RiskRules)
    await flushPromises()
    expect(wrapper.text()).toContain('暂无风控规则')
  })

  it('shows add rule button', async () => {
    const wrapper = mountView(RiskRules)
    await flushPromises()
    expect(wrapper.text()).toContain('添加规则')
  })

  it('applies disabled class to disabled rules', async () => {
    const wrapper = mountView(RiskRules)
    await flushPromises()
    const disabledCards = wrapper.findAll('.rule-card.disabled')
    expect(disabledCards.length).toBe(1)
  })
})

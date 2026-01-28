import { get, post, put, del } from './index'
import type {
  RiskRule,
  RiskTrigger,
  CircuitBreakerStatus,
  CircuitBreakerAction,
  AutoHaltCondition,
  PaginatedData
} from '@/types'

// ================== 风控规则 (/risk-rules) ==================

// 获取风控规则列表
export const getRiskRules = (params?: {
  page?: number
  page_size?: number
  enabled?: boolean
}) =>
  get<PaginatedData<RiskRule>>('/risk-rules', params)

// 获取单个规则
export const getRiskRule = (id: string) =>
  get<RiskRule>(`/risk-rules/${id}`)

// 创建风控规则
export const createRiskRule = (rule: Omit<RiskRule, 'id' | 'created_at' | 'updated_at' | 'status' | 'last_triggered'>) =>
  post<RiskRule>('/risk-rules', rule)

// 更新风控规则
export const updateRiskRule = (id: string, rule: Partial<RiskRule>) =>
  put<RiskRule>(`/risk-rules/${id}`, rule)

// 删除风控规则
export const deleteRiskRule = (id: string) =>
  del<void>(`/risk-rules/${id}`)

// 启用/禁用规则
export const toggleRiskRule = (id: string, enabled: boolean) =>
  post<RiskRule>(`/risk-rules/${id}/toggle`, { enabled })

// ================== 熔断控制 (/circuit-breaker) ==================

// 获取熔断状态
export const getCircuitBreakerStatus = () =>
  get<CircuitBreakerStatus>('/circuit-breaker/status')

// 激活熔断
export const activateCircuitBreaker = (reason?: string) =>
  post<void>('/circuit-breaker/activate', { reason })

// 解除熔断
export const deactivateCircuitBreaker = () =>
  post<void>('/circuit-breaker/deactivate')

// 紧急平仓所有持仓
export const closeAllPositions = () =>
  post<void>('/circuit-breaker/close-all-positions')

// 执行熔断操作 (兼容旧接口)
export const executeCircuitBreakerAction = (action: CircuitBreakerAction) => {
  switch (action.action) {
    case 'activate':
      return activateCircuitBreaker(action.reason)
    case 'deactivate':
      return deactivateCircuitBreaker()
    case 'close_all_positions':
      return closeAllPositions()
    default:
      return Promise.reject(new Error(`Unknown action: ${action.action}`))
  }
}

// 更新自动熔断条件
export const updateAutoHaltCondition = (id: string, condition: Partial<AutoHaltCondition>) =>
  put<AutoHaltCondition>(`/circuit-breaker/conditions/${id}`, condition)

// ================== 触发记录 (/risk-triggers) ==================

// 获取触发记录
export const getRiskTriggers = (params?: {
  page?: number
  page_size?: number
  rule_id?: string
  rule_type?: string
  start_date?: string
  end_date?: string
}) =>
  get<PaginatedData<RiskTrigger>>('/risk-triggers', params)

// 获取最近的触发记录
export const getRecentTriggers = (limit?: number) =>
  get<RiskTrigger[]>('/risk-triggers/recent', { limit })

import { get, post, put, del } from './index'
import type {
  RiskRule,
  RiskTrigger,
  CircuitBreakerStatus,
  CircuitBreakerAction,
  AutoHaltCondition,
  PaginatedData
} from '@/types'

// 获取风控规则列表
export const getRiskRules = () =>
  get<RiskRule[]>('/risk/rules')

// 获取单个规则
export const getRiskRule = (id: string) =>
  get<RiskRule>(`/risk/rules/${id}`)

// 创建风控规则
export const createRiskRule = (rule: Omit<RiskRule, 'id' | 'created_at' | 'updated_at' | 'status' | 'last_triggered'>) =>
  post<RiskRule>('/risk/rules', rule)

// 更新风控规则
export const updateRiskRule = (id: string, rule: Partial<RiskRule>) =>
  put<RiskRule>(`/risk/rules/${id}`, rule)

// 删除风控规则
export const deleteRiskRule = (id: string) =>
  del<void>(`/risk/rules/${id}`)

// 启用/禁用规则
export const toggleRiskRule = (id: string, enabled: boolean) =>
  post<void>(`/risk/rules/${id}/toggle`, { enabled })

// 获取熔断状态
export const getCircuitBreakerStatus = () =>
  get<CircuitBreakerStatus>('/risk/circuit-breaker/status')

// 执行熔断操作
export const executeCircuitBreakerAction = (action: CircuitBreakerAction) =>
  post<void>('/risk/circuit-breaker/action', action)

// 更新自动熔断条件
export const updateAutoHaltCondition = (id: string, condition: Partial<AutoHaltCondition>) =>
  put<AutoHaltCondition>(`/risk/circuit-breaker/conditions/${id}`, condition)

// 获取触发记录
export const getRiskTriggers = (params?: {
  page?: number
  page_size?: number
  rule_id?: string
  rule_type?: string
  start_date?: string
  end_date?: string
}) =>
  get<PaginatedData<RiskTrigger>>('/risk/triggers', params)

// 获取最近的触发记录
export const getRecentTriggers = (limit?: number) =>
  get<RiskTrigger[]>('/risk/triggers/recent', { limit })

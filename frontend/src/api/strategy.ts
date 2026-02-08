import { get, post, put, del } from './index'
import type { Strategy, ValidationResult, PaginatedData } from '@/types'

// 获取策略列表
export const getStrategies = (params?: {
  page?: number
  page_size?: number
  search?: string
  status?: string
}) =>
  get<PaginatedData<Strategy>>('/strategies', params)

// 获取单个策略
export const getStrategy = (id: string) =>
  get<Strategy>(`/strategies/${id}`)

// 创建策略 (JSON body: name, code, description)
export const createStrategy = (data: {
  name: string
  code: string
  description?: string
  params_schema?: Record<string, unknown>
  default_params?: Record<string, unknown>
}) =>
  post<Strategy>('/strategies', data)

// 验证策略代码
export const validateStrategy = (code: string) =>
  post<ValidationResult>('/strategies/validate', { code })

// 更新策略
export const updateStrategy = (id: string, data: Partial<Strategy>) =>
  put<Strategy>(`/strategies/${id}`, data)

// 删除策略
export const deleteStrategy = (id: string) =>
  del<void>(`/strategies/${id}`)


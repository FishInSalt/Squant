import { get, post, put, del, upload } from './index'
import type { Strategy, ValidationResult, StrategyUploadResponse, PaginatedData } from '@/types'

// 获取策略列表
export const getStrategies = (params?: {
  page?: number
  page_size?: number
  search?: string
  is_valid?: boolean
}) =>
  get<PaginatedData<Strategy>>('/strategies', params)

// 获取单个策略
export const getStrategy = (id: string) =>
  get<Strategy>(`/strategies/${id}`)

// 上传策略文件
export const uploadStrategy = (file: File, onProgress?: (percent: number) => void) =>
  upload<StrategyUploadResponse>('/strategies', file, onProgress)

// 验证策略代码
export const validateStrategy = (code: string) =>
  post<ValidationResult>('/strategies/validate', { code })

// 更新策略
export const updateStrategy = (id: string, data: Partial<Strategy>) =>
  put<Strategy>(`/strategies/${id}`, data)

// 删除策略
export const deleteStrategy = (id: string) =>
  del<void>(`/strategies/${id}`)

// 获取策略代码
export const getStrategyCode = (id: string) =>
  get<{ code: string }>(`/strategies/${id}/code`)

// 获取策略的回测历史
export const getStrategyBacktests = (id: string, limit?: number) =>
  get<{ backtest_id: string; created_at: string; status: string }[]>(
    `/strategies/${id}/backtests`,
    { limit }
  )

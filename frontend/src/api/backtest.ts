import { get, post, del } from './index'
import type { BacktestConfig, BacktestRun, BacktestResult, PaginatedData } from '@/types'

// 启动回测
export const startBacktest = (config: BacktestConfig) =>
  post<BacktestRun>('/backtest/start', config)

// 获取回测状态
export const getBacktestStatus = (id: string) =>
  get<BacktestRun>(`/backtest/${id}`)

// 获取回测结果
export const getBacktestResult = (id: string) =>
  get<BacktestResult>(`/backtest/${id}/result`)

// 获取回测列表
export const getBacktests = (params?: {
  page?: number
  page_size?: number
  strategy_id?: string
  status?: string
}) =>
  get<PaginatedData<BacktestRun>>('/backtest/list', params)

// 删除回测记录
export const deleteBacktest = (id: string) =>
  del<void>(`/backtest/${id}`)

// 导出回测结果
export const exportBacktestResult = (id: string, format: 'csv' | 'json' = 'csv') =>
  get<{ download_url: string }>(`/backtest/${id}/export`, { format })

// 获取正在运行的回测
export const getRunningBacktests = () =>
  get<BacktestRun[]>('/backtest/running')

// 停止回测
export const stopBacktest = (id: string) =>
  post<void>(`/backtest/${id}/stop`)

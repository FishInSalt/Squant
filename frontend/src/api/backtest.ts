import { get, post, del } from './index'
import type { BacktestConfig, BacktestRun, BacktestResult, PaginatedData } from '@/types'

// 启动回测 (异步)
export const startBacktest = (config: BacktestConfig) =>
  post<BacktestRun>('/backtest/async', config)

// 获取回测状态
export const getBacktestStatus = (id: string) =>
  get<BacktestRun>(`/backtest/${id}`)

// 获取回测结果详情
export const getBacktestResult = (id: string) =>
  get<BacktestResult>(`/backtest/${id}/detail`)

// 获取回测列表
export const getBacktests = (params?: {
  page?: number
  page_size?: number
  strategy_id?: string
  status?: string
}) =>
  get<PaginatedData<BacktestRun>>('/backtest', params)

// 删除回测记录
export const deleteBacktest = (id: string) =>
  del<void>(`/backtest/${id}`)

// 导出回测结果
export const exportBacktestResult = (id: string, format: 'csv' | 'json' = 'csv') =>
  get<{ download_url: string }>(`/backtest/${id}/export`, { format })

// 获取正在运行的回测
export const getRunningBacktests = () =>
  get<PaginatedData<BacktestRun>>('/backtest', { status: 'running' })

// 取消回测
export const cancelBacktest = (id: string) =>
  post<void>(`/backtest/${id}/cancel`)

import api, { get, post, del } from './index'
import type { ApiResponse, BacktestConfig, BacktestRun, BacktestResult, PaginatedData } from '@/types'

// 启动回测 (同步创建并执行，超时 5 分钟)
export const startBacktest = (config: BacktestConfig) =>
  api.post<unknown, ApiResponse<BacktestRun>>('/backtest', config, { timeout: 300000 })

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
  get<{ content: string; filename: string; content_type: string }>(`/backtest/${id}/export`, { format })

// 获取正在运行的回测
export const getRunningBacktests = () =>
  get<PaginatedData<BacktestRun>>('/backtest', { status: 'running' })

// 取消回测
export const cancelBacktest = (id: string) =>
  post<void>(`/backtest/${id}/cancel`)

// 检查历史数据可用性
export const checkDataAvailability = (data: {
  exchange: string
  symbol: string
  timeframe: string
  start_date: string
  end_date: string
}) =>
  post<{
    has_data: boolean
    is_complete: boolean
    total_bars: number
    first_bar: string | null
    last_bar: string | null
  }>('/backtest/data/check', data)

import { get, post, del } from './index'
import type { BacktestConfig, BacktestRun, BacktestResult, PaginatedData } from '@/types'

// 启动回测 (异步创建并后台执行，立即返回)
export const startBacktest = (config: BacktestConfig) =>
  post<BacktestRun>('/backtest', config)

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

// 获取回测K线数据（分页加载，支持游标翻页）
export const getBacktestCandles = (id: string, params?: {
  before?: string   // ISO datetime — 获取此时间之前的数据
  after?: string    // ISO datetime — 获取此时间之后的数据
  limit?: number    // 最大返回条数 (1-2000, 默认 1000)
}) =>
  get<{
    candles: { timestamp: string; open: number; high: number; low: number; close: number; volume: number }[]
    total_count: number
  }>(`/backtest/${id}/candles`, params as Record<string, unknown>)

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

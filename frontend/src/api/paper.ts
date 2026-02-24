import { get, post } from './index'
import type { PaperSession, PaperTradingStatus, PaginatedData, EquityCurvePoint } from '@/types'

// 启动模拟交易
export const startPaperTrading = (config: {
  strategy_id: string
  exchange: string
  symbol: string
  timeframe: string
  initial_capital: number
  params: Record<string, unknown>
}) =>
  post<PaperSession>('/paper', config)

// 停止模拟交易
export const stopPaperTrading = (id: string) =>
  post<void>(`/paper/${id}/stop`)

// 恢复模拟交易
export const resumePaperTrading = (id: string, config?: { warmup_bars?: number }) =>
  post<PaperSession>(`/paper/${id}/resume`, config)

// 停止所有模拟交易
export const stopAllPaperTrading = () =>
  post<{ stopped_count: number }>('/paper/stop-all')

// 获取会话状态
export const getPaperSession = (id: string) =>
  get<PaperSession>(`/paper/${id}`)

// 获取会话实时状态
export const getPaperSessionStatus = (id: string) =>
  get<PaperTradingStatus>(`/paper/${id}/status`)

// 获取会话列表
export const getPaperSessions = (params?: {
  page?: number
  page_size?: number
  strategy_id?: string
  status?: string
}) =>
  get<PaginatedData<PaperSession>>('/paper/runs', params)

// 获取运行中的会话
export const getRunningPaperSessions = () =>
  get<PaperSession[]>('/paper')

// 获取权益曲线
export const getPaperEquityCurve = (id: string) =>
  get<EquityCurvePoint[]>(`/paper/${id}/equity-curve`)


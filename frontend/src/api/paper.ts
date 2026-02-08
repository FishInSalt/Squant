import { get, post, del } from './index'
import type { PaperSession, PaperTradingStatus, Position, RunLog, Trade, PaginatedData } from '@/types'

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

// 获取会话持仓
export const getPaperPositions = (id: string) =>
  get<Position[]>(`/paper/${id}/positions`)

// 获取会话交易记录
export const getPaperTrades = (id: string, params?: {
  page?: number
  page_size?: number
}) =>
  get<PaginatedData<Trade>>(`/paper/${id}/trades`, params)

// 获取会话日志
export const getPaperLogs = (id: string, params?: {
  limit?: number
  level?: string
  after?: number
}) =>
  get<RunLog[]>(`/paper/${id}/logs`, params)

// 删除会话
export const deletePaperSession = (id: string) =>
  del<void>(`/paper/${id}`)

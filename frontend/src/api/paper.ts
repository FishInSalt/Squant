import { get, post } from './index'
import type { PaperSession, PaperTradingStatus, PaginatedData } from '@/types'

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


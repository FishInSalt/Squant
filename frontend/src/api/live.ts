import { get, post, del } from './index'
import type { LiveSession, Position, RunLog, Trade, RiskConfig, PaginatedData } from '@/types'

// 启动实盘交易
export const startLiveTrading = (config: {
  strategy_id: string
  account_id: string
  exchange: string
  symbol: string
  timeframe: string
  initial_capital: number
  params: Record<string, unknown>
  risk_config: RiskConfig
}) =>
  post<LiveSession>('/live/start', config)

// 停止实盘交易
export const stopLiveTrading = (id: string, close_positions?: boolean) =>
  post<void>(`/live/${id}/stop`, { close_positions })

// 紧急平仓
export const emergencyClosePositions = (id: string) =>
  post<void>(`/live/${id}/emergency-close`)

// 获取会话状态
export const getLiveSession = (id: string) =>
  get<LiveSession>(`/live/${id}`)

// 获取会话列表
export const getLiveSessions = (params?: {
  page?: number
  page_size?: number
  strategy_id?: string
  account_id?: string
  status?: string
}) =>
  get<PaginatedData<LiveSession>>('/live/list', params)

// 获取运行中的会话
export const getRunningLiveSessions = () =>
  get<LiveSession[]>('/live/running')

// 获取会话持仓
export const getLivePositions = (id: string) =>
  get<Position[]>(`/live/${id}/positions`)

// 获取会话交易记录
export const getLiveTrades = (id: string, params?: {
  page?: number
  page_size?: number
}) =>
  get<PaginatedData<Trade>>(`/live/${id}/trades`, params)

// 获取会话日志
export const getLiveLogs = (id: string, params?: {
  limit?: number
  level?: string
  after?: number
}) =>
  get<RunLog[]>(`/live/${id}/logs`, params)

// 更新风控配置
export const updateLiveRiskConfig = (id: string, config: Partial<RiskConfig>) =>
  post<void>(`/live/${id}/risk-config`, config)

// 删除会话
export const deleteLiveSession = (id: string) =>
  del<void>(`/live/${id}`)

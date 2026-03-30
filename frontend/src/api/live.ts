import { get, post } from './index'
import type { LiveSession, LiveSessionOrder, LiveTradingStatus, RiskConfig, PaginatedData, EquityCurvePoint, EmergencyCloseResult } from '@/types'

// 启动实盘交易
export const startLiveTrading = (config: {
  strategy_id: string
  exchange_account_id: string
  symbol: string
  timeframe: string
  initial_equity: number
  params?: Record<string, unknown>
  risk_config: RiskConfig
}) =>
  post<LiveSession>('/live', config)

// 停止实盘交易
export const stopLiveTrading = (id: string, cancel_orders?: boolean) =>
  post<void>(`/live/${id}/stop`, { cancel_orders })

// 紧急平仓
export const emergencyClosePositions = (id: string) =>
  post<EmergencyCloseResult>(`/live/${id}/emergency-close`)

// 获取会话状态
export const getLiveSession = (id: string) =>
  get<LiveSession>(`/live/${id}`)

// 获取会话实时状态
export const getLiveSessionStatus = (id: string) =>
  get<LiveTradingStatus>(`/live/${id}/status`)

// 获取会话列表
export const getLiveSessions = (params?: {
  page?: number
  page_size?: number
  strategy_id?: string
  account_id?: string
  status?: string
}) =>
  get<PaginatedData<LiveSession>>('/live/runs', params)

// 获取运行中的会话
export const getRunningLiveSessions = () =>
  get<LiveSession[]>('/live')

// 获取收益曲线
export const getLiveEquityCurve = (id: string, since?: string) =>
  get<EquityCurvePoint[]>(`/live/${id}/equity-curve`, since ? { since } : undefined)

// 恢复实盘交易
export const resumeLiveTrading = (id: string, warmup_bars?: number) =>
  post<LiveSession>(`/live/${id}/resume`, warmup_bars != null ? { warmup_bars } : undefined)

// 获取会话历史订单（审计表）
export const getLiveSessionOrders = (id: string, params?: { page?: number; page_size?: number }) =>
  get<PaginatedData<LiveSessionOrder>>(`/live/${id}/orders`, params)

// 获取交易日志
export const getLiveLogs = (runId: string, tail = 500) =>
  get<{ logs: string[] }>(`/live/${runId}/logs`, { tail })

// 查询账户可用余额
export const getAccountBalance = (accountId: string, quoteCurrency?: string) =>
  get<{
    account_total_value: number
    quote_currency: string
    running_sessions: Array<{
      run_id: string
      strategy_name: string | null
      symbol: string
      equity: number
    }>
    sessions_total_equity: number
    available: number
  }>(
    `/live/account-balance/${accountId}`,
    quoteCurrency ? { quote_currency: quoteCurrency } : undefined,
  )

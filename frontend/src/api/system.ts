/**
 * System API Module
 *
 * 数据下载和管理接口已实现。日志、状态、配置接口待后端实现。
 */
import api, { get, post, del } from './index'
import type { SystemLog, DataDownloadTask, HistoricalData, PaginatedData } from '@/types'

// 获取系统日志
export const getSystemLogs = (params?: {
  page?: number
  page_size?: number
  level?: string
  module?: string
  search?: string
  start_time?: string
  end_time?: string
}) =>
  get<PaginatedData<SystemLog>>('/system/logs', params)

// 导出系统日志 (返回原始响应用于下载)
export const exportSystemLogs = (params?: {
  level?: string
  module?: string
  start_time?: string
  end_time?: string
}) =>
  api.get('/system/logs/export', {
    params: { ...params, format: 'csv' },
    responseType: 'blob',
  })

// 获取日志级别列表
export const getLogLevels = () =>
  get<string[]>('/system/logs/levels')

// 获取日志模块列表
export const getLogModules = () =>
  get<string[]>('/system/logs/modules')

// 下载历史数据
export const downloadHistoricalData = (params: {
  exchange: string
  symbol: string
  timeframe: string
  start_date: string
  end_date: string
}) =>
  post<DataDownloadTask>('/system/data/download', params)

// 获取下载任务状态
export const getDownloadTaskStatus = (id: string) =>
  get<DataDownloadTask>(`/system/data/download/${id}`)

// 获取下载任务列表
export const getDownloadTasks = () =>
  get<DataDownloadTask[]>('/system/data/download/tasks')

// 取消下载任务
export const cancelDownloadTask = (id: string) =>
  post<void>(`/system/data/download/${id}/cancel`)

// 删除下载任务记录（仅限已完成/失败的任务）
export const removeDownloadTask = (id: string) =>
  del<void>(`/system/data/download/${id}`)

// 获取已下载的历史数据列表
export const getHistoricalDataList = (params?: {
  exchange?: string
  symbol?: string
  timeframe?: string
}) =>
  get<HistoricalData[]>('/system/data/list', params)

// 删除历史数据
export const deleteHistoricalData = (id: string) =>
  del<void>(`/system/data/${id}`)

// 获取系统状态
export const getSystemStatus = () =>
  get<{
    version: string
    uptime_seconds: number
    running_sessions: number
    pending_orders: number
    connected_exchanges: string[]
  }>('/system/status')

// 获取系统配置
export const getSystemConfig = () =>
  get<Record<string, unknown>>('/system/config')

// 更新系统配置
export const updateSystemConfig = (config: Record<string, unknown>) =>
  post<void>('/system/config', config)

// 获取交易所可用交易对
export const getExchangeSymbols = (exchange: string) =>
  get<string[]>(`/system/symbols/${exchange}`)

// 搜索交易对 (deprecated, use getExchangeSymbols + local filter)
export const searchSymbols = (exchange: string, _query: string) =>
  getExchangeSymbols(exchange)

// Alias exports for component compatibility
export const startDownload = downloadHistoricalData
export const cancelDownload = cancelDownloadTask
export const getDownloadedData = getHistoricalDataList
export const deleteDownloadedData = deleteHistoricalData

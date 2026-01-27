import { get, post, del } from './index'
import type { Order, OrderFilter, PaginatedData } from '@/types'

// 获取当前挂单
export const getOpenOrders = (filter?: OrderFilter) =>
  get<Order[]>('/order/open', filter as Record<string, unknown>)

// 获取历史订单
export const getOrderHistory = (params?: OrderFilter & {
  page?: number
  page_size?: number
}) =>
  get<PaginatedData<Order>>('/order/history', params as Record<string, unknown>)

// 获取单个订单
export const getOrder = (id: string) =>
  get<Order>(`/order/${id}`)

// 取消订单
export const cancelOrder = (id: string) =>
  post<void>(`/order/${id}/cancel`)

// 批量取消订单
export const cancelOrders = (ids: string[]) =>
  post<{ success: string[]; failed: string[] }>('/order/cancel-batch', { ids })

// 取消所有挂单
export const cancelAllOrders = (filter?: {
  exchange?: string
  symbol?: string
  session_id?: string
}) =>
  post<{ cancelled_count: number }>('/order/cancel-all', filter)

// 导出订单记录
export const exportOrders = (filter?: OrderFilter & {
  start_date?: string
  end_date?: string
}, format: 'csv' | 'json' = 'csv') =>
  get<{ download_url: string }>('/order/export', { ...filter, format } as Record<string, unknown>)

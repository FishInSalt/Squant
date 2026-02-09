import { get, post } from './index'
import type { Order, OrderFilter, PaginatedData, OrderStats } from '@/types'

// 获取当前挂单
export const getOpenOrders = (filter?: OrderFilter) =>
  get<Order[]>('/orders/open', filter as Record<string, unknown>)

// 获取订单列表 (含历史)
export const getOrderHistory = (params?: OrderFilter & {
  page?: number
  page_size?: number
}) =>
  get<PaginatedData<Order>>('/orders', params as Record<string, unknown>)

// 获取单个订单
export const getOrder = (id: string) =>
  get<Order>(`/orders/${id}`)

// 获取订单统计
export const getOrderStats = () =>
  get<OrderStats>('/orders/stats')

// 取消订单
export const cancelOrder = (id: string) =>
  post<void>(`/orders/${id}/cancel`)

// 同步订单状态
export const syncOrder = (id: string) =>
  post<Order>(`/orders/${id}/sync`)

// 同步所有挂单状态
export const syncOpenOrders = (symbol?: string) =>
  post<{ synced_count: number; orders: Order[] }>('/orders/sync', { symbol })


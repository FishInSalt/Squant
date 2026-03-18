// 订单相关类型（匹配后端 models/enums.py + schemas/order.py）
export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit'
export type OrderStatus = 'pending' | 'submitted' | 'partial' | 'filled' | 'cancelled' | 'rejected'

// 匹配后端 OrderDetail
export interface Order {
  id: string
  account_id: string
  account_name?: string
  run_id?: string
  exchange: string
  exchange_oid?: string
  symbol: string
  side: OrderSide
  type: OrderType
  status: OrderStatus
  status_display?: string
  price?: number
  amount: number
  filled: number
  remaining_amount: number
  avg_price?: number
  reject_reason?: string
  commission?: number
  commission_asset?: string
  strategy_name?: string
  created_at: string
  updated_at: string
}

export interface OrderFilter {
  account_id?: string
  symbol?: string
  side?: OrderSide
  status?: OrderStatus | OrderStatus[]
  strategy_id?: string
  run_id?: string
  start_time?: string
  end_time?: string
}

// 订单统计
export interface OrderStats {
  total: number
  pending: number
  submitted: number
  partial: number
  filled: number
  cancelled: number
  rejected: number
}

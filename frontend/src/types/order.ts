// 订单相关类型
export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit'
export type OrderStatus = 'pending' | 'open' | 'partial' | 'filled' | 'cancelled' | 'rejected'

export interface Order {
  id: string
  client_order_id?: string
  exchange: string
  symbol: string
  side: OrderSide
  type: OrderType
  status: OrderStatus
  price?: number
  stop_price?: number
  amount: number
  filled: number
  remaining: number
  avg_price?: number
  commission?: number
  commission_asset?: string
  session_id?: string
  strategy_id?: string
  strategy_name?: string
  created_at: string
  updated_at: string
  filled_at?: string
}

export interface OrderFilter {
  exchange?: string
  symbol?: string
  side?: OrderSide
  status?: OrderStatus | OrderStatus[]
  strategy_id?: string
  session_id?: string
  start_date?: string
  end_date?: string
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

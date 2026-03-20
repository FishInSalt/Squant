// 订单相关类型（匹配后端 models/enums.py + schemas/order.py）
export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit'
export type OrderStatus = 'pending' | 'submitted' | 'partial' | 'filled' | 'cancelled' | 'rejected'

// 匹配后端 TradeDetail（逐笔成交记录）
export interface TradeDetail {
  id: string
  order_id: string
  exchange_tid: string | null
  price: number
  amount: number
  fee: number
  fee_currency: string | null
  fill_source: string | null
  taker_or_maker: string | null
  timestamp: string
}

// 数据修正变更字段
export interface CorrectionChange {
  field: string
  before: string
  after: string
}

// 数据修正审计记录
export interface CorrectionRecord {
  timestamp: string
  reason: string
  changes: CorrectionChange[]
  missing_trade_ids?: string[]
}

// 匹配后端 OrderWithTrades（含逐笔成交的订单）
export interface OrderWithTrades {
  id: string
  exchange_oid: string | null
  symbol: string
  side: string
  type: string
  status: string
  price: number | null
  amount: number
  filled: number
  avg_price: number | null
  commission: number | null
  commission_asset: string | null
  created_at: string
  updated_at: string
  trades: TradeDetail[]
  corrections: CorrectionRecord[] | null
}

// 匹配后端 OrderDetail (with optional trades when fetched as OrderWithTrades)
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
  // Per-fill trade executions (present when order detail includes trades)
  trades?: TradeDetail[]
  // Data correction audit log
  corrections?: CorrectionRecord[] | null
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

// 后端返回的原始 Ticker 类型
export interface TickerResponse {
  symbol: string
  last: string
  bid: string | null
  ask: string | null
  high_24h: string | null
  low_24h: string | null
  volume_24h: string | null
  volume_quote_24h: string | null  // USDT 成交额
  change_24h: string | null        // 24h 价格变化
  change_pct_24h: string | null    // 24h 涨跌幅 (%)
  timestamp: string
}

// 前端使用的 Ticker 类型（添加计算字段）
export interface Ticker {
  exchange: string
  symbol: string
  last_price: number
  bid_price: number
  ask_price: number
  high_24h: number
  low_24h: number
  volume_24h: number
  quote_volume_24h: number
  change_24h: number
  change_percent_24h: number
  timestamp: number
}

export interface Candle {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type Timeframe = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w'

export interface WatchlistItem {
  exchange: string
  symbol: string
  addedAt: number
}

export interface MarketOverview {
  exchange: string
  total_pairs: number
  active_pairs: number
  total_volume_24h: number
}

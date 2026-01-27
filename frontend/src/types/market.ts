// 行情相关类型
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

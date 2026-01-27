// 市场数据类型定义

import { safeParseFloat } from '@/utils/numberHelper'

/**
 * 后端返回的Ticker（snake_case）- 与FastAPI Schema完全匹配
 */
export interface TickerResponse {
  exchange: string
  symbol: string
  price: string
  open_price: string
  price_change: string
  price_change_percent: string
  high_price: string
  low_price: string
  volume: string
  quote_volume: string
  timestamp: string
}

/**
 * 前端使用的Ticker（camelCase）- 转换后的数据
 */
export interface Ticker {
  symbol: string
  lastPrice: number
  priceChangePercent: number
  volume: number
  quoteVolume: number
  highPrice: number
  lowPrice: number
  openPrice: number
  prevClosePrice: number
}

/**
 * 后端返回的Candle（snake_case）
 */
export interface CandleResponse {
  exchange: string
  symbol: string
  timeframe: string
  open_time: string
  close_time: string | null
  open_price: string
  high_price: string
  low_price: string
  close_price: string
  volume: string
  quote_volume: string | null
  trades_count: number | null
}

/**
 * 前端使用的K线（camelCase）
 */
export interface KLine {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/**
 * 后端返回的Watchlist（snake_case）
 */
export interface WatchlistResponse {
  id: number
  user_id: number
  exchange: string
  symbol: string
  label: string | null
  sort_order: number
  created_at: string
  updated_at: string | null
}

/**
 * 前端使用的Watchlist（camelCase）
 */
export interface WatchlistItem {
  id: number
  symbol: string
  notes?: string
  createdAt: string
  updatedAt: string | undefined
}

/**
 * 市场概览响应
 */
export interface MarketOverviewResponse {
  tickers: TickerResponse[]
  watchlist: WatchlistResponse[]
}

export interface OrderItem {
  price: number
  amount: number
}

export interface OrderBook {
  asks: OrderItem[]
  bids: OrderItem[]
}

export interface MarketOverview {
  tickers: Ticker[]
  watchlist: WatchlistItem[]
}

/**
 * 类型转换函数：后端响应 → 前端类型
 */
export function convertTickerResponse(response: TickerResponse): Ticker {
  return {
    symbol: response.symbol,
    lastPrice: safeParseFloat(response.price, 0),
    priceChangePercent: safeParseFloat(response.price_change_percent, 0),
    volume: safeParseFloat(response.volume, 0),
    quoteVolume: safeParseFloat(response.quote_volume, 0),
    highPrice: safeParseFloat(response.high_price, 0),
    lowPrice: safeParseFloat(response.low_price, 0),
    openPrice: safeParseFloat(response.open_price, 0),
    prevClosePrice: (safeParseFloat(response.price, 0) - safeParseFloat(response.price_change, 0))
  }
}

/**
 * 类型转换函数：后端Candle → 前端K线
 */
export function convertCandleResponse(response: CandleResponse): KLine {
  return {
    time: new Date(response.open_time).getTime() / 1000,
    open: safeParseFloat(response.open_price, 0),
    high: safeParseFloat(response.high_price, 0),
    low: safeParseFloat(response.low_price, 0),
    close: safeParseFloat(response.close_price, 0),
    volume: safeParseFloat(response.volume, 0),
  }
}

/**
 * 类型转换函数：后端Watchlist → 前端Watchlist
 */
export function convertWatchlistResponse(response: WatchlistResponse): WatchlistItem {
  return {
    id: response.id,
    symbol: response.symbol,
    notes: response.label || undefined,
    createdAt: response.created_at,
    updatedAt: response.updated_at ?? undefined
  }
}

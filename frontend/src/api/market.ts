import { get } from './index'
import type { Ticker, Candle, Timeframe, MarketOverview } from '@/types'

// K线响应类型
interface CandlestickResponse {
  symbol: string
  timeframe: string
  candles: Candle[]
}

// 获取交易所列表
export const getExchanges = () =>
  get<string[]>('/market/exchanges')

// 获取交易对列表
export const getSymbols = (exchange: string) =>
  get<string[]>('/market/symbols', { exchange })

// 获取单个行情 (symbol 作为路径参数)
export const getTicker = (symbol: string) =>
  get<Ticker>(`/market/ticker/${encodeURIComponent(symbol)}`)

// 获取多个行情
export const getTickers = (symbols?: string[]) =>
  get<Ticker[]>('/market/tickers', { symbols: symbols?.join(',') })

// 获取热门行情
export const getHotTickers = (exchange?: string, limit?: number) =>
  get<Ticker[]>('/market/hot', { exchange, limit })

// 获取K线数据 (symbol 作为路径参数)
export const getCandles = (
  symbol: string,
  timeframe: Timeframe,
  limit?: number
) =>
  get<CandlestickResponse>(`/market/candles/${encodeURIComponent(symbol)}`, {
    timeframe,
    limit,
  })

// 获取市场概览
export const getMarketOverview = () =>
  get<MarketOverview[]>('/market/overview')

// 获取支持的时间周期
export const getTimeframes = (exchange: string) =>
  get<Timeframe[]>('/market/timeframes', { exchange })

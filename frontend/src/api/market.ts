import { get } from './index'
import type { Ticker, Candle, Timeframe, MarketOverview } from '@/types'

// 获取交易所列表
export const getExchanges = () =>
  get<string[]>('/market/exchanges')

// 获取交易对列表
export const getSymbols = (exchange: string) =>
  get<string[]>('/market/symbols', { exchange })

// 获取单个行情
export const getTicker = (exchange: string, symbol: string) =>
  get<Ticker>('/market/ticker', { exchange, symbol })

// 获取多个行情
export const getTickers = (exchange: string, symbols?: string[]) =>
  get<Ticker[]>('/market/tickers', { exchange, symbols: symbols?.join(',') })

// 获取热门行情
export const getHotTickers = (exchange?: string, limit?: number) =>
  get<Ticker[]>('/market/hot', { exchange, limit })

// 获取K线数据
export const getCandles = (
  exchange: string,
  symbol: string,
  timeframe: Timeframe,
  limit?: number,
  start?: number,
  end?: number
) =>
  get<Candle[]>('/market/candles', {
    exchange,
    symbol,
    timeframe,
    limit,
    start,
    end,
  })

// 获取市场概览
export const getMarketOverview = () =>
  get<MarketOverview[]>('/market/overview')

// 获取支持的时间周期
export const getTimeframes = (exchange: string) =>
  get<Timeframe[]>('/market/timeframes', { exchange })

import { get, put, post, del } from './index'
import type { Ticker, Candle, Timeframe } from '@/types'
import type {
  TickerResponse,
  CandlestickResponse,
  CandlestickItem,
  WatchlistItemResponse,
  WatchlistCheckResponse,
} from '@/types/generated'

// 交易所配置响应类型
interface ExchangeConfigResponse {
  current: string
  supported: string[]
}

// 交易所切换响应类型
interface ExchangeSwitchResponse {
  current: string
  previous: string
}

// 转换后端 Candle 响应为前端 Candle 类型
function transformCandle(data: CandlestickItem): Candle {
  return {
    timestamp: new Date(data.timestamp).getTime(),  // 转换为毫秒时间戳
    open: data.open,
    high: data.high,
    low: data.low,
    close: data.close,
    volume: data.volume,
  }
}

// 当前交易所（从后端同步）
let currentExchangeId = 'okx'

// 转换后端 Ticker 响应为前端 Ticker 类型
function transformTicker(data: TickerResponse): Ticker {
  const last = data.last ?? 0
  return {
    exchange: currentExchangeId,
    symbol: data.symbol,
    last_price: last,
    bid_price: data.bid ?? 0,
    ask_price: data.ask ?? 0,
    high_24h: data.high_24h ?? last,
    low_24h: data.low_24h ?? last,
    volume_24h: data.volume_24h ?? 0,
    quote_volume_24h: data.volume_quote_24h ?? 0,
    change_24h: data.change_24h ?? 0,
    change_percent_24h: data.change_pct_24h ?? 0,
    timestamp: new Date(data.timestamp).getTime(),
  }
}

// 获取当前交易所配置
export const getExchangeConfig = async () => {
  const response = await get<ExchangeConfigResponse>('/market/exchange')
  // Update local state
  currentExchangeId = response.data.current
  return response
}

// 切换交易所
export const setExchange = async (exchangeId: string) => {
  const response = await put<ExchangeSwitchResponse>(`/market/exchange/${exchangeId}`)
  // Update local state
  currentExchangeId = response.data.current
  return response
}

// 获取当前交易所 ID
export const getCurrentExchangeId = () => currentExchangeId

// 获取交易所列表（从后端获取支持的交易所）
export const getExchanges = async () => {
  try {
    const config = await getExchangeConfig()
    return {
      data: config.data.supported,
      code: 0,
      message: 'success',
    }
  } catch {
    // Fallback if API not available
    return {
      data: ['okx', 'binance', 'bybit'],
      code: 0,
      message: 'success',
    }
  }
}

// 获取单个行情
export const getTicker = async (symbol: string) => {
  const response = await get<TickerResponse>(`/market/ticker/${encodeURIComponent(symbol)}`)
  return {
    ...response,
    data: transformTicker(response.data),
  }
}

// 获取多个行情
export const getTickers = async (symbols?: string[]) => {
  const response = await get<TickerResponse[]>('/market/tickers', {
    symbols: symbols?.join(','),
  })
  return {
    ...response,
    data: response.data.map(transformTicker),
  }
}

// 获取全部行情（不限制数量，由前端进行排序和分页）
export const getAllTickers = async () => {
  const response = await get<TickerResponse[]>('/market/tickers')
  return {
    ...response,
    data: response.data.map(transformTicker),
  }
}

// 获取K线数据
export const getCandles = async (
  symbol: string,
  timeframe: Timeframe,
  limit?: number
) => {
  const response = await get<CandlestickResponse>(`/market/candles/${encodeURIComponent(symbol)}`, {
    timeframe,
    limit,
  })
  return {
    ...response,
    data: {
      ...response.data,
      candles: response.data.candles.map(transformCandle),  // 转换 timestamp 格式
    },
  }
}

// 获取交易对列表（从 tickers 中提取）
export const getSymbols = async (_exchange?: string) => {
  const response = await getTickers()
  return {
    ...response,
    data: response.data.map((t) => t.symbol),
  }
}

// 获取支持的时间周期
// TODO: Replace with actual API call when backend provides timeframe endpoint
// Currently hardcoded based on OKX supported timeframes
export const getTimeframes = async (_exchange?: string) => ({
  data: ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'] as Timeframe[],
  code: 0,
  message: 'success',
})

// ============ 自选列表 API ============

// 获取自选列表
export const getWatchlistApi = () => get<WatchlistItemResponse[]>('/watchlist')

// 添加到自选列表
export const addWatchlistItem = (exchange: string, symbol: string) =>
  post<WatchlistItemResponse>('/watchlist', { exchange, symbol })

// 从自选列表移除
export const removeWatchlistItem = (id: string) => del<void>(`/watchlist/${id}`)

// 检查是否在自选列表
export const checkWatchlistItem = (exchange: string, symbol: string) =>
  get<WatchlistCheckResponse>('/watchlist/check', { exchange, symbol })

// 重新排序自选列表
export const reorderWatchlistApi = (items: { id: string; sort_order: number }[]) =>
  put<WatchlistItemResponse[]>('/watchlist/reorder', { items })

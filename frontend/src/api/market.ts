import { get } from './index'
import type { Ticker, TickerResponse, Candle, Timeframe } from '@/types'

// K线响应类型
interface CandlestickResponse {
  symbol: string
  timeframe: string
  candles: Candle[]
}

// 默认交易所（后端目前只支持 OKX）
const DEFAULT_EXCHANGE = 'okx'

// 转换后端 Ticker 响应为前端 Ticker 类型
function transformTicker(data: TickerResponse): Ticker {
  const last = parseFloat(data.last) || 0
  const high = parseFloat(data.high_24h || '0') || last
  const low = parseFloat(data.low_24h || '0') || last

  return {
    exchange: DEFAULT_EXCHANGE,
    symbol: data.symbol,
    last_price: last,
    bid_price: parseFloat(data.bid || '0') || 0,
    ask_price: parseFloat(data.ask || '0') || 0,
    high_24h: high,
    low_24h: low,
    volume_24h: parseFloat(data.volume_24h || '0') || 0,
    quote_volume_24h: parseFloat(data.volume_quote_24h || '0') || 0,
    change_24h: parseFloat(data.change_24h || '0') || 0,
    change_percent_24h: parseFloat(data.change_pct_24h || '0') || 0,
    timestamp: new Date(data.timestamp).getTime(),
  }
}

// 获取交易所列表
// TODO: Replace with actual API call when backend supports multiple exchanges
// Currently hardcoded as backend only supports OKX
export const getExchanges = async () => ({
  data: [DEFAULT_EXCHANGE],
  code: 0,
  message: 'success',
})

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
export const getCandles = (
  symbol: string,
  timeframe: Timeframe,
  limit?: number
) =>
  get<CandlestickResponse>(`/market/candles/${encodeURIComponent(symbol)}`, {
    timeframe,
    limit,
  })

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

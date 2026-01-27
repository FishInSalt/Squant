// 市场数据 API

import request from './request'
import type {
  TickerResponse,
  Ticker,
  CandleResponse,
  KLine,
  WatchlistResponse,
  WatchlistItem,
  MarketOverviewResponse,
  MarketOverview
} from '@/types/market'
import {
  convertTickerResponse,
  convertCandleResponse,
  convertWatchlistResponse
} from '@/types/market'

/**
 * 获取热门币种列表
 */
export const getTickers = async (): Promise<Ticker[]> => {
  const responses: TickerResponse[] = await request.get('/market/tickers')
  return responses.map(convertTickerResponse)
}

/**
 * 获取单个币种行情
 */
export const getTicker = async (symbol: string): Promise<Ticker> => {
  const response: TickerResponse = await request.get(`/market/ticker/${symbol}`)
  return convertTickerResponse(response)
}

/**
 * 获取K线数据
 */
export const getCandles = async (
  symbol: string,
  interval: string,
  limit = 100
): Promise<KLine[]> => {
  const responses: CandleResponse[] = await request.get(`/market/candles/${symbol}`, {
    params: { timeframe: interval, limit }
  })
  // 转换后按时间升序排序（lightweight-charts要求）
  return responses
    .map(convertCandleResponse)
    .sort((a, b) => a.time - b.time)
}

/**
 * 获取自选列表
 */
export const getWatchlist = async (): Promise<WatchlistItem[]> => {
  const responses: WatchlistResponse[] = await request.get('/market/watchlist')
  return responses.map(convertWatchlistResponse)
}

/**
 * 添加到自选
 */
export const addToWatchlist = async (
  symbol: string,
  notes?: string
): Promise<WatchlistItem> => {
  const response: WatchlistResponse = await request.post('/market/watchlist', {
    exchange: 'okx',
    symbol: symbol.toUpperCase(),
    label: notes || undefined,
    sort_order: 0
  })
  return convertWatchlistResponse(response)
}

/**
 * 更新自选
 */
export const updateWatchlist = async (
  id: number,
  notes?: string
): Promise<WatchlistItem> => {
  const response: WatchlistResponse = await request.put(`/market/watchlist/${id}`, {
    label: notes,
    sort_order: 0
  })
  return convertWatchlistResponse(response)
}

/**
 * 删除自选
 */
export const removeFromWatchlist = async (id: number): Promise<void> => {
  await request.delete(`/market/watchlist/${id}`)
}

/**
 * 获取市场概览
 */
export const getMarketOverview = async (): Promise<MarketOverview> => {
  const response: MarketOverviewResponse = await request.get('/market/overview')
  return {
    tickers: response.tickers.map(convertTickerResponse),
    watchlist: response.watchlist.map(convertWatchlistResponse)
  }
}

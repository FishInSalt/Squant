import type { Ticker, Candle } from '@/types'
import type { WatchlistItemResponse } from '@/types/generated'
import type { Strategy } from '@/types/strategy'
import type { BacktestRun, PaperSession, LiveSession } from '@/types/trading'
import type { ApiResponse, PaginatedData } from '@/types/api'

export function createMockTicker(overrides?: Partial<Ticker>): Ticker {
  return {
    exchange: 'okx',
    symbol: 'BTC/USDT',
    last_price: 50000,
    bid_price: 49999,
    ask_price: 50001,
    high_24h: 51000,
    low_24h: 49000,
    volume_24h: 1234.56,
    quote_volume_24h: 61728000,
    change_24h: 500,
    change_percent_24h: 1.01,
    timestamp: Date.now(),
    ...overrides,
  }
}

export function createMockCandle(overrides?: Partial<Candle>): Candle {
  return {
    timestamp: Date.now(),
    open: 50000,
    high: 51000,
    low: 49000,
    close: 50500,
    volume: 100,
    ...overrides,
  }
}

export function createMockStrategy(overrides?: Partial<Strategy>): Strategy {
  return {
    id: 'strategy-1',
    name: 'Test Strategy',
    description: 'A test strategy',
    code: 'class TestStrategy:\n  pass',
    version: '1.0.0',
    status: 'active',
    params_schema: { type: 'object', properties: {} },
    default_params: {},
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

export function createMockBacktestRun(overrides?: Partial<BacktestRun>): BacktestRun {
  return {
    id: 'backtest-1',
    strategy_id: 'strategy-1',
    strategy_name: 'Test Strategy',
    mode: 'backtest',
    exchange: 'okx',
    symbol: 'BTC/USDT',
    timeframe: '1h',
    status: 'completed',
    progress: 1,
    backtest_start: '2024-01-01T00:00:00Z',
    backtest_end: '2024-06-01T00:00:00Z',
    initial_capital: 10000,
    commission_rate: 0.001,
    slippage: 0.0005,
    params: {},
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

export function createMockPaperSession(overrides?: Partial<PaperSession>): PaperSession {
  return {
    id: 'paper-1',
    strategy_id: 'strategy-1',
    strategy_name: 'Test Strategy',
    mode: 'paper',
    exchange: 'okx',
    symbol: 'BTC/USDT',
    timeframe: '1h',
    status: 'running',
    initial_capital: 10000,
    commission_rate: 0.001,
    params: {},
    created_at: '2024-01-01T00:00:00Z',
    started_at: '2024-01-01T00:01:00Z',
    updated_at: '2024-01-01T00:01:00Z',
    ...overrides,
  }
}

export function createMockLiveSession(overrides?: Partial<LiveSession>): LiveSession {
  return {
    id: 'live-1',
    strategy_id: 'strategy-1',
    strategy_name: 'Test Strategy',
    account_id: 'account-1',
    mode: 'live',
    exchange: 'okx',
    symbol: 'BTC/USDT',
    timeframe: '1h',
    status: 'running',
    initial_capital: 10000,
    commission_rate: 0.001,
    params: {},
    created_at: '2024-01-01T00:00:00Z',
    started_at: '2024-01-01T00:01:00Z',
    updated_at: '2024-01-01T00:01:00Z',
    ...overrides,
  }
}

export function createMockWatchlistItem(overrides?: Partial<WatchlistItemResponse>): WatchlistItemResponse {
  return {
    id: 'wl-1',
    exchange: 'okx',
    symbol: 'BTC/USDT',
    sort_order: 0,
    created_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

export function wrapApiResponse<T>(data: T, code = 0, message = 'success'): ApiResponse<T> {
  return { code, message, data }
}

export function wrapPaginatedResponse<T>(
  items: T[],
  total?: number,
  page = 1,
  page_size = 20
): ApiResponse<PaginatedData<T>> {
  return wrapApiResponse({
    items,
    total: total ?? items.length,
    page,
    page_size,
  })
}

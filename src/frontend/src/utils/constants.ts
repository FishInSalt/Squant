// 常量定义

// API 基础 URL
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

// WebSocket 基础 URL
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'

// K线时间周期（与后端 MarketDataFetcher.TIMEFRAMES 保持一致）
export const CANDLE_INTERVALS = [
  '1m', '3m', '5m', '15m', '30m',
  '1h', '2h', '4h', '6h', '12h',
  '1d', '3d',
  '1w',
  '1M'
] as const
export type CandleInterval = typeof CANDLE_INTERVALS[number]

// 交易所类型
export const EXCHANGES = [
  { label: 'Binance', value: 'binance' },
  { label: 'OKX', value: 'okx' },
  { label: 'Bybit', value: 'bybit' }
] as const

// 策略状态
export const STRATEGY_STATUS = [
  { label: '草稿', value: 'draft', type: 'info' },
  { label: '启用', value: 'active', type: 'success' },
  { label: '禁用', value: 'inactive', type: 'warning' },
  { label: '归档', value: 'archived', type: 'info' }
] as const

// 账户状态
export const ACCOUNT_STATUS = [
  { label: '已连接', value: 'connected', icon: '✅' },
  { label: '未连接', value: 'disconnected', icon: '❌' },
  { label: '未测试', value: 'unknown', icon: '⚠️' }
] as const

// 默认热门币种
export const POPULAR_SYMBOLS = [
  { label: 'BTC/USDT', value: 'BTC-USDT' },
  { label: 'ETH/USDT', value: 'ETH-USDT' },
  { label: 'BNB/USDT', value: 'BNB-USDT' },
  { label: 'SOL/USDT', value: 'SOL-USDT' },
  { label: 'XRP/USDT', value: 'XRP-USDT' },
  { label: 'ADA/USDT', value: 'ADA-USDT' },
  { label: 'AVAX/USDT', value: 'AVAX-USDT' },
  { label: 'DOGE/USDT', value: 'DOGE-USDT' },
  { label: 'DOT/USDT', value: 'DOT-USDT' },
  { label: 'MATIC/USDT', value: 'MATIC-USDT' },
  { label: 'LINK/USDT', value: 'LINK-USDT' },
  { label: 'ATOM/USDT', value: 'ATOM-USDT' },
  { label: 'UNI/USDT', value: 'UNI-USDT' },
  { label: 'LTC/USDT', value: 'LTC-USDT' },
  { label: 'BCH/USDT', value: 'BCH-USDT' }
] as const

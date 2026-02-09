// 通用类型
export interface SelectOption<T = string> {
  label: string
  value: T
  disabled?: boolean
}

export interface TableColumn {
  prop: string
  label: string
  width?: number | string
  minWidth?: number | string
  sortable?: boolean | 'custom'
  fixed?: 'left' | 'right'
  align?: 'left' | 'center' | 'right'
  formatter?: (row: unknown, column: unknown, cellValue: unknown, index: number) => string
}

export interface Pagination {
  page: number
  pageSize: number
  total: number
}

export interface DateRange {
  start: string
  end: string
}

export interface WebSocketMessage<T = unknown> {
  type: string
  channel?: string
  data: T
  timestamp: number
}

export interface SystemLog {
  id: string
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  module: string
  message: string
  source?: string
  data?: Record<string, unknown>
  extra?: Record<string, unknown>
  traceback?: string
}

export interface DataDownloadTask {
  id: string
  exchange: string
  symbol: string
  timeframe: string
  start_date: string
  end_date: string
  status: 'pending' | 'downloading' | 'completed' | 'failed'
  progress: number
  total_candles?: number
  downloaded_candles?: number
  error?: string
  created_at: string
  completed_at?: string
}

export interface HistoricalData {
  id: string
  exchange: string
  symbol: string
  timeframe: string
  start_date: string
  end_date: string
  candle_count: number
  file_size: number
  created_at: string
}

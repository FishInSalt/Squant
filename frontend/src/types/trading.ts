// 交易相关类型
export type TradingMode = 'backtest' | 'paper' | 'live'
export type SessionStatus = 'pending' | 'running' | 'completed' | 'error' | 'stopped' | 'cancelled'

// 回测配置
export interface BacktestConfig {
  strategy_id: string
  exchange: string
  symbol: string
  timeframe: string
  start_date: string
  end_date: string
  initial_capital: number
  commission_rate: number
  slippage: number
  params: Record<string, unknown>
}

// 回测运行
export interface BacktestRun {
  id: string
  strategy_id: string
  strategy_name: string
  config: BacktestConfig
  status: SessionStatus
  progress: number
  result?: BacktestResult
  error?: string
  created_at: string
  completed_at?: string
}

// 回测结果
export interface BacktestResult {
  metrics: BacktestMetrics
  equity_curve: EquityPoint[]
  trades: Trade[]
  drawdown_curve: DrawdownPoint[]
}

export interface BacktestMetrics {
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe_ratio: number
  sortino_ratio: number
  win_rate: number
  profit_factor: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_trade_return: number
  avg_win: number
  avg_loss: number
  max_consecutive_wins: number
  max_consecutive_losses: number
  start_capital: number
  end_capital: number
}

export interface EquityPoint {
  timestamp: number
  equity: number
  benchmark?: number
}

// 用于实盘交易的收益曲线点
export interface EquityCurvePoint {
  timestamp: string
  equity: number
  cash: number
  unrealized_pnl?: number
}

export interface DrawdownPoint {
  timestamp: number
  drawdown: number
}

export interface Trade {
  id: string
  timestamp: number
  symbol: string
  side: 'buy' | 'sell'
  price: number
  quantity: number
  commission: number
  pnl?: number
  pnl_percent?: number
}

// 模拟交易会话
export interface PaperSession {
  id: string
  strategy_id: string
  strategy_name: string
  exchange: string
  symbol: string
  timeframe: string
  status: SessionStatus
  initial_capital: number
  current_equity: number
  unrealized_pnl: number
  realized_pnl: number
  params: Record<string, unknown>
  created_at: string
  started_at?: string
  stopped_at?: string
}

// 实盘交易会话
export interface LiveSession {
  id: string
  strategy_id: string
  strategy_name: string
  account_id: string
  exchange: string
  symbol: string
  timeframe: string
  status: SessionStatus
  initial_capital: number
  current_equity: number
  unrealized_pnl: number
  realized_pnl: number
  params: Record<string, unknown>
  risk_config: RiskConfig
  created_at: string
  started_at?: string
  stopped_at?: string
}

export interface RiskConfig {
  max_position_size: number
  max_order_size: number
  daily_trade_limit: number
  daily_loss_limit: number
  price_deviation_limit?: number
  circuit_breaker_threshold?: number
}

// 运行日志
export interface RunLog {
  timestamp: number
  level: 'debug' | 'info' | 'warning' | 'error'
  message: string
  data?: Record<string, unknown>
}

// 持仓
export interface Position {
  symbol: string
  side: 'long' | 'short'
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_percent: number
}

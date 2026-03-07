// 交易相关类型
export type TradingMode = 'backtest' | 'paper' | 'live'
export type SessionStatus = 'pending' | 'running' | 'completed' | 'error' | 'stopped' | 'cancelled' | 'interrupted'

// 回测配置（用于提交请求）
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

// 回测运行（匹配后端 BacktestRunResponse 扁平结构）
export interface BacktestRun {
  id: string
  strategy_id: string
  strategy_name: string
  mode: string
  symbol: string
  exchange: string
  timeframe: string
  status: SessionStatus
  progress: number
  backtest_start?: string
  backtest_end?: string
  initial_capital?: number
  commission_rate: number
  slippage?: number
  params: Record<string, unknown>
  result?: Record<string, unknown>
  error_message?: string
  started_at?: string
  stopped_at?: string
  created_at: string
  updated_at: string
}

// 回测结果（匹配后端 BacktestDetailResponse）
export interface BacktestResult {
  run: BacktestRun
  metrics: BacktestMetrics | null
  equity_curve: EquityPoint[]
  trades: Trade[]
  fills: Fill[]
  total_bars?: number
  logs?: string[]
}

// 回测指标（匹配后端 BacktestMetrics）
export interface BacktestMetrics {
  total_return: number
  total_return_pct: number
  annualized_return: number
  max_drawdown: number
  max_drawdown_pct: number
  max_drawdown_duration_hours: number
  sharpe_ratio: number
  sortino_ratio: number
  calmar_ratio: number
  volatility: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  profit_factor: number
  avg_trade_return: number
  avg_win: number
  avg_loss: number
  largest_win: number
  largest_loss: number
  max_consecutive_losses: number
  avg_trade_duration_hours: number
  total_duration_days: number
  total_fees: number
}

// 权益曲线点（匹配后端 EquityCurvePoint）
export interface EquityPoint {
  time: string
  equity: number
  cash: number
  position_value: number
  unrealized_pnl: number
  benchmark_equity?: number
}

// 用于实盘交易的收益曲线点
export interface EquityCurvePoint {
  time: string
  equity: number
  cash: number
  unrealized_pnl?: number
}

export interface DrawdownPoint {
  timestamp: number
  drawdown: number
}

// 逐笔成交记录（匹配后端 FillRecordResponse）
export interface Fill {
  order_id: string
  symbol: string
  side: 'buy' | 'sell'
  price: number
  amount: number
  fee: number
  timestamp: string
}

// 交易记录（匹配后端 TradeRecordResponse）
export interface Trade {
  symbol: string
  side: 'buy' | 'sell'
  entry_time: string
  entry_price: number
  exit_time?: string
  exit_price?: number
  amount: number
  pnl: number
  pnl_pct: number
  fees: number
}

// 模拟交易会话（匹配后端 PaperTradingRunResponse）
export interface PaperSession {
  id: string
  strategy_id: string
  strategy_name: string
  mode: string
  exchange: string
  symbol: string
  timeframe: string
  status: SessionStatus
  initial_capital?: number
  commission_rate: number
  slippage?: number
  params: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  stopped_at?: string
  updated_at: string
  equity?: number
  unrealized_pnl?: number
}

// 实盘交易会话（匹配后端 LiveTradingRunResponse / LiveTradingListItem）
export interface LiveSession {
  id: string
  strategy_id: string
  strategy_name: string
  account_id?: string
  mode: string
  exchange: string
  symbol: string
  timeframe: string
  status: SessionStatus
  initial_capital?: number
  commission_rate: number
  slippage?: number
  params: Record<string, unknown>
  error_message?: string
  created_at: string
  started_at?: string
  stopped_at?: string
  updated_at: string
  equity?: number
  cash?: number
}

export interface RiskConfig {
  max_position_size: number
  max_order_size: number
  daily_trade_limit: number
  daily_loss_limit: number
  price_deviation_limit?: number
  circuit_breaker_threshold?: number
  min_order_value?: number
}

// 运行日志
export interface RunLog {
  timestamp: number
  level: 'debug' | 'info' | 'warning' | 'error'
  message: string
  data?: Record<string, unknown>
}

// 持仓（匹配后端 PositionInfo）
// symbol 是 status.positions dict 的 key，由前端在展示时注入
// side 由 amount 正负推断: amount > 0 为多头, amount < 0 为空头
export interface Position {
  amount: number
  avg_entry_price: number
  current_price?: number
  unrealized_pnl?: number
}

// 待处理订单信息（匹配后端 PendingOrderInfo）
export interface PendingOrderInfo {
  id: string
  symbol: string
  side: string
  type: string
  amount: number
  price?: number
  status: string
  created_at?: string
}

// 当前持仓入场信息（匹配后端 OpenTradeInfo）
export interface OpenTrade {
  symbol: string
  side: 'buy' | 'sell'
  entry_time: string
  entry_price: number
  amount: number
  fees: number
}

// 模拟交易实时状态（匹配后端 PaperTradingStatusResponse）
export interface PaperTradingStatus {
  run_id: string
  symbol: string
  timeframe: string
  is_running: boolean
  started_at?: string
  stopped_at?: string
  error_message?: string
  bar_count: number
  cash: number
  equity: number
  initial_capital: number
  total_fees: number
  unrealized_pnl: number
  realized_pnl: number
  positions: Record<string, Position>
  pending_orders: PendingOrderInfo[]
  completed_orders_count: number
  trades_count: number
  trades: Trade[]
  fills: Fill[]
  open_trade?: OpenTrade
  logs: string[]
}

// 实盘订单信息（匹配后端 LiveOrderInfo）
export interface LiveOrderInfo {
  internal_id: string
  exchange_order_id?: string
  symbol: string
  side: string
  type: string
  amount: number
  filled_amount: number
  price?: number
  avg_fill_price?: number
  status: string
  created_at?: string
  updated_at?: string
}

// 风控状态（匹配后端 RiskStateResponse）
export interface RiskState {
  daily_pnl: number
  daily_trade_count: number
  consecutive_losses: number
  circuit_breaker_active: boolean
  max_position_size: number
  max_order_size: number
  daily_trade_limit: number
  daily_loss_limit: number
}

// 实盘交易实时状态（匹配后端 LiveTradingStatusResponse）
export interface LiveTradingStatus {
  run_id: string
  symbol: string
  timeframe: string
  is_running: boolean
  started_at?: string
  stopped_at?: string
  error_message?: string
  bar_count: number
  cash: number
  equity: number
  initial_capital: number
  total_fees: number
  unrealized_pnl: number
  realized_pnl: number
  positions: Record<string, Position>
  pending_orders: PendingOrderInfo[]
  live_orders: LiveOrderInfo[]
  completed_orders_count: number
  trades_count: number
  risk_state?: RiskState
}

// WebSocket 交易状态事件类型
export interface TradingBarUpdate {
  event: 'bar_update'
  run_id: string
  bar_count: number
  cash: string
  equity: string
  unrealized_pnl: string
  realized_pnl: string
  total_fees: string
  completed_orders_count: number
  trades_count: number
  positions: Record<string, { amount: string; avg_entry_price: string }>
  pending_orders: PendingOrderInfo[]
  open_trade?: OpenTrade
  new_fills: Fill[]
  new_trades: Trade[]
  new_logs: string[]
  risk_state?: Record<string, unknown>
}

export interface TradingEngineStopped {
  event: 'engine_stopped'
  run_id: string
  error_message?: string
  stopped_at?: string
}

export interface TradingFillEvent {
  event: 'fill'
  run_id: string
  fill: {
    order_id: string
    symbol: string
    side: string
    price: string
    amount: string
    fee: string
    timestamp: string | null
  }
  cash: string
  equity: string
  unrealized_pnl: string
  positions: Record<string, { amount: string; avg_entry_price: string }>
  pending_orders: PendingOrderInfo[]
  open_trade?: OpenTrade
}

export type TradingStatusEvent = TradingBarUpdate | TradingEngineStopped | TradingFillEvent

// 实盘会话成交记录（匹配后端 LiveSessionTradeResponse）
export interface LiveSessionTrade {
  id: string
  price: number
  amount: number
  fee: number
  fee_currency?: string
  timestamp: string
}

// 实盘会话订单记录（匹配后端 LiveSessionOrderResponse，审计表）
export interface LiveSessionOrder {
  id: string
  exchange_oid?: string
  symbol: string
  side: string
  type: string
  amount: number
  filled: number
  avg_price?: number
  price?: number
  status: string
  trades: LiveSessionTrade[]
  created_at: string
  updated_at: string
}

// 紧急平仓响应（匹配后端 EmergencyCloseResponse）
export interface EmergencyCloseResult {
  run_id: string
  status: string
  message?: string
  orders_cancelled?: number
  positions_closed?: number
  remaining_positions?: Array<{ symbol: string; amount: string; side: string }>
  errors?: Array<Record<string, unknown>>
}

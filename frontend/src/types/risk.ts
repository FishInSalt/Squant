// 风控相关类型
export type RiskRuleType =
  | 'max_position_size'
  | 'max_daily_loss'
  | 'max_drawdown'
  | 'max_order_size'
  | 'max_open_orders'
  | 'trading_hours'
  | 'price_deviation'
  | 'custom'

export type RiskRuleStatus = 'active' | 'inactive' | 'triggered'

export interface RiskRule {
  id: string
  name: string
  type: RiskRuleType
  description: string
  enabled: boolean
  status: RiskRuleStatus
  params: Record<string, unknown>
  action: 'warn' | 'block' | 'halt'
  created_at: string
  updated_at: string
  last_triggered?: string
}

export interface RiskTrigger {
  id: string
  rule_id: string
  rule_name: string
  rule_type: RiskRuleType
  session_id?: string
  strategy_name?: string
  exchange?: string
  symbol?: string
  trigger_value: unknown
  threshold_value: unknown
  action_taken: 'warn' | 'block' | 'halt'
  message: string
  created_at: string
}

export interface CircuitBreakerStatus {
  global_halt: boolean
  halt_reason?: string
  halted_at?: string
  halted_by?: string
  auto_halt_conditions: AutoHaltCondition[]
  active_sessions_count: number
  pending_orders_count: number
}

export interface AutoHaltCondition {
  id: string
  name: string
  enabled: boolean
  condition_type: 'total_loss' | 'consecutive_losses' | 'drawdown' | 'error_rate'
  threshold: number
  time_window_minutes?: number
  current_value: number
}

export interface CircuitBreakerAction {
  action: 'trigger' | 'reset' | 'close_all_positions'
  reason?: string
}

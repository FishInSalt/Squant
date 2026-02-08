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

// 匹配后端 RiskRuleResponse
export interface RiskRule {
  id: string
  name: string
  type: RiskRuleType
  description?: string
  enabled: boolean
  params: Record<string, unknown>
  last_triggered?: string
  created_at: string
  updated_at: string
}

// 匹配后端 RiskTriggerListItem
export interface RiskTrigger {
  id: string
  time: string
  rule_id?: string
  run_id?: string
  trigger_type: string
  details: Record<string, unknown>
  rule_name?: string
  rule_type?: string
  strategy_name?: string
  symbol?: string
  message?: string
}

export interface CircuitBreakerStatus {
  is_active: boolean
  trigger_reason?: string
  triggered_at?: string
  trigger_type?: string
  cooldown_until?: string
  active_live_sessions: number
  active_paper_sessions: number
}

export interface CircuitBreakerAction {
  action: 'trigger' | 'reset' | 'close_all_positions'
  reason?: string
}

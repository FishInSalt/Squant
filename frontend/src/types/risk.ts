// 风控相关类型（匹配后端 models/enums.py RiskRuleType）
export type RiskRuleType =
  | 'order_limit'
  | 'position_limit'
  | 'daily_loss_limit'
  | 'total_loss_limit'
  | 'frequency_limit'
  | 'volatility_break'

// 匹配后端 RiskRuleResponse
export interface RiskRule {
  id: string
  name: string
  type: RiskRuleType
  description?: string
  enabled: boolean
  params: Record<string, unknown>
  last_triggered_at?: string
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

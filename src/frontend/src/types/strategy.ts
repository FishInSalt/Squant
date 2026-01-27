// 策略类型定义

export type StrategyStatus = 'draft' | 'active' | 'inactive' | 'archived'

export interface Strategy {
  id: number
  name: string
  description?: string
  status: StrategyStatus
  symbol: string
  parameters: Record<string, any>
  createdAt: string
  updatedAt: string
}

export interface CreateStrategyDto {
  name: string
  description?: string
  symbol: string
  parameters: Record<string, any>
}

export interface UpdateStrategyDto {
  name?: string
  description?: string
  status?: StrategyStatus
  parameters?: Record<string, any>
}

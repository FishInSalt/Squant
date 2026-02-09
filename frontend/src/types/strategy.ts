// 策略相关类型
// 匹配后端 StrategyResponse
export interface Strategy {
  id: string
  name: string
  description: string
  code: string
  version: string
  status: 'active' | 'archived'
  params_schema: ParamsSchema
  default_params: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ParamsSchema {
  type: 'object'
  properties: Record<string, ParamField>
  required?: string[]
}

export interface ParamField {
  type: 'string' | 'number' | 'integer' | 'boolean' | 'array'
  title?: string
  description?: string
  default?: unknown
  minimum?: number
  maximum?: number
  enum?: (string | number)[]
  items?: ParamField
}

// 匹配后端 ValidationResultResponse — errors/warnings 为 string[]
export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  // 匹配后端 StrategyInfo
  strategy_info?: {
    class_name?: string
    has_on_bar: boolean
    has_init: boolean
  }
}


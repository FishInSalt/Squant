// 策略相关类型
export interface Strategy {
  id: string
  name: string
  description: string
  code: string
  version: string
  status: 'active' | 'archived'
  params_schema: ParamsSchema
  created_at: string
  updated_at: string
  validation_errors?: string[]
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

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  warnings: ValidationWarning[]
  strategy_info?: {
    name: string
    class_name: string
    params_schema: ParamsSchema
  }
}

export interface ValidationError {
  line?: number
  column?: number
  message: string
  code: string
}

export interface ValidationWarning {
  line?: number
  column?: number
  message: string
  code: string
}


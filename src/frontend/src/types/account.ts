// 账户类型定义

export type ExchangeType = 'BINANCE' | 'OKX' | 'HUOBI'

/**
 * 交易所选项（用于表单下拉框）
 */
export const EXCHANGES = [
  { label: 'Binance', value: 'BINANCE' as ExchangeType },
  { label: 'OKX', value: 'OKX' as ExchangeType },
  { label: 'Huobi', value: 'HUOBI' as ExchangeType }
] as const

/**
 * 后端返回的ExchangeAccount（snake_case）
 */
export interface ExchangeAccountResponse {
  id: number
  user_id: number
  exchange: ExchangeType
  label: string
  is_active: boolean
  is_validated: boolean
  is_demo: boolean
  last_validated_at: string | null
  created_at: string
  updated_at: string | null
}

/**
 * 前端使用的ExchangeAccount（camelCase）
 */
export interface ExchangeAccount {
  id: number
  userId: number
  exchange: ExchangeType
  name: string
  isActive: boolean
  isValidated: boolean
  isDemo: boolean
  lastValidatedAt: string | null | undefined
  createdAt: string
  updatedAt: string | null | undefined
}

/**
 * 前端使用的表单数据（camelCase）
 */
export interface AccountFormData {
  name: string
  exchange: ExchangeType
  apiKey: string
  apiSecret: string
  passphrase?: string
  isDemo?: boolean
}

/**
 * 创建账户请求（snake_case，与后端一致）
 */
export interface CreateAccountDto {
  exchange: ExchangeType
  label: string
  api_key: string
  api_secret: string
  passphrase?: string
  is_demo?: boolean
}

/**
 * 前端使用的创建表单数据（camelCase）
 */
export interface CreateAccountForm {
  name: string
  exchange: ExchangeType
  apiKey: string
  apiSecret: string
  passphrase?: string
}

/**
 * 更新账户请求（snake_case）
 */
export interface UpdateAccountDto {
  label?: string
  api_key?: string
  api_secret?: string
  passphrase?: string
  is_active?: boolean
  is_demo?: boolean
}

/**
 * 前端使用的更新表单数据（camelCase）
 */
export interface UpdateAccountForm {
  name?: string
  apiKey?: string
  apiSecret?: string
  passphrase?: string
}

/**
 * 验证凭证请求（snake_case）
 */
export interface ValidateCredentialsDto {
  exchange: ExchangeType
  api_key: string
  api_secret: string
  passphrase?: string
}

/**
 * 后端返回的ValidationResult（snake_case）
 */
export interface ValidationResponse {
  is_valid: boolean
  message: string
  exchange_account_id: number | null
}

/**
 * 前端使用的ValidationResult（camelCase）
 */
export interface ValidationResult {
  isValid: boolean
  message: string
  exchangeAccountId: number | null
}

/**
 * 类型转换函数：后端 → 前端
 */
export function convertExchangeAccountResponse(
  response: ExchangeAccountResponse
): ExchangeAccount {
  return {
    id: response.id,
    userId: response.user_id,
    exchange: response.exchange,
    name: response.label,
    isActive: response.is_active,
    isValidated: response.is_validated,
    isDemo: response.is_demo,
    lastValidatedAt: response.last_validated_at || undefined,
    createdAt: response.created_at,
    updatedAt: response.updated_at || undefined
  }
}

/**
 * 类型转换函数：前端表单 → 后端创建请求
 */
export function convertAccountFormToCreateDto(
  form: AccountFormData
): CreateAccountDto {
  return {
    exchange: form.exchange,
    label: form.name,
    api_key: form.apiKey,
    api_secret: form.apiSecret,
    passphrase: form.passphrase,
    is_demo: form.isDemo || false
  }
}

/**
 * 类型转换函数：前端表单 → 后端更新请求
 */
export function convertAccountFormToUpdateDto(
  form: AccountFormData
): UpdateAccountDto {
  const dto: UpdateAccountDto = {}
  if (form.name !== undefined) {
    dto.label = form.name
  }
  if (form.apiKey !== undefined) {
    dto.api_key = form.apiKey
  }
  if (form.apiSecret !== undefined) {
    dto.api_secret = form.apiSecret
  }
  if (form.passphrase !== undefined) {
    dto.passphrase = form.passphrase
  }
  if (form.isDemo !== undefined) {
    dto.is_demo = form.isDemo
  }
  return dto
}

/**
 * 类型转换函数：后端验证结果 → 前端验证结果
 */
export function convertValidationResponse(
  response: ValidationResponse
): ValidationResult {
  return {
    isValid: response.is_valid,
    message: response.message,
    exchangeAccountId: response.exchange_account_id
  }
}

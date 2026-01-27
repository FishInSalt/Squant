// 账户 API

import request from './request'
import type {
  ExchangeAccountResponse,
  ExchangeAccount,
  AccountFormData,
  ValidateCredentialsDto,
  ValidationResult,
  ValidationResponse
} from '@/types/account'
import {
  convertExchangeAccountResponse,
  convertAccountFormToCreateDto,
  convertAccountFormToUpdateDto,
  convertValidationResponse
} from '@/types/account'

/**
 * 获取账户列表
 */
export const getAccounts = async (): Promise<ExchangeAccount[]> => {
  const responses: ExchangeAccountResponse[] = await request.get('/accounts')
  return responses.map(convertExchangeAccountResponse)
}

/**
 * 获取单个账户
 */
export const getAccount = async (id: number): Promise<ExchangeAccount> => {
  const response: ExchangeAccountResponse = await request.get(`/accounts/${id}`)
  return convertExchangeAccountResponse(response)
}

/**
 * 创建账户
 */
export const createAccount = async (data: AccountFormData): Promise<ExchangeAccount> => {
  const response: ExchangeAccountResponse = await request.post('/accounts', convertAccountFormToCreateDto(data))
  return convertExchangeAccountResponse(response)
}

/**
 * 更新账户
 */
export const updateAccount = async (
  id: number,
  data: AccountFormData
): Promise<ExchangeAccount> => {
  const response: ExchangeAccountResponse = await request.put(`/accounts/${id}`, convertAccountFormToUpdateDto(data))
  return convertExchangeAccountResponse(response)
}

/**
 * 删除账户
 */
export const deleteAccount = async (id: number): Promise<void> => {
  await request.delete(`/accounts/${id}`)
}

/**
 * 验证已有账户连接
 */
export const validateAccount = async (id: number): Promise<ValidationResult> => {
  const response: ValidationResponse = await request.post(`/accounts/${id}/validate`)
  return convertValidationResponse(response)
}

/**
 * 验证新凭证（不保存）
 */
export const validateCredentials = async (
  data: ValidateCredentialsDto
): Promise<ValidationResult> => {
  const response: ValidationResponse = await request.post('/accounts/validate', data)
  return convertValidationResponse(response)
}

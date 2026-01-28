import { get, post, put, del } from './index'
import type {
  ExchangeAccount,
  ExchangeAccountCreate,
  ExchangeAccountUpdate,
  AccountBalance,
  AssetOverview
} from '@/types'

// ================== 交易所账户配置 (/exchange-accounts) ==================

// 获取交易所账户列表
export const getAccounts = () =>
  get<ExchangeAccount[]>('/exchange-accounts')

// 获取单个账户
export const getAccount = (id: string) =>
  get<ExchangeAccount>(`/exchange-accounts/${id}`)

// 创建账户
export const createAccount = (account: ExchangeAccountCreate) =>
  post<ExchangeAccount>('/exchange-accounts', account)

// 更新账户
export const updateAccount = (id: string, account: ExchangeAccountUpdate) =>
  put<ExchangeAccount>(`/exchange-accounts/${id}`, account)

// 删除账户
export const deleteAccount = (id: string) =>
  del<void>(`/exchange-accounts/${id}`)

// 测试连接
export const testConnection = (id: string) =>
  post<{ success: boolean; message: string; latency_ms?: number }>(`/exchange-accounts/${id}/test`)

// 刷新账户状态
export const refreshAccountStatus = (id: string) =>
  post<ExchangeAccount>(`/exchange-accounts/${id}/refresh`)

// ================== 账户余额 (/account) ==================

// 获取当前账户余额
export const getAccountBalance = (exchange?: string) =>
  get<AccountBalance>('/account/balance', { exchange })

// 获取所有账户余额
export const getAllBalances = () =>
  get<AccountBalance[]>('/account/balances')

// 获取资产概览
export const getAssetOverview = () =>
  get<AssetOverview>('/account/overview')

// 获取支持的交易所
export const getSupportedExchanges = () =>
  get<{ id: string; name: string; has_testnet: boolean }[]>('/exchange-accounts/supported')

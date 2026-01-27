import { get, post, put, del } from './index'
import type {
  ExchangeAccount,
  ExchangeAccountCreate,
  ExchangeAccountUpdate,
  AccountBalance,
  AssetOverview
} from '@/types'

// 获取交易所账户列表
export const getAccounts = () =>
  get<ExchangeAccount[]>('/account/list')

// 获取单个账户
export const getAccount = (id: string) =>
  get<ExchangeAccount>(`/account/${id}`)

// 创建账户
export const createAccount = (account: ExchangeAccountCreate) =>
  post<ExchangeAccount>('/account/create', account)

// 更新账户
export const updateAccount = (id: string, account: ExchangeAccountUpdate) =>
  put<ExchangeAccount>(`/account/${id}`, account)

// 删除账户
export const deleteAccount = (id: string) =>
  del<void>(`/account/${id}`)

// 测试连接
export const testConnection = (id: string) =>
  post<{ success: boolean; message: string; latency_ms?: number }>(`/account/${id}/test`)

// 获取账户余额
export const getAccountBalance = (id: string) =>
  get<AccountBalance>(`/account/${id}/balance`)

// 获取所有账户余额
export const getAllBalances = () =>
  get<AccountBalance[]>('/account/balances')

// 获取资产概览
export const getAssetOverview = () =>
  get<AssetOverview>('/account/overview')

// 刷新账户状态
export const refreshAccountStatus = (id: string) =>
  post<ExchangeAccount>(`/account/${id}/refresh`)

// 获取支持的交易所
export const getSupportedExchanges = () =>
  get<{ id: string; name: string; has_testnet: boolean }[]>('/account/exchanges')

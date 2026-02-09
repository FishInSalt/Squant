// 账户相关类型（匹配后端支持的交易所）
export type ExchangeType = 'okx' | 'binance'

export interface ExchangeAccount {
  id: string
  name: string
  exchange: string
  testnet: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ExchangeAccountCreate {
  name: string
  exchange: string
  api_key: string
  api_secret: string
  passphrase?: string
  testnet: boolean
}

export interface ExchangeAccountUpdate {
  name?: string
  api_key?: string
  api_secret?: string
  passphrase?: string
  is_active?: boolean
}

export interface Balance {
  currency: string
  available: number
  frozen: number
  total: number
  usd_value?: number
}

export interface AccountBalance {
  account_id: string
  account_name: string
  exchange: ExchangeType
  balances: Balance[]
  total_usd_value: number
  updated_at: string
}

export interface AssetOverview {
  total_usd_value: number
  accounts: AccountBalance[]
  asset_distribution: AssetDistribution[]
}

export interface AssetDistribution {
  asset: string
  total_amount: number
  usd_value: number
  percentage: number
}

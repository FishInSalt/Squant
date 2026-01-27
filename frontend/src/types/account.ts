// 账户相关类型
export type ExchangeType = 'binance' | 'okx' | 'bybit' | 'huobi' | 'gate'

export interface ExchangeAccount {
  id: string
  name: string
  exchange: ExchangeType
  is_testnet: boolean
  is_active: boolean
  permissions: string[]
  created_at: string
  updated_at: string
  last_connected?: string
  connection_status: 'connected' | 'disconnected' | 'error'
  error_message?: string
}

export interface ExchangeAccountCreate {
  name: string
  exchange: ExchangeType
  api_key: string
  api_secret: string
  passphrase?: string
  is_testnet: boolean
}

export interface ExchangeAccountUpdate {
  name?: string
  api_key?: string
  api_secret?: string
  passphrase?: string
  is_active?: boolean
}

export interface Balance {
  asset: string
  free: number
  locked: number
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

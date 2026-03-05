/**
 * Auto-generated type aliases from OpenAPI schema.
 *
 * These types are the single source of truth for API contracts.
 * DO NOT edit manually — regenerate with: pnpm generate:types
 */
import type { components } from './api-types'

// ================== Common ==================
export type ApiResponse<T> = { code: number; message: string; data: T }
export type PaginatedData<T> = { items: T[]; total: number; page: number; page_size: number }

// ================== Backtest ==================
export type BacktestRunResponse = components['schemas']['BacktestRunResponse']
export type BacktestListItem = components['schemas']['BacktestListItem']
export type BacktestDetailResponse = components['schemas']['BacktestDetailResponse']
export type RunBacktestRequest = components['schemas']['RunBacktestRequest']
export type CreateBacktestRequest = components['schemas']['CreateBacktestRequest']
export type EquityCurvePoint = components['schemas']['EquityCurvePoint']

// ================== Strategy ==================
export type StrategyResponse = components['schemas']['StrategyResponse']
export type StrategyListItem = components['schemas']['StrategyListItem']
export type CreateStrategyRequest = components['schemas']['CreateStrategyRequest']
export type UpdateStrategyRequest = components['schemas']['UpdateStrategyRequest']
export type ValidationResultResponse = components['schemas']['ValidationResultResponse']

// ================== Exchange Account ==================
export type ExchangeAccountResponse = components['schemas']['ExchangeAccountResponse']
export type ExchangeAccountListItem = components['schemas']['ExchangeAccountListItem']
export type CreateExchangeAccountRequest = components['schemas']['CreateExchangeAccountRequest']
export type UpdateExchangeAccountRequest = components['schemas']['UpdateExchangeAccountRequest']
export type ConnectionTestResponse = components['schemas']['ConnectionTestResponse']

// ================== Account / Balance ==================
export type BalanceResponse = components['schemas']['BalanceResponse']
export type BalanceItem = components['schemas']['BalanceItem']

// ================== Order ==================
export type OrderDetail = components['schemas']['OrderDetail']
export type OrderWithTrades = components['schemas']['OrderWithTrades']
export type OrderListData = components['schemas']['OrderListData']
export type OrderStatsResponse = components['schemas']['OrderStatsResponse']
export type CreateOrderRequest = components['schemas']['CreateOrderRequest']
export type TradeDetail = components['schemas']['TradeDetail']
export type SyncOrdersResponse = components['schemas']['SyncOrdersResponse']

// ================== Paper Trading ==================
export type PaperTradingRunResponse = components['schemas']['PaperTradingRunResponse']
export type PaperTradingListItem = components['schemas']['PaperTradingListItem']
export type PaperTradingStatusResponse = components['schemas']['PaperTradingStatusResponse']
export type StartPaperTradingRequest = components['schemas']['StartPaperTradingRequest']

// ================== Live Trading ==================
export type LiveTradingRunResponse = components['schemas']['LiveTradingRunResponse']
export type LiveTradingListItem = components['schemas']['LiveTradingListItem']
export type LiveTradingStatusResponse = components['schemas']['LiveTradingStatusResponse']
export type StartLiveTradingRequest = components['schemas']['StartLiveTradingRequest']
export type StopLiveTradingRequest = components['schemas']['StopLiveTradingRequest']
export type EmergencyCloseResponse = components['schemas']['EmergencyCloseResponse']
export type LiveSessionOrderResponse = components['schemas']['LiveSessionOrderResponse']
export type LiveSessionTradeResponse = components['schemas']['LiveSessionTradeResponse']

// ================== Risk ==================
export type RiskRuleResponse = components['schemas']['RiskRuleResponse']
export type RiskRuleListItem = components['schemas']['RiskRuleListItem']
export type CreateRiskRuleRequest = components['schemas']['CreateRiskRuleRequest']
export type UpdateRiskRuleRequest = components['schemas']['UpdateRiskRuleRequest']
export type RiskConfigRequest = components['schemas']['RiskConfigRequest']
export type RiskTriggerListItem = components['schemas']['RiskTriggerListItem']

// ================== Circuit Breaker ==================
export type CircuitBreakerStatusResponse = components['schemas']['CircuitBreakerStatusResponse']
export type TriggerCircuitBreakerResponse = components['schemas']['TriggerCircuitBreakerResponse']
export type ResetCircuitBreakerResponse = components['schemas']['ResetCircuitBreakerResponse']
export type CloseAllPositionsResponse = components['schemas']['CloseAllPositionsResponse']

// ================== Market ==================
export type TickerResponse = components['schemas']['TickerResponse']
export type CandlestickResponse = components['schemas']['CandlestickResponse']
export type CandlestickItem = components['schemas']['CandlestickItem']
export type AvailableSymbolResponse = components['schemas']['AvailableSymbolResponse']

// ================== Watchlist ==================
export type WatchlistItemResponse = components['schemas']['WatchlistItemResponse']
export type WatchlistCheckResponse = components['schemas']['WatchlistCheckResponse']
export type AddToWatchlistRequest = components['schemas']['AddToWatchlistRequest']

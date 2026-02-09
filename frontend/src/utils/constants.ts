// 颜色常量
export const COLORS = {
  // 涨跌颜色
  UP: '#00C853',
  DOWN: '#FF1744',
  NEUTRAL: '#909399',

  // 状态颜色
  PRIMARY: '#1890FF',
  SUCCESS: '#4CAF50',
  WARNING: '#FF9800',
  DANGER: '#FF4D4F',
  INFO: '#909399',

  // 图表颜色
  CHART_LINE: '#1890FF',
  CHART_AREA: 'rgba(24, 144, 255, 0.1)',
  CHART_GRID: '#E4E7ED',
} as const

// 时间周期选项
export const TIMEFRAME_OPTIONS = [
  { label: '1分钟', value: '1m' },
  { label: '5分钟', value: '5m' },
  { label: '15分钟', value: '15m' },
  { label: '30分钟', value: '30m' },
  { label: '1小时', value: '1h' },
  { label: '4小时', value: '4h' },
  { label: '1天', value: '1d' },
  { label: '1周', value: '1w' },
] as const

// 交易所选项（匹配后端支持的交易所）
export const EXCHANGE_OPTIONS = [
  { label: 'OKX', value: 'okx' },
  { label: 'Binance', value: 'binance' },
  { label: 'Bybit', value: 'bybit' },
] as const

// 支持的交易所（用于账户配置）
export const SUPPORTED_EXCHANGES = [
  { id: 'okx', name: 'OKX', has_testnet: true },
  { id: 'binance', name: 'Binance', has_testnet: true },
  { id: 'bybit', name: 'Bybit', has_testnet: true },
] as const

// 订单方向选项
export const ORDER_SIDE_OPTIONS = [
  { label: '买入', value: 'buy' },
  { label: '卖出', value: 'sell' },
] as const

// 订单类型选项（匹配后端 OrderType 枚举）
export const ORDER_TYPE_OPTIONS = [
  { label: '市价', value: 'market' },
  { label: '限价', value: 'limit' },
] as const

// 订单状态选项（匹配后端 OrderStatus 枚举）
export const ORDER_STATUS_OPTIONS = [
  { label: '待处理', value: 'pending' },
  { label: '已提交', value: 'submitted' },
  { label: '部分成交', value: 'partial' },
  { label: '已成交', value: 'filled' },
  { label: '已取消', value: 'cancelled' },
  { label: '已拒绝', value: 'rejected' },
] as const

// 会话状态选项
export const SESSION_STATUS_OPTIONS = [
  { label: '待启动', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '错误', value: 'error' },
  { label: '已停止', value: 'stopped' },
  { label: '已取消', value: 'cancelled' },
] as const

// 风控规则类型选项（匹配后端 RiskRuleType 枚举）
export const RISK_RULE_TYPE_OPTIONS = [
  { label: '单笔订单限制', value: 'order_limit' },
  { label: '持仓比例限制', value: 'position_limit' },
  { label: '日亏损限制', value: 'daily_loss_limit' },
  { label: '总亏损限制', value: 'total_loss_limit' },
  { label: '交易频率限制', value: 'frequency_limit' },
  { label: '波动熔断', value: 'volatility_break' },
] as const

// 日志级别选项
export const LOG_LEVEL_OPTIONS = [
  { label: 'DEBUG', value: 'debug' },
  { label: 'INFO', value: 'info' },
  { label: 'WARNING', value: 'warning' },
  { label: 'ERROR', value: 'error' },
  { label: 'CRITICAL', value: 'critical' },
] as const

// 分页配置
export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  PAGE_SIZES: [10, 20, 50, 100],
} as const

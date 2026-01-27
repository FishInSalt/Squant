import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

// 格式化数字 - 添加千分位
export function formatNumber(value: number, decimals = 2): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

// 格式化价格 - 自动精度
export function formatPrice(value: number): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }

  if (value >= 1000) {
    return formatNumber(value, 2)
  } else if (value >= 1) {
    return formatNumber(value, 4)
  } else if (value >= 0.01) {
    return formatNumber(value, 6)
  } else {
    return formatNumber(value, 8)
  }
}

// 格式化百分比
export function formatPercent(value: number, decimals = 2): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value, decimals)}%`
}

// 格式化大数字 (K, M, B)
export function formatLargeNumber(value: number): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }

  const abs = Math.abs(value)
  if (abs >= 1e9) {
    return `${(value / 1e9).toFixed(2)}B`
  } else if (abs >= 1e6) {
    return `${(value / 1e6).toFixed(2)}M`
  } else if (abs >= 1e3) {
    return `${(value / 1e3).toFixed(2)}K`
  }
  return formatNumber(value, 2)
}

// 格式化成交量
export function formatVolume(value: number): string {
  return formatLargeNumber(value)
}

// 格式化日期时间
export function formatDateTime(value: string | number | Date, format = 'YYYY-MM-DD HH:mm:ss'): string {
  if (!value) return '-'
  return dayjs(value).format(format)
}

// 格式化日期
export function formatDate(value: string | number | Date): string {
  return formatDateTime(value, 'YYYY-MM-DD')
}

// 格式化时间
export function formatTime(value: string | number | Date): string {
  return formatDateTime(value, 'HH:mm:ss')
}

// 格式化相对时间
export function formatRelativeTime(value: string | number | Date): string {
  if (!value) return '-'
  return dayjs(value).fromNow()
}

// 格式化时长 (秒)
export function formatDuration(seconds: number): string {
  if (seconds === null || seconds === undefined || isNaN(seconds)) {
    return '-'
  }

  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)

  const parts: string[] = []
  if (days > 0) parts.push(`${days}天`)
  if (hours > 0) parts.push(`${hours}小时`)
  if (minutes > 0) parts.push(`${minutes}分`)
  if (secs > 0 || parts.length === 0) parts.push(`${secs}秒`)

  return parts.join('')
}

// 格式化文件大小
export function formatFileSize(bytes: number): string {
  if (bytes === null || bytes === undefined || isNaN(bytes)) {
    return '-'
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unitIndex = 0
  let size = bytes

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }

  return `${size.toFixed(2)} ${units[unitIndex]}`
}

// 格式化订单方向
export function formatOrderSide(side: string): string {
  return side === 'buy' ? '买入' : '卖出'
}

// 格式化订单类型
export function formatOrderType(type: string): string {
  const types: Record<string, string> = {
    market: '市价',
    limit: '限价',
    stop: '止损',
    stop_limit: '止损限价',
  }
  return types[type] || type
}

// 格式化订单状态
export function formatOrderStatus(status: string): string {
  const statuses: Record<string, string> = {
    pending: '待处理',
    open: '挂单中',
    partial: '部分成交',
    filled: '已成交',
    cancelled: '已取消',
    rejected: '已拒绝',
    expired: '已过期',
  }
  return statuses[status] || status
}

// 格式化会话状态
export function formatSessionStatus(status: string): string {
  const statuses: Record<string, string> = {
    pending: '待启动',
    running: '运行中',
    completed: '已完成',
    failed: '已失败',
    stopped: '已停止',
  }
  return statuses[status] || status
}

// 格式化交易所名称
export function formatExchangeName(exchange: string): string {
  const exchanges: Record<string, string> = {
    binance: 'Binance',
    okx: 'OKX',
    bybit: 'Bybit',
    huobi: 'Huobi',
    gate: 'Gate.io',
  }
  return exchanges[exchange] || exchange
}

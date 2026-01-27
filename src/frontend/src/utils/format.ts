// 格式化工具函数

/**
 * 格式化价格
 */
export function formatPrice(price: number, decimals = 2): string {
  return price.toFixed(decimals)
}

/**
 * 格式化百分比
 */
export function formatPercentage(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

/**
 * 格式化成交量
 */
export function formatVolume(volume: number): string {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(2)}K`
  return volume.toString()
}

/**
 * 脱敏敏感信息
 */
export function maskSecret(secret: string): string {
  if (!secret) return ''
  const len = secret.length
  if (len <= 8) return '••••••••'
  return secret.substring(0, 4) + '••••••••' + secret.substring(len - 4)
}

/**
 * 格式化日期时间
 */
export function formatDateTime(timestamp: number | string): string {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

/**
 * 格式化日期
 */
export function formatDate(timestamp: number | string): string {
  const date = new Date(timestamp)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

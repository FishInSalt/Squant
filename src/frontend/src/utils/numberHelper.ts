/**
 * 数字转换工具函数
 *
 * 提供安全的类型转换，避免 NaN 错误
 */

/**
 * 安全地将值转换为数字
 *
 * @param value - 要转换的值（可以是字符串、数字、undefined、null）
 * @param defaultValue - 转换失败时的默认值
 * @returns 转换后的数字或默认值
 *
 * @example
 * safeParseFloat("123.45") // 123.45
 * safeParseFloat("") // 0
 * safeParseFloat(null) // 0
 * safeParseFloat("abc") // 0
 * safeParseFloat("NaN") // 0
 */
export function safeParseFloat(
  value: string | number | undefined | null,
  defaultValue: number = 0
): number {
  // 如果已经是数字类型且有效
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : defaultValue
  }

  // 如果是字符串且非空
  if (typeof value === 'string' && value.trim() !== '') {
    const trimmed = value.trim()
    const parsed = parseFloat(trimmed)

    // 验证转换结果是否为有效数字
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  // 默认返回默认值
  return defaultValue
}

/**
 * 安全地将值转换为整数
 *
 * @param value - 要转换的值
 * @param defaultValue - 转换失败时的默认值
 * @returns 转换后的整数或默认值
 *
 * @example
 * safeParseInt("123") // 123
 * safeParseInt("123.45") // 123
 * safeParseInt("") // 0
 * safeParseInt(null) // 0
 */
export function safeParseInt(
  value: string | number | undefined | null,
  defaultValue: number = 0
): number {
  // 如果已经是数字类型且有效整数
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) ? value : defaultValue
  }

  // 如果是字符串且非空
  if (typeof value === 'string' && value.trim() !== '') {
    const trimmed = value.trim()
    const parsed = parseInt(trimmed, 10)

    // 验证转换结果是否为有效整数
    if (Number.isSafeInteger(parsed)) {
      return parsed
    }
  }

  // 默认返回默认值
  return defaultValue
}

/**
 * 验证数值是否有效
 *
 * @param value - 要验证的值
 * @returns 是否为有效数字
 */
export function isValidNumber(value: string | number | undefined | null): boolean {
  return safeParseFloat(value, Number.NaN) !== Number.NaN
}

/**
 * 格式化数字显示
 *
 * @param value - 要格式化的值
 * @param decimals - 小数位数
 * @returns 格式化后的字符串
 *
 * @example
 * formatNumber(1234.5678, 2) // "1,234.57"
 * formatNumber(1234.5678, 4) // "1,234.5678"
 */
export function formatNumber(value: number | undefined | null, decimals: number = 2): string {
  const num = safeParseFloat(value, 0)

  // 使用 Intl.NumberFormat 进行本地化格式化
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num)
}

/**
 * 格式化百分比
 *
 * @param value - 要格式化的值
 * @param decimals - 小数位数
 * @returns 格式化后的字符串
 *
 * @example
 * formatPercentage(0.1234, 2) // "12.34%"
 * formatPercentage(-0.0567, 2) // "-5.67%"
 */
export function formatPercentage(
  value: number | undefined | null,
  decimals: number = 2
): string {
  const num = safeParseFloat(value, 0)

  // 使用 Intl.NumberFormat 进行本地化格式化
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num)
}

// Axios 请求封装

import axios from 'axios'
import { ElMessage } from 'element-plus'

// ========== 环境配置 ==========

/**
 * 是否为开发环境
 */
const isDevelopment = import.meta.env.MODE === 'development'

/**
 * 是否启用详细日志（可通过环境变量 VITE_APP_DEBUG=true 覆盖）
 */
const isDebug = import.meta.env.VITE_APP_DEBUG === 'true' || isDevelopment

/**
 * 日志前缀
 */
const LOG_PREFIX = '[API]'

/**
 * 格式化请求数据为可读字符串
 */
function formatRequestData(data: any): string {
  if (!data) return '(none)'
  if (typeof data === 'string') return data
  if (Object.keys(data).length === 0) return '(empty)'
  return JSON.stringify(data, null, 2)
}

/**
 * 格式化响应数据为可读字符串（限制长度）
 */
function formatResponseData(data: any): string {
  if (!data) return '(none)'
  if (typeof data !== 'object') return String(data)

  const json = JSON.stringify(data)
  if (json.length > 200) {
    return `${json.substring(0, 200)}... (${json.length} chars)`
  }
  return json
}

/**
 * 计算响应耗时（毫秒）
 */
function calculateDuration(startTime: number): number {
  return Date.now() - startTime
}

/**
 * 记录请求日志（仅开发环境）
 */
function logRequest(config: any): void {
  if (!isDebug) return

  const method = (config.method || 'GET').toUpperCase()
  const url = config.url || ''

  console.group(`${LOG_PREFIX} 🚀 ${method} ${url}`)
  console.log('Method:', method)
  console.log('URL:', `${config.baseURL || ''}${url}`)
  console.log('Params:', config.params ? formatRequestData(config.params) : '(none)')
  console.log('Headers:', config.headers)

  if (config.data) {
    try {
      console.log('Body:', formatRequestData(config.data))
    } catch (e) {
      console.log('Body:', '(unable to stringify)')
    }
  }

  console.log('Timeout:', config.timeout + 'ms')
  console.log('Start Time:', new Date().toISOString())
  console.groupEnd()
}

/**
 * 记录响应日志（仅开发环境）
 */
function logResponse(response: any, startTime: number): void {
  if (!isDebug) return

  const duration = calculateDuration(startTime)
  const method = (response.config.method || 'GET').toUpperCase()
  const url = response.config.url || ''
  const status = response.status
  const statusText = response.statusText || ''

  // 根据状态码显示不同颜色
  const statusIcon = status >= 200 && status < 300 ? '✅' : '⚠️'

  console.group(`${LOG_PREFIX} ${statusIcon} ${method} ${url}`)
  console.log('Status:', `${status} ${statusText}`)
  console.log('Duration:', `${duration}ms`)

  // 记录响应头（选择性）
  if (response.headers) {
    const contentType = response.headers['content-type']
    const contentLength = response.headers['content-length']
    console.log('Content-Type:', contentType || '(unknown)')
    console.log('Content-Length:', contentLength ? `${contentLength} bytes` : '(unknown)')
  }

  // 记录响应数据
  try {
    console.log('Response:', formatResponseData(response.data))
  } catch (e) {
    console.log('Response:', '(unable to format)')
  }

  console.groupEnd()
}

/**
 * 记录错误日志
 */
function logError(error: any, startTime?: number): void {
  const duration = startTime ? calculateDuration(startTime) : 0
  const method = error.config?.method?.toUpperCase() || 'UNKNOWN'
  const url = error.config?.url || 'unknown'

  console.group(`${LOG_PREFIX} ❌ ${method} ${url}`)

  if (duration > 0) {
    console.log('Duration:', `${duration}ms (failed)`)
  }

  if (error.response) {
    // 服务器返回了响应
    console.log('Status:', `${error.response.status} ${error.response.statusText || ''}`)
    console.log('Response Data:', error.response.data)

    // 记录响应头
    if (error.response.headers) {
      console.log('Response Headers:', error.response.headers)
    }
  } else if (error.request) {
    // 请求已发送但没有收到响应
    console.log('Error:', 'No response received')
    console.log('Request:', error.request)
  } else {
    // 请求配置错误
    console.log('Error Message:', error.message)
  }

  if (error.code) {
    console.log('Error Code:', error.code)
  }

  console.log('Stack:', error.stack || '(no stack trace)')
  console.groupEnd()
}

// 创建 axios 实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// ========== 请求取消管理 ==========

/**
 * 存储活跃的 AbortController
 * Map key: request signature (e.g., 'GET:/api/v1/market/tickers')
 * Map value: AbortController
 */
const activeControllers = new Map<string, AbortController>()

/**
 * 生成请求签名
 *
 * @param method - HTTP 方法
 * @param url - 请求 URL
 * @param params - URL 参数
 * @returns 请求签名字符串
 */
function getRequestSignature(method: string, url: string, params?: any): string {
  const paramStr = params ? JSON.stringify(params) : ''
  return `${method}:${url}:${paramStr}`
}

/**
 * 取消所有活跃的请求
 */
export function cancelAllRequests(): void {
  if (isDebug) {
    console.log(`${LOG_PREFIX} 🛑 Canceling ${activeControllers.size} active requests`)
  }

  activeControllers.forEach((controller, key) => {
    controller.abort()
    if (isDebug) {
      console.log(`${LOG_PREFIX}   └─ Canceled:`, key)
    }
  })
  activeControllers.clear()
}

/**
 * 取消指定 URL 的所有请求
 *
 * @param urlPattern - URL 匹配模式（部分匹配）
 */
export function cancelRequestsByUrl(urlPattern: string): void {
  if (isDebug) {
    console.log(`${LOG_PREFIX} 🛑 Canceling requests matching: ${urlPattern}`)
  }

  activeControllers.forEach((controller, key) => {
    if (key.includes(urlPattern)) {
      controller.abort()
      if (isDebug) {
        console.log(`${LOG_PREFIX}   └─ Canceled:`, key)
      }
      activeControllers.delete(key)
    }
  })
}

/**
 * 创建带取消功能的配置
 *
 * @param signature - 请求签名
 * @returns 包含 AbortSignal 的请求配置
 */
function createRequestConfig(signature: string): any {
  // 如果存在相同签名的请求，先取消
  if (activeControllers.has(signature)) {
    const existingController = activeControllers.get(signature)!
    existingController.abort()
    if (isDebug) {
      console.log(`${LOG_PREFIX} ⏭️  Cancelled previous request:`, signature)
    }
  }

  // 创建新的 AbortController
  const controller = new AbortController()
  activeControllers.set(signature, controller)

  if (isDebug) {
    console.log(`${LOG_PREFIX} 📝 Active requests: ${activeControllers.size}`)
  }

  return {
    signal: controller.signal
  }
}

// 请求拦截器
service.interceptors.request.use(
  (config: any) => {
    // 生成请求签名
    const signature = getRequestSignature(config.method || 'GET', config.url || '', config.params)

    // 创建带取消功能的配置
    const requestConfig = createRequestConfig(signature)

    // 记录请求开始时间（用于计算响应耗时）
    config.metadata = { startTime: Date.now() }

    // 记录请求日志
    logRequest(config)

    // 将取消信号合并到配置
    return { ...config, ...requestConfig }
  },
  (error: any) => {
    logError(error)
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response: any) => {
    // 获取请求开始时间
    const startTime = response.config.metadata?.startTime

    // 记录响应日志
    logResponse(response, startTime)

    // 直接返回后端数据（FastAPI 直接返回数据，不包装在 {code, message, data} 中）
    return response.data
  },
  (error: any) => {
    // 获取请求开始时间（如果存在）
    const startTime = error.config?.metadata?.startTime

    // 记录错误日志
    logError(error, startTime)

    // 处理请求取消的情况
    if (error.code === 'ERR_CANCELED' || error?.message === 'canceled') {
      console.log('[Request Canceled] Request was canceled')
      // 不显示错误提示，直接返回
      return Promise.reject(error)
    }

    let message = '请求失败'

    if (error.response) {
      // 服务器返回错误
      const data = error.response.data as any

      // FastAPI HTTPException 格式
      if (data.detail) {
        message = typeof data.detail === 'string' ? data.detail : '请求失败'
      } else {
        // 其他格式
        switch (error.response.status) {
          case 400:
            message = '请求参数错误'
            break
          case 401:
            message = '未授权，请重新登录'
            break
          case 403:
            message = '拒绝访问'
            break
          case 404:
            message = '请求资源不存在'
            break
          case 409:
            message = '资源已存在'
            break
          case 500:
          case 503:
            message = '服务器内部错误'
            break
          default:
            message = data.message || message
        }
      }
    } else if (error.request) {
      // 请求已发送但没有收到响应
      message = '网络错误，请检查网络连接'
    } else {
      // 请求配置错误
      message = error.message
    }

    ElMessage.error(message)
    return Promise.reject(error)
  }
)

// 导出 axios 实例
export default service

// 导出类型
export type { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios'

/**
 * 检查错误是否为取消状态
 */
export const isCancel = (error: any): boolean => {
  return error?.code === 'ERR_CANCELED' || error?.message === 'canceled'
}

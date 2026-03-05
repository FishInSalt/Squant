import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types'

// 创建 axios 实例
const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 可以在这里添加 token 等认证信息
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    const data = response.data as ApiResponse
    // 后端成功响应: { code: 0, message: "success", data: T }
    // 非0 code 表示业务错误
    if (data.code !== undefined && data.code !== 0) {
      ElMessage.error(data.message || '请求失败')
      return Promise.reject(new Error(data.message))
    }
    return response.data
  },
  (error: AxiosError<ApiResponse>) => {
    let message = '网络错误，请稍后重试'

    if (error.response) {
      const status = error.response.status
      const data = error.response.data
      const dataMsg = (data && typeof data === 'object' && 'message' in data) ? data.message : undefined

      switch (status) {
        case 400:
          message = dataMsg || '请求参数错误'
          break
        case 401:
          message = '未授权，请重新登录'
          break
        case 403:
          message = '拒绝访问'
          break
        case 404:
          message = dataMsg || '请求的资源不存在'
          break
        case 409:
          // 409 由业务代码自行处理提示（如名称冲突），拦截器不弹 toast
          return Promise.reject(error)
        case 500:
          message = '服务器内部错误'
          break
        case 502:
          message = '网关错误'
          break
        case 503:
          message = '服务不可用'
          break
        default:
          message = dataMsg || `请求失败 (${status})`
      }
    } else if (error.code === 'ECONNABORTED') {
      message = '请求超时，请稍后重试'
    }

    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default api

// 导出便捷方法
export const get = <T>(
  url: string,
  params?: Record<string, unknown>,
  config?: { timeout?: number },
) =>
  api.get<unknown, ApiResponse<T>>(url, { params, ...config })

export const post = <T>(url: string, data?: unknown) =>
  api.post<unknown, ApiResponse<T>>(url, data)

export const put = <T>(url: string, data?: unknown) =>
  api.put<unknown, ApiResponse<T>>(url, data)

export const del = <T>(url: string, params?: Record<string, unknown>) =>
  api.delete<unknown, ApiResponse<T>>(url, { params })

export const upload = <T>(url: string, file: File, onProgress?: (percent: number) => void) => {
  const formData = new FormData()
  formData.append('file', file)

  return api.post<unknown, ApiResponse<T>>(url, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total && onProgress) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    },
  })
}

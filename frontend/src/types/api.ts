// API 响应类型
export interface ApiResponse<T = unknown> {
  success: boolean
  data: T
  message?: string
  error?: string
}

export interface PaginatedData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PaginatedResponse<T> extends ApiResponse<PaginatedData<T>> {}

// 通用错误
export interface ApiError {
  code: string
  message: string
  details?: Record<string, unknown>
}

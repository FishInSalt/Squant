// API 响应类型 — 匹配后端 ApiResponse[T]
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface PaginatedData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PaginatedResponse<T> extends ApiResponse<PaginatedData<T>> {}

// 通用错误
export interface ApiError {
  code: string
  message: string
  details?: Record<string, unknown>
}

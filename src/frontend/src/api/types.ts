// API 类型定义

export interface PaginationParams {
  page?: number
  pageSize?: number
}

export interface PaginationResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

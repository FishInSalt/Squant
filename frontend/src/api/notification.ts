import { get, post, del } from './index'
import type { NotificationRecord, UnreadCount, PaginatedData } from '@/types'

// 获取通知列表
export const getNotifications = (params?: {
  page?: number
  page_size?: number
  level?: string
  is_read?: boolean
  event_type?: string
}) => get<PaginatedData<NotificationRecord>>('/notifications', params)

// 获取未读数量
export const getUnreadCount = () =>
  get<UnreadCount>('/notifications/unread-count')

// 标记已读
export const markRead = (notificationIds?: string[]) =>
  post<{ updated: number }>('/notifications/mark-read', {
    notification_ids: notificationIds ?? null,
  })

// 删除通知
export const deleteNotification = (id: string) =>
  del<void>(`/notifications/${id}`)

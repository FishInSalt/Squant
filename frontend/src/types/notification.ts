// 告警通知类型

export type NotificationLevel = 'critical' | 'warning' | 'info'

export interface NotificationRecord {
  id: string
  level: NotificationLevel
  event_type: string
  title: string
  message: string
  details: Record<string, unknown>
  run_id?: string
  status: string
  is_read: boolean
  created_at: string
  updated_at: string
}

export interface UnreadCount {
  count: number
}

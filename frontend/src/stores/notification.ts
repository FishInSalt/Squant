import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElNotification } from 'element-plus'
import type { NotificationRecord } from '@/types'
import { getNotifications, getUnreadCount, markRead } from '@/api/notification'

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<NotificationRecord[]>([])
  const unreadCount = ref(0)
  const loading = ref(false)
  const total = ref(0)

  async function loadUnreadCount() {
    try {
      const resp = await getUnreadCount()
      unreadCount.value = resp.data.count
    } catch {
      // silent
    }
  }

  async function loadNotifications(page = 1, pageSize = 20) {
    loading.value = true
    try {
      const resp = await getNotifications({ page, page_size: pageSize })
      notifications.value = resp.data.items
      total.value = resp.data.total
    } catch {
      // silent
    } finally {
      loading.value = false
    }
  }

  function handleRealtimeNotification(data: NotificationRecord) {
    // Prepend to list
    notifications.value.unshift(data)
    unreadCount.value++

    // Toast for critical/warning
    if (data.level === 'critical') {
      ElNotification.error({
        title: data.title,
        message: data.message,
        duration: 0, // don't auto-close
      })
    } else if (data.level === 'warning') {
      ElNotification.warning({
        title: data.title,
        message: data.message,
        duration: 5000,
      })
    }
  }

  async function markAllRead() {
    try {
      await markRead()
      notifications.value.forEach((n) => { n.is_read = true })
      unreadCount.value = 0
    } catch {
      // silent
    }
  }

  async function markAsRead(ids: string[]) {
    try {
      await markRead(ids)
      notifications.value.forEach((n) => {
        if (ids.includes(n.id)) n.is_read = true
      })
      unreadCount.value = Math.max(0, unreadCount.value - ids.length)
    } catch {
      // silent
    }
  }

  return {
    notifications,
    unreadCount,
    loading,
    total,
    loadUnreadCount,
    loadNotifications,
    handleRealtimeNotification,
    markAllRead,
    markAsRead,
  }
})

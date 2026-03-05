import { setActivePinia, createPinia } from 'pinia'
import { ElNotification } from 'element-plus'
import { useNotificationStore } from './notification'
import * as notificationApi from '@/api/notification'
import type { NotificationRecord } from '@/types'

vi.mock('@/api/notification')

const mockedApi = vi.mocked(notificationApi)

function createMockNotification(overrides: Partial<NotificationRecord> = {}): NotificationRecord {
  return {
    id: 'n-001',
    level: 'critical',
    event_type: 'engine_crashed',
    title: 'Engine Crashed',
    message: 'Something went wrong',
    details: {},
    status: 'pending',
    is_read: false,
    created_at: '2026-03-04T12:00:00Z',
    updated_at: '2026-03-04T12:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useNotificationStore', () => {
  describe('initial state', () => {
    it('has default values', () => {
      const store = useNotificationStore()
      expect(store.notifications).toEqual([])
      expect(store.unreadCount).toBe(0)
      expect(store.loading).toBe(false)
      expect(store.total).toBe(0)
    })
  })

  describe('loadUnreadCount', () => {
    it('updates count from API', async () => {
      mockedApi.getUnreadCount.mockResolvedValue({ data: { count: 5 } } as any)
      const store = useNotificationStore()

      await store.loadUnreadCount()

      expect(store.unreadCount).toBe(5)
      expect(mockedApi.getUnreadCount).toHaveBeenCalledOnce()
    })

    it('handles error silently', async () => {
      mockedApi.getUnreadCount.mockRejectedValue(new Error('Network error'))
      const store = useNotificationStore()

      await store.loadUnreadCount()

      expect(store.unreadCount).toBe(0) // unchanged
    })
  })

  describe('loadNotifications', () => {
    it('updates notifications and total', async () => {
      const items = [createMockNotification({ id: 'n-1' }), createMockNotification({ id: 'n-2' })]
      mockedApi.getNotifications.mockResolvedValue({
        data: { items, total: 10, page: 1, page_size: 20 },
      } as any)

      const store = useNotificationStore()
      await store.loadNotifications()

      expect(store.notifications).toEqual(items)
      expect(store.total).toBe(10)
    })

    it('sets loading state', async () => {
      mockedApi.getNotifications.mockResolvedValue({
        data: { items: [], total: 0, page: 1, page_size: 20 },
      } as any)

      const store = useNotificationStore()
      const promise = store.loadNotifications()

      // loading should be true while request is pending
      expect(store.loading).toBe(true)
      await promise
      expect(store.loading).toBe(false)
    })
  })

  describe('handleRealtimeNotification', () => {
    it('prepends notification and increments unreadCount', () => {
      const store = useNotificationStore()
      store.notifications = [createMockNotification({ id: 'old' })]
      store.unreadCount = 1

      const newNotif = createMockNotification({ id: 'new' })
      store.handleRealtimeNotification(newNotif)

      expect(store.notifications[0].id).toBe('new')
      expect(store.notifications.length).toBe(2)
      expect(store.unreadCount).toBe(2)
    })

    it('shows error toast for critical level', () => {
      const store = useNotificationStore()
      store.handleRealtimeNotification(
        createMockNotification({ level: 'critical', title: 'Crash', message: 'Engine down' }),
      )

      expect(ElNotification.error).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Crash',
          message: 'Engine down',
          duration: 0,
        }),
      )
    })

    it('shows warning toast for warning level', () => {
      const store = useNotificationStore()
      store.handleRealtimeNotification(
        createMockNotification({ level: 'warning', title: 'Mismatch', message: 'Position diff' }),
      )

      expect(ElNotification.warning).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Mismatch',
          message: 'Position diff',
          duration: 5000,
        }),
      )
    })

    it('does not show toast for info level', () => {
      const store = useNotificationStore()
      store.handleRealtimeNotification(createMockNotification({ level: 'info' }))

      expect(ElNotification.error).not.toHaveBeenCalled()
      expect(ElNotification.warning).not.toHaveBeenCalled()
    })
  })

  describe('markAllRead', () => {
    it('marks all notifications as read and resets count', async () => {
      mockedApi.markRead.mockResolvedValue({ data: { updated: 3 } } as any)
      const store = useNotificationStore()
      store.notifications = [
        createMockNotification({ id: 'n-1', is_read: false }),
        createMockNotification({ id: 'n-2', is_read: false }),
      ]
      store.unreadCount = 2

      await store.markAllRead()

      expect(store.notifications.every((n) => n.is_read)).toBe(true)
      expect(store.unreadCount).toBe(0)
      expect(mockedApi.markRead).toHaveBeenCalledOnce()
    })
  })

  describe('markAsRead', () => {
    it('marks specific ids and decrements count', async () => {
      mockedApi.markRead.mockResolvedValue({ data: { updated: 1 } } as any)
      const store = useNotificationStore()
      store.notifications = [
        createMockNotification({ id: 'n-1', is_read: false }),
        createMockNotification({ id: 'n-2', is_read: false }),
      ]
      store.unreadCount = 2

      await store.markAsRead(['n-1'])

      expect(store.notifications[0].is_read).toBe(true)
      expect(store.notifications[1].is_read).toBe(false)
      expect(store.unreadCount).toBe(1)
      expect(mockedApi.markRead).toHaveBeenCalledWith(['n-1'])
    })
  })
})

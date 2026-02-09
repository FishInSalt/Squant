import { ElNotification, ElMessage, ElMessageBox } from 'element-plus'
import type { NotificationParams, MessageParams, ElMessageBoxOptions } from 'element-plus'

type NotificationType = 'success' | 'warning' | 'info' | 'error'

interface NotifyOptions {
  title?: string
  message: string
  type?: NotificationType
  duration?: number
  showClose?: boolean
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left'
}

interface ToastOptions {
  message: string
  type?: NotificationType
  duration?: number
  showClose?: boolean
}

interface ConfirmOptions {
  title?: string
  message: string
  type?: 'warning' | 'info' | 'success' | 'error'
  confirmText?: string
  cancelText?: string
  dangerouslyUseHTMLString?: boolean
}

export function useNotification() {
  // 通知
  function notify(options: NotifyOptions | string) {
    const opts: NotificationParams =
      typeof options === 'string'
        ? { message: options }
        : {
            title: options.title,
            message: options.message,
            type: options.type || 'info',
            duration: options.duration ?? 4500,
            showClose: options.showClose ?? true,
            position: options.position || 'top-right',
          }

    return ElNotification(opts)
  }

  function notifySuccess(message: string, title = '成功') {
    return notify({ title, message, type: 'success' })
  }

  function notifyWarning(message: string, title = '警告') {
    return notify({ title, message, type: 'warning' })
  }

  function notifyError(message: string, title = '错误') {
    return notify({ title, message, type: 'error' })
  }

  function notifyInfo(message: string, title = '提示') {
    return notify({ title, message, type: 'info' })
  }

  // Toast 消息
  function toast(options: ToastOptions | string) {
    const opts: MessageParams =
      typeof options === 'string'
        ? { message: options }
        : {
            message: options.message,
            type: options.type || 'info',
            duration: options.duration ?? 3000,
            showClose: options.showClose ?? false,
          }

    return ElMessage(opts)
  }

  function toastSuccess(message: string) {
    return toast({ message, type: 'success' })
  }

  function toastWarning(message: string) {
    return toast({ message, type: 'warning' })
  }

  function toastError(message: string) {
    return toast({ message, type: 'error' })
  }

  function toastInfo(message: string) {
    return toast({ message, type: 'info' })
  }

  // 确认对话框
  async function confirm(options: ConfirmOptions): Promise<boolean> {
    const opts: ElMessageBoxOptions = {
      title: options.title || '确认',
      message: options.message,
      type: options.type || 'warning',
      confirmButtonText: options.confirmText || '确定',
      cancelButtonText: options.cancelText || '取消',
      showCancelButton: true,
      dangerouslyUseHTMLString: options.dangerouslyUseHTMLString,
    }

    try {
      await ElMessageBox.confirm(options.message, options.title || '确认', opts)
      return true
    } catch {
      return false
    }
  }

  // 危险操作确认
  async function confirmDanger(message: string, title = '危险操作'): Promise<boolean> {
    return confirm({
      title,
      message,
      type: 'error',
      confirmText: '确认执行',
    })
  }

  // 删除确认
  async function confirmDelete(itemName = '此项'): Promise<boolean> {
    return confirm({
      title: '删除确认',
      message: `确定要删除${itemName}吗？此操作不可恢复。`,
      type: 'warning',
      confirmText: '删除',
    })
  }

  // 输入对话框
  async function prompt(
    message: string,
    title = '请输入',
    defaultValue = ''
  ): Promise<string | null> {
    try {
      const result = await ElMessageBox.prompt(message, title, {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: defaultValue,
      })
      // ElMessageBox.prompt returns { value: string, action: string }
      return (result as { value: string }).value
    } catch {
      return null
    }
  }

  return {
    notify,
    notifySuccess,
    notifyWarning,
    notifyError,
    notifyInfo,
    toast,
    toastSuccess,
    toastWarning,
    toastError,
    toastInfo,
    confirm,
    confirmDanger,
    confirmDelete,
    prompt,
  }
}

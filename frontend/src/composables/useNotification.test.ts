import { ElNotification, ElMessage, ElMessageBox } from 'element-plus'
import { useNotification } from './useNotification'

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<typeof import('element-plus')>('element-plus')
  return {
    ...actual,
    ElNotification: vi.fn(),
    ElMessage: vi.fn(),
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue('confirm'),
      prompt: vi.fn().mockResolvedValue({ value: 'input', action: 'confirm' }),
    },
  }
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useNotification', () => {
  describe('notify', () => {
    it('calls ElNotification with string message', () => {
      const { notify } = useNotification()
      notify('hello')
      expect(ElNotification).toHaveBeenCalledWith({ message: 'hello' })
    })

    it('calls ElNotification with options object', () => {
      const { notify } = useNotification()
      notify({ title: 'Title', message: 'body', type: 'success', duration: 3000 })
      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Title',
          message: 'body',
          type: 'success',
          duration: 3000,
        })
      )
    })

    it('uses default type info and duration 4500', () => {
      const { notify } = useNotification()
      notify({ message: 'test' })
      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'info', duration: 4500 })
      )
    })
  })

  describe('notify variants', () => {
    it('notifySuccess calls with type success', () => {
      const { notifySuccess } = useNotification()
      notifySuccess('done')
      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'success', message: 'done', title: '成功' })
      )
    })

    it('notifyWarning calls with type warning', () => {
      const { notifyWarning } = useNotification()
      notifyWarning('warn')
      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'warning', title: '警告' })
      )
    })

    it('notifyError calls with type error', () => {
      const { notifyError } = useNotification()
      notifyError('oops')
      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error', title: '错误' })
      )
    })

    it('notifyInfo calls with type info', () => {
      const { notifyInfo } = useNotification()
      notifyInfo('fyi')
      expect(ElNotification).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'info', title: '提示' })
      )
    })
  })

  describe('toast', () => {
    it('calls ElMessage with string', () => {
      const { toast } = useNotification()
      toast('hi')
      expect(ElMessage).toHaveBeenCalledWith({ message: 'hi' })
    })

    it('calls ElMessage with options', () => {
      const { toast } = useNotification()
      toast({ message: 'msg', type: 'error', duration: 1000 })
      expect(ElMessage).toHaveBeenCalledWith(
        expect.objectContaining({ message: 'msg', type: 'error', duration: 1000 })
      )
    })
  })

  describe('toast variants', () => {
    it('toastSuccess', () => {
      const { toastSuccess } = useNotification()
      toastSuccess('yay')
      expect(ElMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'success', message: 'yay' })
      )
    })

    it('toastWarning', () => {
      const { toastWarning } = useNotification()
      toastWarning('careful')
      expect(ElMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'warning' })
      )
    })

    it('toastError', () => {
      const { toastError } = useNotification()
      toastError('bad')
      expect(ElMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'error' })
      )
    })

    it('toastInfo', () => {
      const { toastInfo } = useNotification()
      toastInfo('note')
      expect(ElMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'info' })
      )
    })
  })

  describe('confirm', () => {
    it('returns true on confirmation', async () => {
      const { confirm } = useNotification()
      const result = await confirm({ message: 'Sure?' })
      expect(result).toBe(true)
      expect(ElMessageBox.confirm).toHaveBeenCalled()
    })

    it('returns false on cancel', async () => {
      vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
      const { confirm } = useNotification()
      const result = await confirm({ message: 'Sure?' })
      expect(result).toBe(false)
    })
  })

  describe('confirmDanger', () => {
    it('calls confirm with error type', async () => {
      const { confirmDanger } = useNotification()
      await confirmDanger('Delete everything?')
      expect(ElMessageBox.confirm).toHaveBeenCalledWith(
        'Delete everything?',
        '危险操作',
        expect.objectContaining({ type: 'error' })
      )
    })
  })

  describe('confirmDelete', () => {
    it('calls confirm with delete message', async () => {
      const { confirmDelete } = useNotification()
      await confirmDelete('此策略')
      expect(ElMessageBox.confirm).toHaveBeenCalledWith(
        expect.stringContaining('此策略'),
        '删除确认',
        expect.objectContaining({ type: 'warning' })
      )
    })

    it('uses default item name', async () => {
      const { confirmDelete } = useNotification()
      await confirmDelete()
      expect(ElMessageBox.confirm).toHaveBeenCalledWith(
        expect.stringContaining('此项'),
        '删除确认',
        expect.anything()
      )
    })
  })

  describe('prompt', () => {
    it('returns input value on confirm', async () => {
      const { prompt } = useNotification()
      const result = await prompt('Enter name')
      expect(result).toBe('input')
      expect(ElMessageBox.prompt).toHaveBeenCalled()
    })

    it('returns null on cancel', async () => {
      vi.mocked(ElMessageBox.prompt).mockRejectedValueOnce('cancel')
      const { prompt } = useNotification()
      const result = await prompt('Enter name')
      expect(result).toBeNull()
    })
  })
})

import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { usePolling, useConditionalPolling } from './usePolling'

// Helper to mount a composable within a real component
function withSetup<T>(composableFn: () => T): { result: T; unmount: () => void } {
  let result!: T
  const Comp = defineComponent({
    setup() {
      result = composableFn()
      return () => null
    },
  })
  const wrapper = mount(Comp)
  return { result, unmount: () => wrapper.unmount() }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('usePolling', () => {
  describe('initial state', () => {
    it('has default values', () => {
      const fetchFn = vi.fn().mockResolvedValue('data')
      const { result } = withSetup(() => usePolling(fetchFn, { autoStart: false }))
      expect(result.data.value).toBeNull()
      expect(result.loading.value).toBe(false)
      expect(result.error.value).toBeNull()
      expect(result.isPolling.value).toBe(false)
    })
  })

  describe('autoStart', () => {
    it('starts polling on mount when autoStart is true', async () => {
      const fetchFn = vi.fn().mockResolvedValue('result')
      const { result, unmount } = withSetup(() => usePolling(fetchFn, { autoStart: true }))
      await flushPromises()
      expect(fetchFn).toHaveBeenCalledTimes(1)
      expect(result.data.value).toBe('result')
      expect(result.isPolling.value).toBe(true)
      unmount()
    })

    it('does not start polling when autoStart is false', () => {
      const fetchFn = vi.fn().mockResolvedValue('data')
      const { result } = withSetup(() => usePolling(fetchFn, { autoStart: false }))
      expect(fetchFn).not.toHaveBeenCalled()
      expect(result.isPolling.value).toBe(false)
    })
  })

  describe('manual start / stop', () => {
    it('start() begins polling', async () => {
      const fetchFn = vi.fn().mockResolvedValue('value')
      const { result, unmount } = withSetup(() =>
        usePolling(fetchFn, { autoStart: false, immediate: true })
      )
      expect(result.isPolling.value).toBe(false)
      result.start()
      await flushPromises()
      expect(result.isPolling.value).toBe(true)
      expect(result.data.value).toBe('value')
      unmount()
    })

    it('stop() clears polling', async () => {
      const fetchFn = vi.fn().mockResolvedValue('data')
      const { result, unmount } = withSetup(() =>
        usePolling(fetchFn, { autoStart: false, immediate: true })
      )
      result.start()
      await flushPromises()
      result.stop()
      expect(result.isPolling.value).toBe(false)
      unmount()
    })

    it('start() is no-op when already polling', async () => {
      const fetchFn = vi.fn().mockResolvedValue('data')
      const { result, unmount } = withSetup(() =>
        usePolling(fetchFn, { autoStart: false, immediate: true })
      )
      result.start()
      await flushPromises()
      result.start() // second call is no-op
      expect(fetchFn).toHaveBeenCalledTimes(1)
      unmount()
    })
  })

  describe('refresh', () => {
    it('fetches data on demand', async () => {
      const fetchFn = vi.fn().mockResolvedValue('refreshed')
      const { result } = withSetup(() => usePolling(fetchFn, { autoStart: false }))
      await result.refresh()
      expect(result.data.value).toBe('refreshed')
    })
  })

  describe('error handling', () => {
    it('sets error on fetch failure after retries', async () => {
      const fetchFn = vi.fn().mockRejectedValue(new Error('network'))
      const { result } = withSetup(() =>
        usePolling(fetchFn, { autoStart: false, retries: 0, retryDelay: 0 })
      )
      await result.refresh()
      expect(result.error.value).toBeInstanceOf(Error)
      expect(result.error.value!.message).toBe('network')
    })

    it('retries on failure before giving up', async () => {
      const fetchFn = vi
        .fn()
        .mockRejectedValueOnce(new Error('fail1'))
        .mockRejectedValueOnce(new Error('fail2'))
        .mockResolvedValue('success')
      const { result } = withSetup(() =>
        usePolling(fetchFn, { autoStart: false, retries: 3, retryDelay: 10 })
      )
      const promise = result.refresh()
      // Advance timers for retry delays
      await vi.advanceTimersByTimeAsync(100)
      await promise
      expect(result.data.value).toBe('success')
      expect(fetchFn).toHaveBeenCalledTimes(3)
    })

    it('wraps non-Error throwables', async () => {
      const fetchFn = vi.fn().mockRejectedValue('string error')
      const { result } = withSetup(() =>
        usePolling(fetchFn, { autoStart: false, retries: 0, retryDelay: 0 })
      )
      await result.refresh()
      expect(result.error.value).toBeInstanceOf(Error)
      expect(result.error.value!.message).toBe('string error')
    })
  })

  describe('unmount cleanup', () => {
    it('stops polling on unmount', async () => {
      const fetchFn = vi.fn().mockResolvedValue('data')
      const { result, unmount } = withSetup(() => usePolling(fetchFn, { autoStart: true }))
      await flushPromises()
      expect(result.isPolling.value).toBe(true)
      unmount()
      expect(result.isPolling.value).toBe(false)
    })
  })
})

describe('useConditionalPolling', () => {
  it('stops when condition is met', async () => {
    let callCount = 0
    const fetchFn = vi.fn().mockImplementation(async () => {
      callCount++
      return callCount >= 2 ? 'done' : 'pending'
    })
    const shouldStop = (data: string) => data === 'done'
    const { result, unmount } = withSetup(() =>
      useConditionalPolling(fetchFn, shouldStop, { autoStart: false, immediate: true })
    )
    result.start()
    await flushPromises()
    // First call returns 'pending', should not stop
    expect(result.isPolling.value).toBe(true)

    // Simulate next poll via refresh
    await result.refresh()
    // Second call returns 'done', should stop
    expect(result.isPolling.value).toBe(false)
    expect(result.data.value).toBe('done')
    unmount()
  })
})

import { ref, onMounted, onUnmounted, type Ref } from 'vue'

interface UsePollingOptions {
  // 轮询间隔 (毫秒)
  interval?: number
  // 是否立即执行
  immediate?: boolean
  // 是否自动开始
  autoStart?: boolean
  // 失败重试次数
  retries?: number
  // 失败后的延迟 (毫秒)
  retryDelay?: number
}

interface UsePollingReturn<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<Error | null>
  isPolling: Ref<boolean>
  start: () => void
  stop: () => void
  refresh: () => Promise<void>
}

export function usePolling<T>(
  fetchFn: () => Promise<T>,
  options: UsePollingOptions = {}
): UsePollingReturn<T> {
  const {
    interval = 5000,
    immediate = true,
    autoStart = true,
    retries = 3,
    retryDelay = 1000,
  } = options

  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<Error | null>(null)
  const isPolling = ref(false)

  let timer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0

  async function fetch() {
    loading.value = true
    error.value = null

    try {
      data.value = await fetchFn()
      retryCount = 0
    } catch (e) {
      error.value = e instanceof Error ? e : new Error(String(e))

      if (retryCount < retries) {
        retryCount++
        await new Promise((resolve) => setTimeout(resolve, retryDelay))
        // Recurse and return early so that loading.value = false
        // is only executed once by the innermost successful call
        // (or the outermost call after retries are exhausted).
        await fetch()
        return
      }
    }
    loading.value = false
  }

  function scheduleNext() {
    if (!isPolling.value) return

    timer = setTimeout(async () => {
      retryCount = 0
      await fetch()
      scheduleNext()
    }, interval)
  }

  function start() {
    if (isPolling.value) return

    isPolling.value = true

    if (immediate) {
      fetch().then(() => {
        scheduleNext()
      })
    } else {
      scheduleNext()
    }
  }

  function stop() {
    isPolling.value = false
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  async function refresh() {
    await fetch()
  }

  onMounted(() => {
    if (autoStart) {
      start()
    }
  })

  onUnmounted(() => {
    stop()
  })

  return {
    data,
    loading,
    error,
    isPolling,
    start,
    stop,
    refresh,
  }
}

// 条件轮询 - 当条件满足时停止
export function useConditionalPolling<T>(
  fetchFn: () => Promise<T>,
  shouldStop: (data: T) => boolean,
  options: UsePollingOptions = {}
) {
  const polling = usePolling(fetchFn, {
    ...options,
    autoStart: false,
  })

  const originalFetch = polling.refresh

  polling.refresh = async () => {
    await originalFetch()
    if (polling.data.value && shouldStop(polling.data.value)) {
      polling.stop()
    }
  }

  if (options.autoStart !== false) {
    polling.start()
  }

  return polling
}

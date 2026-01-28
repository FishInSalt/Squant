import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { BacktestRun, PaperSession, LiveSession } from '@/types'
import * as backtestApi from '@/api/backtest'
import * as paperApi from '@/api/paper'
import * as liveApi from '@/api/live'

export const useTradingStore = defineStore('trading', () => {
  // State
  const runningBacktests = ref<BacktestRun[]>([])
  const runningPaperSessions = ref<PaperSession[]>([])
  const runningLiveSessions = ref<LiveSession[]>([])
  const currentBacktest = ref<BacktestRun | null>(null)
  const currentPaperSession = ref<PaperSession | null>(null)
  const currentLiveSession = ref<LiveSession | null>(null)
  const loading = ref(false)

  // Getters
  const totalRunningSessions = computed(
    () =>
      runningBacktests.value.length +
      runningPaperSessions.value.length +
      runningLiveSessions.value.length
  )

  const hasRunningLive = computed(() => runningLiveSessions.value.length > 0)

  // Actions
  async function loadRunningBacktests() {
    try {
      const response = await backtestApi.getRunningBacktests()
      runningBacktests.value = response.data.items
    } catch (error) {
      console.error('Failed to load running backtests:', error)
    }
  }

  async function loadRunningPaperSessions() {
    try {
      const response = await paperApi.getRunningPaperSessions()
      runningPaperSessions.value = response.data
    } catch (error) {
      console.error('Failed to load running paper sessions:', error)
    }
  }

  async function loadRunningLiveSessions() {
    try {
      const response = await liveApi.getRunningLiveSessions()
      runningLiveSessions.value = response.data
    } catch (error) {
      console.error('Failed to load running live sessions:', error)
    }
  }

  async function loadAllRunningSessions() {
    loading.value = true
    try {
      await Promise.all([
        loadRunningBacktests(),
        loadRunningPaperSessions(),
        loadRunningLiveSessions(),
      ])
    } finally {
      loading.value = false
    }
  }

  async function loadBacktest(id: string) {
    loading.value = true
    try {
      const response = await backtestApi.getBacktestStatus(id)
      currentBacktest.value = response.data
      return response.data
    } catch (error) {
      console.error('Failed to load backtest:', error)
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadPaperSession(id: string) {
    loading.value = true
    try {
      const response = await paperApi.getPaperSession(id)
      currentPaperSession.value = response.data
      return response.data
    } catch (error) {
      console.error('Failed to load paper session:', error)
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadLiveSession(id: string) {
    loading.value = true
    try {
      const response = await liveApi.getLiveSession(id)
      currentLiveSession.value = response.data
      return response.data
    } catch (error) {
      console.error('Failed to load live session:', error)
      return null
    } finally {
      loading.value = false
    }
  }

  function updateBacktest(backtest: BacktestRun) {
    const index = runningBacktests.value.findIndex((b) => b.id === backtest.id)
    if (backtest.status === 'running') {
      if (index === -1) {
        runningBacktests.value.push(backtest)
      } else {
        runningBacktests.value[index] = backtest
      }
    } else {
      if (index !== -1) {
        runningBacktests.value.splice(index, 1)
      }
    }
    if (currentBacktest.value?.id === backtest.id) {
      currentBacktest.value = backtest
    }
  }

  function updatePaperSession(session: PaperSession) {
    const index = runningPaperSessions.value.findIndex((s) => s.id === session.id)
    if (session.status === 'running') {
      if (index === -1) {
        runningPaperSessions.value.push(session)
      } else {
        runningPaperSessions.value[index] = session
      }
    } else {
      if (index !== -1) {
        runningPaperSessions.value.splice(index, 1)
      }
    }
    if (currentPaperSession.value?.id === session.id) {
      currentPaperSession.value = session
    }
  }

  function updateLiveSession(session: LiveSession) {
    const index = runningLiveSessions.value.findIndex((s) => s.id === session.id)
    if (session.status === 'running') {
      if (index === -1) {
        runningLiveSessions.value.push(session)
      } else {
        runningLiveSessions.value[index] = session
      }
    } else {
      if (index !== -1) {
        runningLiveSessions.value.splice(index, 1)
      }
    }
    if (currentLiveSession.value?.id === session.id) {
      currentLiveSession.value = session
    }
  }

  function clearCurrentSessions() {
    currentBacktest.value = null
    currentPaperSession.value = null
    currentLiveSession.value = null
  }

  return {
    // State
    runningBacktests,
    runningPaperSessions,
    runningLiveSessions,
    currentBacktest,
    currentPaperSession,
    currentLiveSession,
    loading,
    // Getters
    totalRunningSessions,
    hasRunningLive,
    // Actions
    loadRunningBacktests,
    loadRunningPaperSessions,
    loadRunningLiveSessions,
    loadAllRunningSessions,
    loadBacktest,
    loadPaperSession,
    loadLiveSession,
    updateBacktest,
    updatePaperSession,
    updateLiveSession,
    clearCurrentSessions,
  }
})

import { setActivePinia, createPinia } from 'pinia'
import { useTradingStore } from './trading'
import {
  createMockBacktestRun,
  createMockPaperSession,
  createMockLiveSession,
  wrapApiResponse,
  wrapPaginatedResponse,
} from '@/__tests__/fixtures'
import * as backtestApi from '@/api/backtest'
import * as paperApi from '@/api/paper'
import * as liveApi from '@/api/live'

vi.mock('@/api/backtest')
vi.mock('@/api/paper')
vi.mock('@/api/live')

const mockedBacktest = vi.mocked(backtestApi)
const mockedPaper = vi.mocked(paperApi)
const mockedLive = vi.mocked(liveApi)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useTradingStore', () => {
  describe('initial state', () => {
    it('has empty arrays and null sessions', () => {
      const store = useTradingStore()
      expect(store.runningBacktests).toEqual([])
      expect(store.runningPaperSessions).toEqual([])
      expect(store.runningLiveSessions).toEqual([])
      expect(store.currentBacktest).toBeNull()
      expect(store.currentPaperSession).toBeNull()
      expect(store.currentLiveSession).toBeNull()
      expect(store.loading).toBe(false)
    })
  })

  describe('totalRunningSessions', () => {
    it('sums all running arrays', () => {
      const store = useTradingStore()
      store.runningBacktests = [createMockBacktestRun({ status: 'running' })]
      store.runningPaperSessions = [createMockPaperSession(), createMockPaperSession({ id: 'paper-2' })]
      expect(store.totalRunningSessions).toBe(3)
    })

    it('returns 0 when nothing running', () => {
      const store = useTradingStore()
      expect(store.totalRunningSessions).toBe(0)
    })
  })

  describe('hasRunningLive', () => {
    it('returns true when live sessions exist', () => {
      const store = useTradingStore()
      store.runningLiveSessions = [createMockLiveSession()]
      expect(store.hasRunningLive).toBe(true)
    })

    it('returns false when no live sessions', () => {
      const store = useTradingStore()
      expect(store.hasRunningLive).toBe(false)
    })
  })

  describe('updateBacktest', () => {
    it('adds running backtest to list', () => {
      const store = useTradingStore()
      const bt = createMockBacktestRun({ id: 'bt-1', status: 'running' })
      store.updateBacktest(bt)
      expect(store.runningBacktests).toHaveLength(1)
    })

    it('updates existing running backtest', () => {
      const store = useTradingStore()
      store.runningBacktests = [createMockBacktestRun({ id: 'bt-1', status: 'running', progress: 0.5 })]
      store.updateBacktest(createMockBacktestRun({ id: 'bt-1', status: 'running', progress: 0.8 }))
      expect(store.runningBacktests).toHaveLength(1)
      expect(store.runningBacktests[0].progress).toBe(0.8)
    })

    it('removes non-running backtest from list', () => {
      const store = useTradingStore()
      store.runningBacktests = [createMockBacktestRun({ id: 'bt-1', status: 'running' })]
      store.updateBacktest(createMockBacktestRun({ id: 'bt-1', status: 'completed' }))
      expect(store.runningBacktests).toHaveLength(0)
    })

    it('updates currentBacktest if matching ID', () => {
      const store = useTradingStore()
      store.currentBacktest = createMockBacktestRun({ id: 'bt-1', progress: 0.5 })
      const updated = createMockBacktestRun({ id: 'bt-1', status: 'completed', progress: 1 })
      store.updateBacktest(updated)
      expect(store.currentBacktest?.status).toBe('completed')
    })
  })

  describe('updatePaperSession', () => {
    it('adds running session', () => {
      const store = useTradingStore()
      store.updatePaperSession(createMockPaperSession({ id: 'p-1', status: 'running' }))
      expect(store.runningPaperSessions).toHaveLength(1)
    })

    it('removes stopped session', () => {
      const store = useTradingStore()
      store.runningPaperSessions = [createMockPaperSession({ id: 'p-1' })]
      store.updatePaperSession(createMockPaperSession({ id: 'p-1', status: 'stopped' }))
      expect(store.runningPaperSessions).toHaveLength(0)
    })

    it('updates currentPaperSession if matching', () => {
      const store = useTradingStore()
      store.currentPaperSession = createMockPaperSession({ id: 'p-1' })
      store.updatePaperSession(createMockPaperSession({ id: 'p-1', status: 'stopped' }))
      expect(store.currentPaperSession?.status).toBe('stopped')
    })
  })

  describe('updateLiveSession', () => {
    it('adds running session', () => {
      const store = useTradingStore()
      store.updateLiveSession(createMockLiveSession({ id: 'l-1', status: 'running' }))
      expect(store.runningLiveSessions).toHaveLength(1)
    })

    it('removes stopped session', () => {
      const store = useTradingStore()
      store.runningLiveSessions = [createMockLiveSession({ id: 'l-1' })]
      store.updateLiveSession(createMockLiveSession({ id: 'l-1', status: 'stopped' }))
      expect(store.runningLiveSessions).toHaveLength(0)
    })
  })

  describe('loadAllRunningSessions', () => {
    it('calls all three load APIs', async () => {
      const store = useTradingStore()
      mockedBacktest.getRunningBacktests.mockResolvedValue(wrapPaginatedResponse([]))
      mockedPaper.getRunningPaperSessions.mockResolvedValue(wrapApiResponse([]))
      mockedLive.getRunningLiveSessions.mockResolvedValue(wrapApiResponse([]))
      await store.loadAllRunningSessions()
      expect(mockedBacktest.getRunningBacktests).toHaveBeenCalled()
      expect(mockedPaper.getRunningPaperSessions).toHaveBeenCalled()
      expect(mockedLive.getRunningLiveSessions).toHaveBeenCalled()
      expect(store.loading).toBe(false)
    })

    it('sets loading during execution', async () => {
      const store = useTradingStore()
      let loadingDuring = false
      mockedBacktest.getRunningBacktests.mockImplementation(async () => {
        loadingDuring = store.loading
        return wrapPaginatedResponse([])
      })
      mockedPaper.getRunningPaperSessions.mockResolvedValue(wrapApiResponse([]))
      mockedLive.getRunningLiveSessions.mockResolvedValue(wrapApiResponse([]))
      await store.loadAllRunningSessions()
      expect(loadingDuring).toBe(true)
    })
  })

  describe('loadBacktest', () => {
    it('sets currentBacktest from API', async () => {
      const store = useTradingStore()
      const bt = createMockBacktestRun({ id: 'bt-1' })
      mockedBacktest.getBacktestStatus.mockResolvedValue(wrapApiResponse(bt))
      const result = await store.loadBacktest('bt-1')
      expect(store.currentBacktest).toEqual(bt)
      expect(result).toEqual(bt)
    })

    it('returns null on error', async () => {
      const store = useTradingStore()
      mockedBacktest.getBacktestStatus.mockRejectedValue(new Error('Not found'))
      const result = await store.loadBacktest('missing')
      expect(result).toBeNull()
    })
  })

  describe('clearCurrentSessions', () => {
    it('nulls all current sessions', () => {
      const store = useTradingStore()
      store.currentBacktest = createMockBacktestRun()
      store.currentPaperSession = createMockPaperSession()
      store.currentLiveSession = createMockLiveSession()
      store.clearCurrentSessions()
      expect(store.currentBacktest).toBeNull()
      expect(store.currentPaperSession).toBeNull()
      expect(store.currentLiveSession).toBeNull()
    })
  })
})

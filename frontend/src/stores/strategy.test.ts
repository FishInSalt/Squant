import { setActivePinia, createPinia } from 'pinia'
import { useStrategyStore } from './strategy'
import { createMockStrategy, wrapApiResponse } from '@/__tests__/fixtures'
import type { PaginatedData } from '@/types'
import type { Strategy } from '@/types/strategy'
import * as strategyApi from '@/api/strategy'

vi.mock('@/api/strategy')

const mockedApi = vi.mocked(strategyApi)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useStrategyStore', () => {
  describe('initial state', () => {
    it('has empty strategies and default pagination', () => {
      const store = useStrategyStore()
      expect(store.strategies).toEqual([])
      expect(store.currentStrategy).toBeNull()
      expect(store.pagination.page).toBe(1)
      expect(store.pagination.pageSize).toBe(20)
      expect(store.loading).toBe(false)
    })
  })

  describe('validStrategies', () => {
    it('filters strategies by status active', () => {
      const store = useStrategyStore()
      store.strategies = [
        createMockStrategy({ id: 's-1', status: 'active' }),
        createMockStrategy({ id: 's-2', status: 'archived' }),
        createMockStrategy({ id: 's-3', status: 'active' }),
      ]
      expect(store.validStrategies).toHaveLength(2)
    })

    it('returns empty when none active', () => {
      const store = useStrategyStore()
      store.strategies = [createMockStrategy({ status: 'archived' })]
      expect(store.validStrategies).toHaveLength(0)
    })
  })

  describe('strategyById', () => {
    it('finds strategy by id', () => {
      const store = useStrategyStore()
      store.strategies = [
        createMockStrategy({ id: 's-1', name: 'First' }),
        createMockStrategy({ id: 's-2', name: 'Second' }),
      ]
      expect(store.strategyById('s-2')?.name).toBe('Second')
    })

    it('returns undefined when not found', () => {
      const store = useStrategyStore()
      expect(store.strategyById('missing')).toBeUndefined()
    })
  })

  describe('loadStrategies', () => {
    it('sets strategies and pagination from API', async () => {
      const store = useStrategyStore()
      const data: PaginatedData<Strategy> = {
        items: [createMockStrategy()],
        total: 1,
        page: 1,
        page_size: 20,
      }
      mockedApi.getStrategies.mockResolvedValue(wrapApiResponse(data))
      await store.loadStrategies()
      expect(store.strategies).toHaveLength(1)
      expect(store.pagination.total).toBe(1)
    })

    it('passes params to API', async () => {
      const store = useStrategyStore()
      const data: PaginatedData<Strategy> = { items: [], total: 0, page: 2, page_size: 10 }
      mockedApi.getStrategies.mockResolvedValue(wrapApiResponse(data))
      await store.loadStrategies({ page: 2, pageSize: 10 })
      expect(mockedApi.getStrategies).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2, page_size: 10 })
      )
    })

    it('handles error gracefully', async () => {
      const store = useStrategyStore()
      mockedApi.getStrategies.mockRejectedValue(new Error('fail'))
      await store.loadStrategies()
      expect(store.strategies).toEqual([])
    })
  })

  describe('loadStrategy', () => {
    it('sets currentStrategy from API', async () => {
      const store = useStrategyStore()
      const strategy = createMockStrategy({ id: 's-1' })
      mockedApi.getStrategy.mockResolvedValue(wrapApiResponse(strategy))
      const result = await store.loadStrategy('s-1')
      expect(store.currentStrategy).toEqual(strategy)
      expect(result).toEqual(strategy)
    })

    it('returns null on error', async () => {
      const store = useStrategyStore()
      mockedApi.getStrategy.mockRejectedValue(new Error('Not found'))
      const result = await store.loadStrategy('missing')
      expect(result).toBeNull()
    })
  })

  describe('deleteStrategy', () => {
    it('removes from list and returns true', async () => {
      const store = useStrategyStore()
      store.strategies = [createMockStrategy({ id: 's-1' }), createMockStrategy({ id: 's-2' })]
      mockedApi.deleteStrategy.mockResolvedValue(wrapApiResponse(undefined as unknown as void))
      const result = await store.deleteStrategy('s-1')
      expect(result).toBe(true)
      expect(store.strategies).toHaveLength(1)
      expect(store.strategies[0].id).toBe('s-2')
    })

    it('clears currentStrategy if matching', async () => {
      const store = useStrategyStore()
      store.strategies = [createMockStrategy({ id: 's-1' })]
      store.currentStrategy = createMockStrategy({ id: 's-1' })
      mockedApi.deleteStrategy.mockResolvedValue(wrapApiResponse(undefined as unknown as void))
      await store.deleteStrategy('s-1')
      expect(store.currentStrategy).toBeNull()
    })

    it('returns false on error', async () => {
      const store = useStrategyStore()
      mockedApi.deleteStrategy.mockRejectedValue(new Error('fail'))
      const result = await store.deleteStrategy('s-1')
      expect(result).toBe(false)
    })
  })

  describe('setters', () => {
    it('setPage updates pagination.page', () => {
      const store = useStrategyStore()
      store.setPage(3)
      expect(store.pagination.page).toBe(3)
    })

    it('clearCurrentStrategy nulls currentStrategy', () => {
      const store = useStrategyStore()
      store.currentStrategy = createMockStrategy()
      store.clearCurrentStrategy()
      expect(store.currentStrategy).toBeNull()
    })
  })
})

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Strategy, PaginatedData } from '@/types'
import * as strategyApi from '@/api/strategy'

export const useStrategyStore = defineStore('strategy', () => {
  // State
  const strategies = ref<Strategy[]>([])
  const currentStrategy = ref<Strategy | null>(null)
  const pagination = ref({
    page: 1,
    pageSize: 20,
    total: 0,
  })
  const loading = ref(false)

  // Getters
  const validStrategies = computed(() =>
    strategies.value.filter((s) => s.status === 'active')
  )

  const strategyById = computed(() => (id: string) =>
    strategies.value.find((s) => s.id === id)
  )

  // Actions
  async function loadStrategies(params?: {
    page?: number
    pageSize?: number
    status?: string
  }) {
    loading.value = true
    try {
      const response = await strategyApi.getStrategies({
        page: params?.page || pagination.value.page,
        page_size: params?.pageSize || pagination.value.pageSize,
        status: params?.status ?? 'active',
      })
      const data = response.data as PaginatedData<Strategy>
      strategies.value = data.items
      pagination.value = {
        page: data.page,
        pageSize: data.page_size,
        total: data.total,
      }
    } catch (error) {
      console.error('Failed to load strategies:', error)
    } finally {
      loading.value = false
    }
  }

  async function loadStrategy(id: string) {
    loading.value = true
    try {
      const response = await strategyApi.getStrategy(id)
      currentStrategy.value = response.data
      return response.data
    } catch (error) {
      console.error('Failed to load strategy:', error)
      return null
    } finally {
      loading.value = false
    }
  }

  async function updateStrategy(id: string, data: Partial<Strategy>) {
    try {
      const response = await strategyApi.updateStrategy(id, data)
      const updated = response.data
      // Update in list
      const idx = strategies.value.findIndex((s) => s.id === id)
      if (idx !== -1) {
        strategies.value[idx] = updated
      }
      // Update current if viewing
      if (currentStrategy.value?.id === id) {
        currentStrategy.value = updated
      }
      return updated
    } catch (error) {
      console.error('Failed to update strategy:', error)
      return null
    }
  }

  async function deleteStrategy(id: string) {
    try {
      await strategyApi.deleteStrategy(id)
      strategies.value = strategies.value.filter((s) => s.id !== id)
      if (currentStrategy.value?.id === id) {
        currentStrategy.value = null
      }
      return true
    } catch (error) {
      console.error('Failed to delete strategy:', error)
      return false
    }
  }

  function setPage(page: number) {
    pagination.value.page = page
  }

  function clearCurrentStrategy() {
    currentStrategy.value = null
  }

  return {
    // State
    strategies,
    currentStrategy,
    pagination,
    loading,
    // Getters
    validStrategies,
    strategyById,
    // Actions
    loadStrategies,
    loadStrategy,
    updateStrategy,
    deleteStrategy,
    setPage,
    clearCurrentStrategy,
  }
})

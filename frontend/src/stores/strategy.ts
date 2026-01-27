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
  const searchQuery = ref('')

  // Getters
  const validStrategies = computed(() =>
    strategies.value.filter((s) => s.is_valid)
  )

  const strategyById = computed(() => (id: string) =>
    strategies.value.find((s) => s.id === id)
  )

  // Actions
  async function loadStrategies(params?: {
    page?: number
    pageSize?: number
    search?: string
    isValid?: boolean
  }) {
    loading.value = true
    try {
      const response = await strategyApi.getStrategies({
        page: params?.page || pagination.value.page,
        page_size: params?.pageSize || pagination.value.pageSize,
        search: params?.search || searchQuery.value || undefined,
        is_valid: params?.isValid,
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

  function setSearchQuery(query: string) {
    searchQuery.value = query
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
    searchQuery,
    // Getters
    validStrategies,
    strategyById,
    // Actions
    loadStrategies,
    loadStrategy,
    deleteStrategy,
    setSearchQuery,
    setPage,
    clearCurrentStrategy,
  }
})

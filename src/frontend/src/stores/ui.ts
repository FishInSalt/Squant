// UI Store

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

export const useUiStore = defineStore('ui', () => {
  // ========== State ==========
  const sidebarCollapsed = ref(false)
  const theme = ref<'light' | 'dark'>('light')
  const language = ref<'zh' | 'en'>('zh')
  const loading = ref(false)

  // ========== Getters ==========
  const isDark = computed(() => theme.value === 'dark')

  // ========== Actions ==========
  /**
   * 切换侧边栏
   */
  const toggleSidebar = () => {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  /**
   * 设置侧边栏状态
   */
  const setSidebarCollapsed = (collapsed: boolean) => {
    sidebarCollapsed.value = collapsed
  }

  /**
   * 切换主题
   */
  const toggleTheme = () => {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
    applyTheme()
  }

  /**
   * 设置主题
   */
  const setTheme = (newTheme: 'light' | 'dark') => {
    theme.value = newTheme
    applyTheme()
  }

  /**
   * 应用主题
   */
  const applyTheme = () => {
    const html = document.documentElement
    if (theme.value === 'dark') {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }
  }

  /**
   * 设置语言
   */
  const setLanguage = (lang: 'zh' | 'en') => {
    language.value = lang
  }

  // ========== 持久化 ==========
  // 从 localStorage 恢复
  const restoreFromStorage = () => {
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null
    if (savedTheme) {
      theme.value = savedTheme
      applyTheme()
    }

    const savedCollapsed = localStorage.getItem('sidebarCollapsed')
    if (savedCollapsed) {
      sidebarCollapsed.value = savedCollapsed === 'true'
    }

    const savedLanguage = localStorage.getItem('language') as 'zh' | 'en' | null
    if (savedLanguage) {
      language.value = savedLanguage
    }
  }

  // 监听变化并保存到 localStorage
  watch(theme, (val) => {
    localStorage.setItem('theme', val)
  })

  watch(sidebarCollapsed, (val) => {
    localStorage.setItem('sidebarCollapsed', String(val))
  })

  watch(language, (val) => {
    localStorage.setItem('language', val)
  })

  // 初始化
  restoreFromStorage()

  return {
    // State
    sidebarCollapsed,
    theme,
    language,
    loading,

    // Getters
    isDark,

    // Actions
    toggleSidebar,
    setSidebarCollapsed,
    toggleTheme,
    setTheme,
    setLanguage
  }
})

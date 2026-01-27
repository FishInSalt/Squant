import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { ElMessage } from 'element-plus'
import { useMarketStore } from './stores/market'

// 引入 Element Plus
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// 引入全局样式
import './assets/styles/index.scss'

const app = createApp(App)

// 注册 Pinia（必须在其他 store 使用之前注册）
const pinia = createPinia()
app.use(pinia)

// 注册 Element Plus
app.use(ElementPlus)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册路由
app.use(router)

// ========== 全局错误处理 ==========

/**
 * Vue 全局错误处理器
 *
 * 捕获所有未处理的错误，防止应用崩溃
 */
app.config.errorHandler = (err, instance, info) => {
  // 记录详细错误信息
  console.error('🔴 Global Error Handler')
  console.error('Error:', err)
  console.error('Component:', instance?.$options?.name || 'Unknown')
  console.error('Info:', info)

  // 显示友好的错误提示
  let errorMessage = '应用发生未知错误'
  if (err instanceof Error) {
    errorMessage = err.message || errorMessage
  } else if (typeof err === 'string') {
    errorMessage = err
  } else if (err && typeof err === 'object' && 'message' in err) {
    errorMessage = (err as any).message || errorMessage
  }

  ElMessage({
    message: errorMessage,
    type: 'error',
    duration: 5000,
    showClose: true
  })

  // 可选：上报错误到监控服务
  // reportErrorToMonitoringService(err, { instance, info, route: router.currentRoute.value })
}

/**
 * Vue 全局警告处理器
 *
 * 捕获 Vue 警告信息
 */
app.config.warnHandler = (msg, instance, trace) => {
  console.warn('⚠️  Vue Warning:', msg)
  console.warn('Component:', instance?.$options?.name || 'Unknown')
  console.warn('Trace:', trace)

  // 生产环境可以上报警告
  if (import.meta.env.PROD) {
    // reportWarningToMonitoringService(msg, { instance, trace })
  }
}

// ========== 全局错误边界 ==========

/**
 * 处理未捕获的 Promise 错误
 *
 * 捕获所有未处理的 Promise rejection
 */
window.addEventListener('unhandledrejection', (event) => {
  console.error('🔴 Unhandled Promise Rejection')
  console.error('Reason:', event.reason)
  console.error('Promise:', event.promise)

  // 阻止默认的控制台输出
  event.preventDefault()

  // 显示错误提示
  const errorMessage = event.reason instanceof Error
    ? event.reason.message
    : '操作失败，请重试'
  
  ElMessage({
    message: errorMessage,
    type: 'error',
    duration: 5000,
    showClose: true
  })
})

/**
 * 处理全局 JavaScript 错误
 *
 * 捕获所有全局 JavaScript 错误
 */
window.addEventListener('error', (event) => {
  console.error('🔴 Global JavaScript Error')
  console.error('Message:', event.message)
  console.error('Source:', event.filename)
  console.error('Line:', event.lineno)
  console.error('Column:', event.colno)
  console.error('Error:', event.error)

  // 显示错误提示
  const errorMessage = event.message || '系统发生错误，请刷新页面'
  
  ElMessage({
    message: errorMessage,
    type: 'error',
    duration: 5000,
    showClose: true
  })
})

// ========== 启动 Store 生命周期管理 ==========

/**
 * 启动 Market Store 的自动清理机制
 */
const marketStore = useMarketStore()
marketStore.startAutoCleanup()

/**
 * 应用卸载前清理资源
 */
window.addEventListener('beforeunload', () => {
  const marketStore = useMarketStore()
  marketStore.stopAutoCleanup()

  if (import.meta.env.DEV) {
    console.log('[App] Cleanup completed before unload')
  }
})

// ========== 挂载应用 ==========
app.mount('#app')

// ========== 开发环境调试工具 ==========

/**
 * 在开发环境暴露全局调试工具
 */
if (import.meta.env.DEV) {
  (window as any).__DEV_TOOLS__ = {
    // Market Store 调试
    market: () => {
      const marketStore = useMarketStore()
      return {
        stats: marketStore.stats,
        tickerSymbols: marketStore.getTickerSymbols(),
        kLineKeys: marketStore.getKLineKeys(),
        tickers: Array.from(marketStore.tickers.values()),
        kLines: Array.from(marketStore.kLines.values())
      }
    },

    // 清理过期数据
    cleanup: () => {
      const marketStore = useMarketStore()
      marketStore.cleanupExpiredData(true)
    },

    // 清空所有数据
    clear: () => {
      const marketStore = useMarketStore()
      marketStore.clear()
    },

    // 获取 Store 配置
    config: () => {
      return {
        MAX_KLINE_CACHE_SIZE: 100,
        TICKER_EXPIRY_TIME: 35 * 1000,
        KLINE_EXPIRY_TIME: 5 * 60 * 1000
      }
    }
  }

  console.log('[DevTools] Available: window.__DEV_TOOLS__.market(), .cleanup(), .clear(), .config()')
}

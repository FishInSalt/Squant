<template>
  <div id="app">
    <AppHeader />
    <AppNav />
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
    <AppFooter />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppNav from '@/components/layout/AppNav.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import { useMarketStore } from '@/stores/market'
import { useTradingStore } from '@/stores/trading'
import { useWebSocketStore } from '@/stores/websocket'

const marketStore = useMarketStore()
const tradingStore = useTradingStore()
const wsStore = useWebSocketStore()

onMounted(async () => {
  try {
    // 加载交易所列表
    await marketStore.loadExchanges()

    // 加载自选列表
    await marketStore.loadWatchlist()

    // 加载运行中的会话
    await tradingStore.loadAllRunningSessions()
  } catch (error) {
    console.error('App initialization error:', error)
  }

  // WebSocket 连接独立于上述初始化，即使加载失败也尝试连接
  wsStore.connect()
})

onUnmounted(() => {
  wsStore.disconnect()
})
</script>

<style lang="scss">
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

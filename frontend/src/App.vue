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
import { onMounted } from 'vue'
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
  // 加载交易所列表
  await marketStore.loadExchanges()

  // 加载运行中的会话
  await tradingStore.loadAllRunningSessions()

  // 连接 WebSocket
  wsStore.connect()
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

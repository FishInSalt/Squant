<template>
  <footer class="app-footer">
    <div class="footer-left">
      <span class="status-item" v-if="connectedExchanges.length > 0">
        <el-icon class="status-icon connected"><CircleCheck /></el-icon>
        <span>已连接: {{ connectedExchanges.join(', ') }}</span>
      </span>
      <span class="status-item" v-else>
        <el-icon class="status-icon disconnected"><CircleClose /></el-icon>
        <span>未连接交易所</span>
      </span>
    </div>

    <div class="footer-center">
      <span class="status-item" v-if="runningPaper > 0">
        <el-tag size="small" type="info">模拟: {{ runningPaper }}</el-tag>
      </span>
      <span class="status-item" v-if="runningLive > 0">
        <el-tag size="small" type="success">实盘: {{ runningLive }}</el-tag>
      </span>
      <span class="status-item" v-if="runningBacktest > 0">
        <el-tag size="small">回测: {{ runningBacktest }}</el-tag>
      </span>
    </div>

    <div class="footer-right">
      <span class="version">v1.0.0</span>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useTradingStore } from '@/stores/trading'
import { getAccounts } from '@/api/account'

const tradingStore = useTradingStore()

const connectedExchanges = ref<string[]>([])

const runningPaper = computed(() => tradingStore.runningPaperSessions.length)
const runningLive = computed(() => tradingStore.runningLiveSessions.length)
const runningBacktest = computed(() => tradingStore.runningBacktests.length)

onMounted(async () => {
  try {
    const response = await getAccounts()
    connectedExchanges.value = response.data
      .filter(a => a.connection_status === 'connected')
      .map(a => a.exchange.toUpperCase())
  } catch (error) {
    console.error('Failed to load accounts:', error)
  }
})
</script>

<style lang="scss" scoped>
.app-footer {
  height: 32px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  font-size: 12px;
  color: #909399;
}

.footer-left,
.footer-center,
.footer-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-icon {
  font-size: 14px;

  &.connected {
    color: #4caf50;
  }

  &.disconnected {
    color: #909399;
  }
}

.version {
  color: #c0c4cc;
}
</style>

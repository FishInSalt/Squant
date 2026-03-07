<template>
  <header class="app-header">
    <div class="header-left">
      <router-link to="/" class="logo">
        <span class="logo-icon">S</span>
        <span class="logo-text">Squant</span>
      </router-link>
    </div>

    <div class="header-center">
      <el-input
        v-model="searchQuery"
        placeholder="搜索交易对..."
        prefix-icon="Search"
        clearable
        class="search-input"
        @keyup.enter="handleSearch"
      />
    </div>

    <div class="header-right">
      <el-badge :value="runningCount" :hidden="runningCount === 0" class="status-badge">
        <el-button text @click="goToMonitor">
          <el-icon><VideoPlay /></el-icon>
          <span class="status-text">运行中</span>
        </el-button>
      </el-badge>

      <NotificationBell />

      <el-tooltip :content="wsConnected ? '已连接' : '未连接'" placement="bottom">
        <span class="connection-status" :class="{ connected: wsConnected }">
          <el-icon><Connection /></el-icon>
        </span>
      </el-tooltip>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTradingStore } from '@/stores/trading'
import { useWebSocketStore } from '@/stores/websocket'
import { useNotificationStore } from '@/stores/notification'
import NotificationBell from './NotificationBell.vue'

const router = useRouter()
const tradingStore = useTradingStore()
const wsStore = useWebSocketStore()
const notificationStore = useNotificationStore()

// Load unread count on mount
onMounted(() => {
  notificationStore.loadUnreadCount()
})

const searchQuery = ref('')

const runningCount = computed(() => tradingStore.totalRunningSessions)
const wsConnected = computed(() => wsStore.isConnected)

function handleSearch() {
  if (searchQuery.value.trim()) {
    // 实现搜索逻辑
    router.push({ name: 'HotMarket', query: { search: searchQuery.value } })
  }
}

function goToMonitor() {
  router.push('/trading/monitor')
}
</script>

<style lang="scss" scoped>
.app-header {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  flex: 0 0 200px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: inherit;

  .logo-icon {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #1890ff, #096dd9);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 20px;
    font-weight: 700;
  }

  .logo-text {
    font-size: 20px;
    font-weight: 600;
    color: #303133;
  }
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;

  .search-input {
    width: 360px;
  }
}

.header-right {
  flex: 0 0 200px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;

  .status-badge {
    :deep(.el-badge__content) {
      background-color: #1890ff;
    }
  }

  .status-text {
    margin-left: 4px;
  }

  .connection-status {
    display: flex;
    align-items: center;
    color: #909399;
    transition: color 0.3s;

    &.connected {
      color: #4caf50;
    }
  }
}
</style>

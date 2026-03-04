<template>
  <el-popover
    placement="bottom-end"
    :width="400"
    trigger="click"
    @show="onPanelShow"
  >
    <template #reference>
      <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99" class="notification-badge">
        <el-button text class="bell-btn">
          <el-icon :size="18"><Bell /></el-icon>
        </el-button>
      </el-badge>
    </template>

    <div class="notification-panel">
      <div class="panel-header">
        <span class="panel-title">告警通知</span>
        <el-button v-if="unreadCount > 0" text size="small" @click="handleMarkAllRead">
          全部已读
        </el-button>
      </div>

      <div class="panel-body">
        <div v-if="loading" class="panel-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <template v-else-if="notifications.length > 0">
          <div
            v-for="n in notifications"
            :key="n.id"
            class="notification-item"
            :class="{ unread: !n.is_read }"
            @click="handleClickItem(n)"
          >
            <div class="item-indicator" :class="n.level" />
            <div class="item-content">
              <div class="item-title">{{ n.title }}</div>
              <div class="item-message">{{ n.message }}</div>
              <div class="item-time">{{ formatRelativeTime(n.created_at) }}</div>
            </div>
          </div>
        </template>
        <el-empty v-else description="暂无通知" :image-size="60" />
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bell, Loading } from '@element-plus/icons-vue'
import { useNotificationStore } from '@/stores/notification'
import type { NotificationRecord } from '@/types'

const store = useNotificationStore()

const notifications = computed(() => store.notifications)
const unreadCount = computed(() => store.unreadCount)
const loading = computed(() => store.loading)

function onPanelShow() {
  store.loadNotifications()
}

function handleMarkAllRead() {
  store.markAllRead()
}

function handleClickItem(n: NotificationRecord) {
  if (!n.is_read) {
    store.markAsRead([n.id])
  }
}

function formatRelativeTime(isoStr: string): string {
  const now = Date.now()
  const then = new Date(isoStr).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 60) return '刚刚'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`
  return `${Math.floor(diffSec / 86400)} 天前`
}
</script>

<style lang="scss" scoped>
.bell-btn {
  padding: 4px;
  color: #606266;
}

.notification-badge {
  :deep(.el-badge__content) {
    background-color: #f56c6c;
  }
}

.notification-panel {
  max-height: 440px;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 8px;

  .panel-title {
    font-weight: 600;
    font-size: 14px;
  }
}

.panel-body {
  overflow-y: auto;
  max-height: 380px;
}

.panel-loading {
  display: flex;
  justify-content: center;
  padding: 24px;
  color: #909399;
}

.notification-item {
  display: flex;
  gap: 10px;
  padding: 10px 4px;
  border-bottom: 1px solid #f5f7fa;
  cursor: pointer;
  transition: background-color 0.2s;

  &:hover {
    background-color: #f5f7fa;
  }

  &.unread {
    background-color: #ecf5ff;

    &:hover {
      background-color: #d9ecff;
    }
  }

  &:last-child {
    border-bottom: none;
  }
}

.item-indicator {
  flex-shrink: 0;
  width: 4px;
  border-radius: 2px;
  min-height: 100%;

  &.critical { background-color: #f56c6c; }
  &.warning { background-color: #e6a23c; }
  &.info { background-color: #909399; }
}

.item-content {
  flex: 1;
  min-width: 0;

  .item-title {
    font-size: 13px;
    font-weight: 500;
    color: #303133;
    margin-bottom: 4px;
  }

  .item-message {
    font-size: 12px;
    color: #606266;
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .item-time {
    font-size: 11px;
    color: #909399;
    margin-top: 4px;
  }
}
</style>

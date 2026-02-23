<template>
  <el-tag :type="tagType" :size="size" :effect="effect">
    {{ displayText }}
  </el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Status = 'pending' | 'running' | 'completed' | 'failed' | 'stopped' |
              'submitted' | 'open' | 'partial' | 'filled' | 'cancelled' | 'rejected' |
              'active' | 'inactive' | 'archived' | 'triggered' | 'connected' | 'disconnected' | 'error'

type StatusContext = 'session' | 'order'

type TagType = 'success' | 'warning' | 'info' | 'danger' | 'primary'

interface Props {
  status: Status
  context?: StatusContext
  size?: 'small' | 'default' | 'large'
  effect?: 'dark' | 'light' | 'plain'
  showText?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  context: 'session',
  size: 'small',
  effect: 'light',
  showText: true,
})

const statusConfig: Record<Status, { type: TagType; text: string }> = {
  // 会话状态
  pending: { type: 'info', text: '待启动' },
  running: { type: 'success', text: '运行中' },
  completed: { type: 'primary', text: '已完成' },
  failed: { type: 'danger', text: '已失败' },
  stopped: { type: 'warning', text: '已停止' },
  // 订单状态
  submitted: { type: 'primary', text: '已提交' },
  open: { type: 'primary', text: '挂单中' },
  partial: { type: 'warning', text: '部分成交' },
  filled: { type: 'success', text: '已成交' },
  cancelled: { type: 'info', text: '已取消' },
  rejected: { type: 'danger', text: '已拒绝' },
  // 规则状态
  active: { type: 'success', text: '启用' },
  inactive: { type: 'info', text: '禁用' },
  archived: { type: 'info', text: '已归档' },
  triggered: { type: 'danger', text: '已触发' },
  // 连接状态
  connected: { type: 'success', text: '已连接' },
  disconnected: { type: 'info', text: '未连接' },
  error: { type: 'danger', text: '错误' },
}

// Context-specific overrides for statuses that have different meanings
const orderOverrides: Partial<Record<Status, { type: TagType; text: string }>> = {
  pending: { type: 'primary', text: '等待成交' },
}

const tagType = computed(() => {
  if (props.context === 'order') {
    const override = orderOverrides[props.status]
    if (override) return override.type
  }
  return statusConfig[props.status]?.type || 'info'
})

const displayText = computed(() => {
  if (props.context === 'order') {
    const override = orderOverrides[props.status]
    if (override) return override.text
  }
  return statusConfig[props.status]?.text || props.status
})
</script>

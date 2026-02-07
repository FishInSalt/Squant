<template>
  <div class="circuit-breaker">
    <div class="page-header">
      <h1 class="page-title">熔断控制</h1>
    </div>

    <div class="status-panel card" :class="{ halted: status?.global_halt }">
      <div class="status-indicator">
        <el-icon :size="64" :class="status?.global_halt ? 'danger' : 'success'">
          <Warning v-if="status?.global_halt" />
          <CircleCheck v-else />
        </el-icon>
      </div>

      <div class="status-info">
        <h2 class="status-title">
          {{ status?.global_halt ? '系统已熔断' : '系统运行正常' }}
        </h2>
        <p v-if="status?.global_halt" class="halt-reason">
          原因: {{ status.halt_reason || '手动触发' }}
        </p>
        <p v-if="status?.halted_at" class="halt-time">
          熔断时间: {{ formatDateTime(status.halted_at) }}
        </p>
      </div>

      <div class="status-stats">
        <div class="stat">
          <span class="value">{{ status?.active_sessions_count || 0 }}</span>
          <span class="label">运行中策略</span>
        </div>
        <div class="stat">
          <span class="value">{{ status?.pending_orders_count || 0 }}</span>
          <span class="label">待处理订单</span>
        </div>
      </div>
    </div>

    <div class="actions-panel card">
      <div class="card-header">
        <h3 class="card-title">紧急操作</h3>
      </div>

      <div class="actions-grid">
        <div class="action-item">
          <el-button
            v-if="!status?.global_halt"
            type="danger"
            size="large"
            @click="handleHalt"
          >
            <el-icon><Warning /></el-icon>
            一键熔断
          </el-button>
          <el-button
            v-else
            type="success"
            size="large"
            @click="handleResume"
          >
            <el-icon><CircleCheck /></el-icon>
            恢复交易
          </el-button>
          <p class="action-desc">
            {{ status?.global_halt ? '恢复所有交易功能' : '立即停止所有交易活动' }}
          </p>
        </div>

        <div class="action-item">
          <el-button
            type="warning"
            size="large"
            @click="handleCloseAll"
            :disabled="status?.active_sessions_count === 0"
          >
            <el-icon><Position /></el-icon>
            一键平仓
          </el-button>
          <p class="action-desc">
            平掉所有运行中策略的持仓
          </p>
        </div>
      </div>
    </div>

    <div class="conditions-panel card">
      <div class="card-header">
        <h3 class="card-title">自动熔断条件</h3>
      </div>

      <div class="conditions-list">
        <div
          v-for="condition in status?.auto_halt_conditions || []"
          :key="condition.id"
          class="condition-item"
        >
          <div class="condition-header">
            <span class="condition-name">{{ condition.name }}</span>
            <el-switch
              v-model="condition.enabled"
              @change="handleConditionToggle(condition)"
            />
          </div>

          <div class="condition-progress">
            <el-progress
              :percentage="getConditionProgress(condition)"
              :color="getConditionColor(condition)"
              :stroke-width="8"
            />
            <span class="progress-text">
              {{ formatConditionValue(condition) }} / {{ condition.threshold }}{{ getConditionUnit(condition) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { formatDateTime } from '@/utils/format'
import {
  getCircuitBreakerStatus,
  executeCircuitBreakerAction,
  updateAutoHaltCondition,
} from '@/api/risk'
import { useNotification } from '@/composables/useNotification'
import type { CircuitBreakerStatus, AutoHaltCondition } from '@/types'

const { toastSuccess, toastError, confirmDanger } = useNotification()

const status = ref<CircuitBreakerStatus | null>(null)

async function loadStatus() {
  try {
    const response = await getCircuitBreakerStatus()
    status.value = response.data
  } catch (error) {
    console.error('Failed to load status:', error)
  }
}

async function handleHalt() {
  const confirmed = await confirmDanger(
    '确定要执行一键熔断吗？这将立即停止所有交易活动！'
  )
  if (!confirmed) return

  try {
    await executeCircuitBreakerAction({ action: 'trigger', reason: '手动触发熔断' })
    toastSuccess('系统已熔断')
    loadStatus()
  } catch (error) {
    toastError('操作失败')
  }
}

async function handleResume() {
  const confirmed = await confirmDanger('确定要恢复交易吗？')
  if (!confirmed) return

  try {
    await executeCircuitBreakerAction({ action: 'reset' })
    toastSuccess('交易已恢复')
    loadStatus()
  } catch (error) {
    toastError('操作失败')
  }
}

async function handleCloseAll() {
  const confirmed = await confirmDanger(
    '确定要执行一键平仓吗？这将立即平掉所有持仓！'
  )
  if (!confirmed) return

  try {
    await executeCircuitBreakerAction({ action: 'close_all_positions' })
    toastSuccess('平仓指令已发送')
    loadStatus()
  } catch (error) {
    toastError('操作失败')
  }
}

async function handleConditionToggle(condition: AutoHaltCondition) {
  try {
    await updateAutoHaltCondition(condition.id, { enabled: condition.enabled })
    toastSuccess(condition.enabled ? '条件已启用' : '条件已禁用')
  } catch (error) {
    condition.enabled = !condition.enabled
    toastError('操作失败')
  }
}

function getConditionProgress(condition: AutoHaltCondition) {
  if (condition.threshold === 0) return 0
  return Math.min(100, (Math.abs(condition.current_value) / condition.threshold) * 100)
}

function getConditionColor(condition: AutoHaltCondition) {
  const progress = getConditionProgress(condition)
  if (progress >= 100) return '#ff4d4f'
  if (progress >= 80) return '#ff9800'
  if (progress >= 50) return '#faad14'
  return '#4caf50'
}

function formatConditionValue(condition: AutoHaltCondition) {
  return condition.current_value.toFixed(2)
}

function getConditionUnit(condition: AutoHaltCondition) {
  switch (condition.condition_type) {
    case 'total_loss':
    case 'drawdown':
      return '%'
    case 'consecutive_losses':
      return '次'
    case 'error_rate':
      return '%'
    default:
      return ''
  }
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadStatus()
  refreshTimer = setInterval(loadStatus, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style lang="scss" scoped>
.circuit-breaker {
  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .status-panel {
    display: flex;
    align-items: center;
    gap: 32px;
    padding: 32px;
    margin-bottom: 24px;
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border: 2px solid #4caf50;

    &.halted {
      background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
      border-color: #ff4d4f;
    }

    .status-indicator {
      .success {
        color: #4caf50;
      }

      .danger {
        color: #ff4d4f;
      }
    }

    .status-info {
      flex: 1;

      .status-title {
        font-size: 24px;
        font-weight: 600;
        margin: 0 0 8px;
      }

      .halt-reason,
      .halt-time {
        color: #606266;
        margin: 4px 0;
      }
    }

    .status-stats {
      display: flex;
      gap: 32px;

      .stat {
        text-align: center;

        .value {
          display: block;
          font-size: 32px;
          font-weight: 600;
        }

        .label {
          font-size: 12px;
          color: #909399;
        }
      }
    }
  }

  .actions-panel {
    margin-bottom: 24px;

    .actions-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 24px;
    }

    .action-item {
      text-align: center;
      padding: 24px;
      background: #f5f7fa;
      border-radius: 8px;

      .el-button {
        margin-bottom: 12px;
      }

      .action-desc {
        color: #909399;
        font-size: 14px;
        margin: 0;
      }
    }
  }

  .conditions-panel {
    .conditions-list {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }

    .condition-item {
      padding: 16px;
      background: #f5f7fa;
      border-radius: 8px;

      .condition-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;

        .condition-name {
          font-weight: 500;
        }
      }

      .condition-progress {
        .progress-text {
          display: block;
          text-align: right;
          font-size: 12px;
          color: #909399;
          margin-top: 4px;
        }
      }
    }
  }
}
</style>

<template>
  <div class="session-detail" v-loading="loading">
    <div class="page-header" v-if="session">
      <div class="header-left">
        <el-button icon="ArrowLeft" @click="goBack">返回</el-button>
        <div class="session-info">
          <h1 class="title">{{ session.strategy_name }}</h1>
          <el-tag size="small" :type="isPaper ? 'info' : 'danger'">
            {{ isPaper ? '模拟' : '实盘' }}
          </el-tag>
          <StatusBadge :status="session.status" />
        </div>
      </div>
      <div class="header-right" v-if="isRunning">
        <el-button type="warning" @click="handleStop">停止</el-button>
        <el-button v-if="isLive" type="danger" @click="handleEmergencyClose">
          紧急平仓
        </el-button>
      </div>
    </div>

    <div v-if="session?.error_message" class="error-status card">
      <el-icon class="error-icon"><CircleCloseFilled /></el-icon>
      <p class="error-message">{{ session.error_message }}</p>
    </div>

    <div v-if="status" class="result-content">
      <div class="metrics-grid">
        <div class="metric-card card">
          <span class="label">当前权益</span>
          <span class="value">{{ formatNumber(status.equity, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">可用资金</span>
          <span class="value">{{ formatNumber(status.cash, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">已实现盈亏</span>
          <PriceCell
            :value="status.realized_pnl"
            :change="status.realized_pnl"
            show-sign
            class="value"
          />
        </div>
        <div class="metric-card card">
          <span class="label">未实现盈亏</span>
          <PriceCell
            :value="status.unrealized_pnl"
            :change="status.unrealized_pnl"
            show-sign
            class="value"
          />
        </div>
      </div>

      <div class="metrics-grid secondary">
        <div class="metric-card card">
          <span class="label">初始资金</span>
          <span class="value secondary-value">{{ formatNumber(status.initial_capital, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">总手续费</span>
          <span class="value secondary-value">{{ formatNumber(status.total_fees, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">已处理Bar数</span>
          <span class="value secondary-value">{{ status.bar_count }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">已完成订单 / 交易数</span>
          <span class="value secondary-value">
            {{ status.completed_orders_count }} / {{ status.trades_count }}
          </span>
        </div>
      </div>

      <div class="positions-section card">
        <div class="card-header">
          <h3 class="card-title">当前持仓</h3>
          <span class="item-count">共 {{ positions.length }} 项</span>
        </div>
        <el-table :data="positionRows" stripe empty-text="暂无持仓">
          <el-table-column prop="symbol" label="币对" width="140" />
          <el-table-column prop="side" label="方向" width="80">
            <template #default="{ row }">
              <el-tag
                :type="row.side === 'long' ? 'success' : 'danger'"
                size="small"
              >
                {{ row.side === 'long' ? '多' : '空' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量" width="120" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.amount, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="avg_entry_price" label="均价" width="140" align="right">
            <template #default="{ row }">
              {{ formatPrice(row.avg_entry_price) }}
            </template>
          </el-table-column>
          <el-table-column prop="current_price" label="现价" width="140" align="right">
            <template #default="{ row }">
              {{ row.current_price != null ? formatPrice(row.current_price) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="unrealized_pnl" label="未实现盈亏" width="160" align="right">
            <template #default="{ row }">
              <PriceCell
                v-if="row.unrealized_pnl != null"
                :value="row.unrealized_pnl"
                :change="row.unrealized_pnl"
                show-sign
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="orders-section card">
        <div class="card-header">
          <h3 class="card-title">挂单</h3>
          <span class="item-count">
            共 {{ isPaper ? paperPendingOrders.length : liveOrders.length }} 项
          </span>
        </div>

        <el-table
          v-if="isPaper"
          :data="paperPendingOrders"
          stripe
          empty-text="暂无挂单"
        >
          <el-table-column prop="symbol" label="币对" width="140" />
          <el-table-column prop="side" label="方向" width="80">
            <template #default="{ row }">
              <el-tag
                :type="row.side === 'buy' ? 'success' : 'danger'"
                size="small"
              >
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="{ row }">
              {{ formatOrderType(row.type) }}
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量" width="120" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.amount, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="140" align="right">
            <template #default="{ row }">
              {{ row.price != null ? formatPrice(row.price) : '市价' }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <StatusBadge :status="row.status" />
            </template>
          </el-table-column>
        </el-table>

        <el-table
          v-else
          :data="liveOrders"
          stripe
          empty-text="暂无挂单"
        >
          <el-table-column prop="symbol" label="币对" width="140" />
          <el-table-column prop="side" label="方向" width="80">
            <template #default="{ row }">
              <el-tag
                :type="row.side === 'buy' ? 'success' : 'danger'"
                size="small"
              >
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="{ row }">
              {{ formatOrderType(row.type) }}
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量" width="120" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.amount, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="filled_amount" label="已成交" width="120" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.filled_amount, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="140" align="right">
            <template #default="{ row }">
              {{ row.price != null ? formatPrice(row.price) : '市价' }}
            </template>
          </el-table-column>
          <el-table-column prop="avg_fill_price" label="均价" width="140" align="right">
            <template #default="{ row }">
              {{ row.avg_fill_price != null ? formatPrice(row.avg_fill_price) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <StatusBadge :status="row.status" />
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="isLive && riskState" class="risk-section card">
        <div class="card-header">
          <h3 class="card-title">风控状态</h3>
        </div>
        <div class="risk-grid">
          <div class="risk-item">
            <span class="label">日盈亏</span>
            <PriceCell
              :value="riskState.daily_pnl"
              :change="riskState.daily_pnl"
              show-sign
              class="value"
            />
          </div>
          <div class="risk-item">
            <span class="label">日交易次数</span>
            <span class="value">{{ riskState.daily_trade_count }}</span>
          </div>
          <div class="risk-item">
            <span class="label">连续亏损</span>
            <span class="value">{{ riskState.consecutive_losses }}</span>
          </div>
          <div class="risk-item">
            <span class="label">熔断状态</span>
            <StatusBadge
              :status="riskState.circuit_breaker_active ? 'active' : 'inactive'"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCloseFilled } from '@element-plus/icons-vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatNumber, formatPrice, formatOrderType } from '@/utils/format'
import { getPaperSession, getPaperSessionStatus, stopPaperTrading } from '@/api/paper'
import {
  getLiveSession,
  getLiveSessionStatus,
  stopLiveTrading,
  emergencyClosePositions,
} from '@/api/live'
import { useNotification } from '@/composables/useNotification'
import type {
  PaperSession,
  LiveSession,
  PaperTradingStatus,
  LiveTradingStatus,
  PendingOrderInfo,
  LiveOrderInfo,
  Position,
  RiskState,
} from '@/types'

const props = defineProps<{
  type: 'paper' | 'live'
  id: string
}>()

const router = useRouter()
const { toastSuccess, toastError, confirmDanger } = useNotification()

const loading = ref(true)
const session = ref<PaperSession | LiveSession | null>(null)
const status = ref<PaperTradingStatus | LiveTradingStatus | null>(null)

let refreshTimer: ReturnType<typeof setInterval> | null = null

const isPaper = computed(() => props.type === 'paper')
const isLive = computed(() => props.type === 'live')
const isRunning = computed(() => session.value?.status === 'running')

const positions = computed<[string, Position][]>(() => {
  if (!status.value) return []
  return Object.entries(status.value.positions)
})

const positionRows = computed(() => {
  return positions.value.map(([symbol, pos]) => ({
    ...pos,
    symbol,
    side: pos.amount >= 0 ? 'long' : 'short',
  }))
})

const paperPendingOrders = computed<PendingOrderInfo[]>(() => {
  if (!status.value || !isPaper.value) return []
  return (status.value as PaperTradingStatus).pending_orders || []
})

const liveOrders = computed<LiveOrderInfo[]>(() => {
  if (!status.value || !isLive.value) return []
  return (status.value as LiveTradingStatus).live_orders || []
})

const riskState = computed<RiskState | null>(() => {
  if (!status.value || !isLive.value) return null
  return (status.value as LiveTradingStatus).risk_state || null
})

async function loadSession() {
  try {
    loading.value = true
    const response = isPaper.value
      ? await getPaperSession(props.id)
      : await getLiveSession(props.id)
    session.value = response.data

    if (isRunning.value) {
      await loadStatus()
      startPolling()
    } else {
      stopPolling()
    }
  } catch (error) {
    console.error('Failed to load session:', error)
    toastError('加载会话失败')
  } finally {
    loading.value = false
  }
}

async function loadStatus() {
  try {
    const response = isPaper.value
      ? await getPaperSessionStatus(props.id)
      : await getLiveSessionStatus(props.id)
    status.value = response.data

    if (!status.value.is_running) {
      stopPolling()
      await loadSession()
    }
  } catch (error) {
    console.error('Failed to load status:', error)
  }
}

function startPolling() {
  if (refreshTimer) return
  refreshTimer = setInterval(loadStatus, 3000)
}

function stopPolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function goBack() {
  router.push('/trading/monitor')
}

async function handleStop() {
  const label = isPaper.value ? '模拟交易' : '实盘交易'
  const confirmed = await confirmDanger(`确定要停止该${label}吗？`)
  if (!confirmed) return

  try {
    if (isPaper.value) {
      await stopPaperTrading(props.id)
    } else {
      await stopLiveTrading(props.id)
    }
    toastSuccess('已停止')
    await loadSession()
  } catch (error) {
    toastError('停止失败')
  }
}

async function handleEmergencyClose() {
  const confirmed = await confirmDanger('确定要执行紧急平仓吗？这将立即平掉所有持仓！')
  if (!confirmed) return

  try {
    await emergencyClosePositions(props.id)
    toastSuccess('紧急平仓执行中')
    await loadSession()
  } catch (error) {
    toastError('执行失败')
  }
}

onMounted(() => {
  loadSession()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.session-detail {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    .header-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .session-info {
      display: flex;
      align-items: center;
      gap: 12px;

      .title {
        font-size: 24px;
        font-weight: 600;
        margin: 0;
      }
    }

    .header-right {
      display: flex;
      gap: 12px;
    }
  }

  .error-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;
    margin-bottom: 24px;

    .error-icon {
      font-size: 48px;
      color: #ff4d4f;
      margin-bottom: 16px;
    }

    .error-message {
      color: #ff4d4f;
      margin-bottom: 16px;
      text-align: center;
      max-width: 600px;
      word-break: break-word;
    }
  }

  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;

    &.secondary {
      margin-bottom: 24px;
    }
  }

  .metric-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 20px;

    .label {
      font-size: 12px;
      color: #909399;
    }

    .value {
      font-size: 24px;
      font-weight: 600;

      &.secondary-value {
        font-size: 18px;
      }
    }
  }

  .positions-section,
  .orders-section,
  .risk-section {
    margin-bottom: 24px;

    .item-count {
      font-size: 12px;
      color: #909399;
    }
  }

  .risk-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    padding: 16px;
  }

  .risk-item {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .label {
      font-size: 12px;
      color: #909399;
    }

    .value {
      font-size: 18px;
      font-weight: 500;
    }
  }
}
</style>

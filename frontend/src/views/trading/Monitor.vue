<template>
  <div class="monitor">
    <div class="page-header">
      <h1 class="page-title">运行监控</h1>
    </div>

    <el-tabs v-model="activeTab" class="monitor-tabs">
      <el-tab-pane label="全部" name="all">
        <div class="sessions-grid">
          <SessionCard
            v-for="session in allSessions"
            :key="`${session.type}-${session.id}`"
            :session="session"
            @click="goToSession(session)"
            @stop="handleStop(session)"
            @emergency-close="handleEmergencyClose(session)"
          />
        </div>
        <div v-if="allSessions.length === 0" class="empty-state card">
          <el-icon class="empty-icon"><VideoPlay /></el-icon>
          <p>暂无运行中的交易会话</p>
        </div>
      </el-tab-pane>

      <el-tab-pane label="回测" name="backtest">
        <div class="sessions-grid">
          <SessionCard
            v-for="session in backtestSessions"
            :key="session.id"
            :session="{ ...session, type: 'backtest' }"
            @click="goToBacktest(session.id)"
          />
        </div>
        <div v-if="backtestSessions.length === 0" class="empty-state card">
          <p>暂无运行中的回测</p>
        </div>
      </el-tab-pane>

      <el-tab-pane label="模拟交易" name="paper">
        <div class="sessions-grid">
          <SessionCard
            v-for="session in paperSessions"
            :key="session.id"
            :session="{ ...session, type: 'paper' }"
            @click="goToPaper(session.id)"
            @stop="handleStopPaper(session.id)"
          />
        </div>
        <div v-if="paperSessions.length === 0" class="empty-state card">
          <p>暂无运行中的模拟交易</p>
        </div>
      </el-tab-pane>

      <el-tab-pane label="实盘交易" name="live">
        <div class="sessions-grid">
          <SessionCard
            v-for="session in liveSessions"
            :key="session.id"
            :session="{ ...session, type: 'live' }"
            @click="goToLive(session.id)"
            @stop="handleStopLive(session.id)"
            @emergency-close="handleEmergencyCloseLive(session.id)"
          />
        </div>
        <div v-if="liveSessions.length === 0" class="empty-state card">
          <p>暂无运行中的实盘交易</p>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, defineComponent, h } from 'vue'
import { useRouter } from 'vue-router'
import { useTradingStore } from '@/stores/trading'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatExchangeName, formatNumber, formatRelativeTime } from '@/utils/format'
import { stopPaperTrading } from '@/api/paper'
import { stopLiveTrading, emergencyClosePositions } from '@/api/live'
import { useNotification } from '@/composables/useNotification'
import type { BacktestRun, PaperSession, LiveSession } from '@/types'

// SessionCard component
const SessionCard = defineComponent({
  name: 'SessionCard',
  props: {
    session: {
      type: Object as () => (BacktestRun | PaperSession | LiveSession) & { type: string },
      required: true,
    },
  },
  emits: ['click', 'stop', 'emergency-close'],
  setup(props, { emit }) {
    return () => {
      const session = props.session
      const isLive = session.type === 'live'
      const isPaper = session.type === 'paper'
      const isBacktest = session.type === 'backtest'

      return h('div', {
        class: ['session-card', 'card', { live: isLive }],
        onClick: () => emit('click'),
      }, [
        h('div', { class: 'card-header' }, [
          h('div', { class: 'header-left' }, [
            h('span', { class: 'strategy-name' }, (session as any).strategy_name),
            h('el-tag', {
              size: 'small',
              type: isLive ? 'danger' : isPaper ? 'info' : 'primary',
            }, isLive ? '实盘' : isPaper ? '模拟' : '回测'),
          ]),
          h(StatusBadge, { status: session.status }),
        ]),

        !isBacktest && h('div', { class: 'session-info' }, [
          h('span', null, (session as any).symbol),
          h('span', null, formatExchangeName((session as any).exchange)),
        ]),

        isBacktest && h('el-progress', {
          percentage: (session as BacktestRun).progress,
          'stroke-width': 8,
        }),

        !isBacktest && h('div', { class: 'session-stats' }, [
          h('div', { class: 'stat' }, [
            h('span', { class: 'label' }, '当前权益'),
            h('span', { class: 'value' }, formatNumber((session as any).current_equity, 2)),
          ]),
          h('div', { class: 'stat' }, [
            h('span', { class: 'label' }, '收益'),
            h(PriceCell, {
              value: (session as any).realized_pnl + (session as any).unrealized_pnl,
              change: (session as any).realized_pnl + (session as any).unrealized_pnl,
              showSign: true,
              class: 'value',
            }),
          ]),
        ]),

        h('div', { class: 'session-meta' }, [
          h('span', null, `启动于 ${formatRelativeTime((session as any).created_at)}`),
        ]),

        session.status === 'running' && h('div', {
          class: 'session-actions',
          onClick: (e: Event) => e.stopPropagation(),
        }, [
          h('el-button', {
            size: 'small',
            type: 'warning',
            onClick: () => emit('stop'),
          }, '停止'),
          isLive && h('el-button', {
            size: 'small',
            type: 'danger',
            onClick: () => emit('emergency-close'),
          }, '紧急平仓'),
        ]),
      ])
    }
  },
})

const router = useRouter()
const tradingStore = useTradingStore()
const { toastSuccess, toastError, confirmDanger } = useNotification()

const activeTab = ref('all')

const backtestSessions = computed(() => tradingStore.runningBacktests)
const paperSessions = computed(() => tradingStore.runningPaperSessions)
const liveSessions = computed(() => tradingStore.runningLiveSessions)

const allSessions = computed(() => {
  const sessions: ((BacktestRun | PaperSession | LiveSession) & { type: string })[] = []

  backtestSessions.value.forEach((s) => {
    sessions.push({ ...s, type: 'backtest' })
  })
  paperSessions.value.forEach((s) => {
    sessions.push({ ...s, type: 'paper' })
  })
  liveSessions.value.forEach((s) => {
    sessions.push({ ...s, type: 'live' })
  })

  return sessions.sort((a, b) => {
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

function goToSession(session: { type: string; id: string }) {
  if (session.type === 'backtest') {
    goToBacktest(session.id)
  } else if (session.type === 'paper') {
    goToPaper(session.id)
  } else {
    goToLive(session.id)
  }
}

function goToBacktest(id: string) {
  router.push(`/trading/backtest/${id}/result`)
}

function goToPaper(id: string) {
  router.push(`/trading/monitor/paper/${id}`)
}

function goToLive(id: string) {
  router.push(`/trading/monitor/live/${id}`)
}

function handleStop(session: { type: string; id: string }) {
  if (session.type === 'paper') {
    handleStopPaper(session.id)
  } else if (session.type === 'live') {
    handleStopLive(session.id)
  }
}

function handleEmergencyClose(session: { type: string; id: string }) {
  if (session.type === 'live') {
    handleEmergencyCloseLive(session.id)
  }
}

async function handleStopPaper(id: string) {
  const confirmed = await confirmDanger('确定要停止该模拟交易吗？')
  if (!confirmed) return

  try {
    await stopPaperTrading(id)
    toastSuccess('已停止')
    tradingStore.loadRunningPaperSessions()
  } catch (error) {
    toastError('停止失败')
  }
}

async function handleStopLive(id: string) {
  const confirmed = await confirmDanger('确定要停止该实盘交易吗？当前持仓将被保留。')
  if (!confirmed) return

  try {
    await stopLiveTrading(id)
    toastSuccess('已停止')
    tradingStore.loadRunningLiveSessions()
  } catch (error) {
    toastError('停止失败')
  }
}

async function handleEmergencyCloseLive(id: string) {
  const confirmed = await confirmDanger('确定要执行紧急平仓吗？这将立即平掉所有持仓！')
  if (!confirmed) return

  try {
    await emergencyClosePositions(id)
    toastSuccess('紧急平仓执行中')
    tradingStore.loadRunningLiveSessions()
  } catch (error) {
    toastError('执行失败')
  }
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  tradingStore.loadAllRunningSessions()
  refreshTimer = setInterval(() => {
    tradingStore.loadAllRunningSessions()
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style lang="scss" scoped>
.monitor {
  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .sessions-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 16px;
  }

  .session-card {
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
      transform: translateY(-2px);
    }

    &.live {
      border-left: 4px solid #ff4d4f;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;

      .header-left {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .strategy-name {
        font-weight: 600;
      }
    }

    .session-info {
      display: flex;
      gap: 12px;
      font-size: 13px;
      color: #606266;
      margin-bottom: 12px;
    }

    .session-stats {
      display: flex;
      gap: 24px;
      margin-bottom: 12px;

      .stat {
        .label {
          font-size: 12px;
          color: #909399;
          display: block;
        }

        .value {
          font-size: 16px;
          font-weight: 500;
        }
      }
    }

    .session-meta {
      font-size: 12px;
      color: #909399;
      margin-bottom: 12px;
    }

    .session-actions {
      display: flex;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid #ebeef5;
    }
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;
    color: #909399;

    .empty-icon {
      font-size: 48px;
      margin-bottom: 16px;
      color: #dcdfe6;
    }
  }
}
</style>

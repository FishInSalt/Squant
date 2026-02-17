<template>
  <div class="backtest-result" v-loading="loading">
    <div class="page-header" v-if="backtest">
      <div class="header-left">
        <el-button icon="ArrowLeft" @click="goBack">返回</el-button>
        <div class="backtest-info">
          <h1 class="title">{{ backtest.strategy_name }}</h1>
          <StatusBadge :status="backtest.status" />
        </div>
      </div>
      <div class="header-right" v-if="backtest.status === 'completed'">
        <el-button @click="exportResult">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
        <el-button type="primary" @click="runAgain">
          再次回测
        </el-button>
      </div>
    </div>

    <div v-if="backtest?.status === 'pending' || backtest?.status === 'running'" class="running-status card">
      <el-progress
        :percentage="Math.round(backtest.progress || 0)"
        :stroke-width="20"
        striped
        striped-flow
      />
      <p class="status-text">
        {{ backtest.status === 'pending' ? '正在准备回测...' : '正在回测中...' }}
      </p>
      <el-button
        type="danger"
        plain
        :loading="cancelling"
        :disabled="backtest.status === 'pending'"
        @click="handleCancel"
      >
        取消回测
      </el-button>
    </div>

    <div v-if="backtest?.status === 'error'" class="error-status card">
      <el-icon class="error-icon"><CircleCloseFilled /></el-icon>
      <p class="error-message">{{ backtest.error_message }}</p>
      <el-button type="primary" @click="runAgain">重新回测</el-button>
    </div>

    <div v-if="backtest?.status === 'completed' && result && result.metrics" class="result-content">
      <div class="metrics-grid">
        <div class="metric-card card">
          <span class="label">总收益率</span>
          <PriceCell
            :value="result.metrics.total_return_pct"
            :change="result.metrics.total_return_pct"
            :decimals="2"
            show-sign
            suffix="%"
            class="value"
          />
        </div>
        <div class="metric-card card">
          <span class="label">年化收益</span>
          <PriceCell
            :value="result.metrics.annualized_return"
            :change="result.metrics.annualized_return"
            :decimals="2"
            show-sign
            suffix="%"
            class="value"
          />
        </div>
        <div class="metric-card card">
          <span class="label">最大回撤</span>
          <span class="value danger">{{ formatPercent(-result.metrics.max_drawdown_pct) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">夏普比率</span>
          <span class="value">{{ formatNumber(result.metrics.sharpe_ratio, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">胜率</span>
          <span class="value">{{ formatNumber(result.metrics.win_rate, 2) }}%</span>
        </div>
        <div class="metric-card card">
          <span class="label">盈亏比</span>
          <span class="value">{{ formatNumber(result.metrics.profit_factor, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">总交易数</span>
          <span class="value">{{ result.metrics.total_trades }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">总手续费</span>
          <span class="value">{{ formatNumber(result.metrics.total_fees, 2) }}</span>
        </div>
      </div>

      <div class="chart-section card">
        <div class="card-header">
          <h3 class="card-title">收益曲线</h3>
        </div>
        <EquityCurve :data="result.equity_curve" :trades="result.trades" height="400px" show-benchmark />
      </div>

      <div class="trades-section card">
        <div class="card-header">
          <h3 class="card-title">交易记录</h3>
          <div class="trade-summary">
            <el-tag type="success" size="small" effect="plain">盈利 {{ tradeStats.wins }}</el-tag>
            <el-tag type="danger" size="small" effect="plain">亏损 {{ tradeStats.losses }}</el-tag>
            <el-tag size="small" effect="plain">胜率 {{ formatNumber(tradeStats.winRate, 2) }}%</el-tag>
            <span class="trade-count">共 {{ result.trades.length }} 笔</span>
          </div>
        </div>
        <el-table :data="paginatedTrades" stripe max-height="500" :default-sort="{ prop: 'entry_time', order: 'ascending' }" @sort-change="handleSortChange">
          <el-table-column prop="entry_time" label="入场时间" width="170" sortable="custom">
            <template #default="{ row }">
              {{ formatDateTime(row.entry_time) }}
            </template>
          </el-table-column>
          <el-table-column prop="side" label="类型" width="70">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === 'buy' ? '做多' : '做空' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="entry_price" label="入场价" width="120" align="right" sortable="custom">
            <template #default="{ row }">
              {{ formatPrice(row.entry_price) }}
            </template>
          </el-table-column>
          <el-table-column prop="exit_price" label="出场价" width="120" align="right">
            <template #default="{ row }">
              {{ row.exit_price ? formatPrice(row.exit_price) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="exit_time" label="出场时间" width="170" sortable="custom">
            <template #default="{ row }">
              {{ row.exit_time ? formatDateTime(row.exit_time) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="数量" width="100" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.amount, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="fees" label="手续费" width="90" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.fees, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="pnl" label="盈亏" width="120" align="right" sortable="custom">
            <template #default="{ row }">
              <PriceCell
                v-if="row.pnl !== undefined"
                :value="row.pnl"
                :change="row.pnl"
                show-sign
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="pnl_pct" label="盈亏%" width="100" align="right" sortable="custom">
            <template #default="{ row }">
              <PriceCell
                v-if="row.pnl_pct !== undefined"
                :value="row.pnl_pct"
                :change="row.pnl_pct"
                :decimals="2"
                show-sign
                suffix="%"
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="trade-pagination" v-if="result.trades.length > tradesPageSize">
          <el-pagination
            v-model:current-page="tradesPage"
            :page-size="tradesPageSize"
            :page-sizes="[20, 50, 100]"
            :total="result.trades.length"
            layout="total, sizes, prev, pager, next"
            @size-change="handleTradesPageSizeChange"
          />
        </div>
      </div>

      <div class="details-section card">
        <div class="card-header">
          <h3 class="card-title">详细指标</h3>
        </div>
        <div class="details-grid">
          <div class="detail-item">
            <span class="label">总收益</span>
            <span class="value">{{ formatNumber(result.metrics.total_return, 2) }} USDT</span>
          </div>
          <div class="detail-item">
            <span class="label">年化波动率</span>
            <span class="value">{{ formatNumber(result.metrics.volatility, 2) }}%</span>
          </div>
          <div class="detail-item">
            <span class="label">索提诺比率</span>
            <span class="value">{{ formatNumber(result.metrics.sortino_ratio, 2) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">卡尔玛比率</span>
            <span class="value">{{ formatNumber(result.metrics.calmar_ratio, 2) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">回撤持续时间</span>
            <span class="value">{{ formatHours(result.metrics.max_drawdown_duration_hours) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">回测天数</span>
            <span class="value">{{ result.metrics.total_duration_days }}天</span>
          </div>
          <div class="detail-item">
            <span class="label">盈利交易数</span>
            <span class="value">{{ result.metrics.winning_trades }}</span>
          </div>
          <div class="detail-item">
            <span class="label">亏损交易数</span>
            <span class="value">{{ result.metrics.losing_trades }}</span>
          </div>
          <div class="detail-item">
            <span class="label">平均收益</span>
            <span class="value">{{ formatNumber(result.metrics.avg_trade_return, 2) }} USDT</span>
          </div>
          <div class="detail-item">
            <span class="label">平均盈利</span>
            <span class="value success">{{ formatNumber(result.metrics.avg_win, 2) }} USDT</span>
          </div>
          <div class="detail-item">
            <span class="label">平均亏损</span>
            <span class="value danger">{{ formatNumber(result.metrics.avg_loss, 2) }} USDT</span>
          </div>
          <div class="detail-item">
            <span class="label">最大连亏</span>
            <span class="value">{{ result.metrics.max_consecutive_losses }}</span>
          </div>
          <div class="detail-item">
            <span class="label">最大单笔盈利</span>
            <span class="value success">{{ formatNumber(result.metrics.largest_win, 2) }} USDT</span>
          </div>
          <div class="detail-item">
            <span class="label">最大单笔亏损</span>
            <span class="value danger">{{ formatNumber(result.metrics.largest_loss, 2) }} USDT</span>
          </div>
          <div class="detail-item">
            <span class="label">平均持仓时间</span>
            <span class="value">{{ formatHours(result.metrics.avg_trade_duration_hours) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">总手续费</span>
            <span class="value">{{ formatNumber(result.metrics.total_fees, 2) }} USDT</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import { formatDateTime, formatPrice, formatNumber, formatPercent } from '@/utils/format'
import { getBacktestStatus, getBacktestResult, exportBacktestResult, cancelBacktest } from '@/api/backtest'
import { useNotification } from '@/composables/useNotification'
import type { BacktestRun, BacktestResult } from '@/types'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const { toastSuccess, toastError } = useNotification()

const loading = ref(true)
const cancelling = ref(false)
const backtest = ref<BacktestRun | null>(null)
const result = ref<BacktestResult | null>(null)

const tradesPage = ref(1)
const tradesPageSize = ref(20)
const tradesSortProp = ref('')
const tradesSortOrder = ref('')

const sortedTrades = computed(() => {
  if (!result.value) return []
  const trades = [...result.value.trades]
  if (!tradesSortProp.value || !tradesSortOrder.value) return trades

  const prop = tradesSortProp.value
  const asc = tradesSortOrder.value === 'ascending'

  trades.sort((a: any, b: any) => {
    let va = a[prop]
    let vb = b[prop]
    if (prop === 'entry_time' || prop === 'exit_time') {
      va = va ? new Date(va).getTime() : 0
      vb = vb ? new Date(vb).getTime() : 0
    }
    if (va < vb) return asc ? -1 : 1
    if (va > vb) return asc ? 1 : -1
    return 0
  })
  return trades
})

const paginatedTrades = computed(() => {
  const start = (tradesPage.value - 1) * tradesPageSize.value
  return sortedTrades.value.slice(start, start + tradesPageSize.value)
})

const tradeStats = computed(() => {
  if (!result.value) return { wins: 0, losses: 0, winRate: 0 }
  const trades = result.value.trades
  const wins = trades.filter(t => t.pnl > 0).length
  const losses = trades.filter(t => t.pnl < 0).length
  const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0
  return { wins, losses, winRate }
})

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  tradesSortProp.value = prop || ''
  tradesSortOrder.value = order || ''
  tradesPage.value = 1
}

function handleTradesPageSizeChange(size: number) {
  tradesPageSize.value = size
  tradesPage.value = 1
}

let pollingTimer: ReturnType<typeof setInterval> | null = null

async function loadBacktest() {
  try {
    const response = await getBacktestStatus(props.id)
    backtest.value = response.data

    if (backtest.value.status === 'completed') {
      await loadResult()
      stopPolling()
    } else if (backtest.value.status === 'running' || backtest.value.status === 'pending') {
      startPolling()
    } else {
      // error / cancelled
      stopPolling()
    }
  } catch (error) {
    console.error('Failed to load backtest:', error)
    stopPolling()
    toastError('加载回测数据失败')
  } finally {
    loading.value = false
  }
}

async function loadResult() {
  try {
    const response = await getBacktestResult(props.id)
    result.value = response.data
  } catch (error) {
    console.error('Failed to load result:', error)
  }
}

function startPolling() {
  if (pollingTimer) return
  pollingTimer = setInterval(loadBacktest, 2000)
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

function goBack() {
  router.push('/trading/backtest')
}

function runAgain() {
  if (backtest.value) {
    router.push({
      path: '/trading/backtest',
      query: {
        strategy_id: backtest.value.strategy_id,
        exchange: backtest.value.exchange,
        symbol: backtest.value.symbol,
      },
    })
  }
}

function formatHours(hours: number): string {
  if (hours === null || hours === undefined || isNaN(hours)) return '-'
  if (hours >= 24) {
    const days = hours / 24
    return `${formatNumber(days, 1)}天`
  }
  return `${formatNumber(hours, 1)}小时`
}

async function exportResult() {
  try {
    const response = await exportBacktestResult(props.id, 'csv')
    const blob = new Blob(['\uFEFF' + response.data.content], { type: response.data.content_type || 'text/csv;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = response.data.filename || `backtest_${props.id}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
    toastSuccess('导出成功')
  } catch (error) {
    toastError('导出失败')
  }
}

async function handleCancel() {
  cancelling.value = true
  try {
    await cancelBacktest(props.id)
    toastSuccess('已请求取消回测')
  } catch {
    toastError('取消回测失败')
  } finally {
    cancelling.value = false
  }
}

onMounted(() => {
  loadBacktest()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.backtest-result {
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

    .backtest-info {
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

  .running-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;

    :deep(.el-progress) {
      width: 100%;
      max-width: 600px;
    }

    .status-text {
      margin-top: 16px;
      margin-bottom: 16px;
      color: #909399;
    }
  }

  .error-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;

    .error-icon {
      font-size: 48px;
      color: #ff4d4f;
      margin-bottom: 16px;
    }

    .error-message {
      color: #ff4d4f;
      margin-bottom: 16px;
    }
  }

  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
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

      &.success {
        color: #00c853;
      }

      &.danger {
        color: #ff1744;
      }
    }
  }

  .chart-section {
    margin-bottom: 24px;
  }

  .trades-section {
    margin-bottom: 24px;

    .trade-summary {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .trade-count {
      font-size: 12px;
      color: #909399;
    }

    .trade-pagination {
      display: flex;
      justify-content: flex-end;
      margin-top: 16px;
    }
  }

  .details-section {
    .details-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }

    .detail-item {
      display: flex;
      flex-direction: column;
      gap: 4px;

      .label {
        font-size: 12px;
        color: #909399;
      }

      .value {
        font-size: 16px;
        font-weight: 500;

        &.success {
          color: #00c853;
        }

        &.danger {
          color: #ff1744;
        }
      }
    }
  }
}
</style>

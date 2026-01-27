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

    <div v-if="backtest?.status === 'running'" class="running-status card">
      <el-progress
        :percentage="backtest.progress"
        :stroke-width="20"
        striped
        striped-flow
      />
      <p class="status-text">正在回测中...</p>
    </div>

    <div v-if="backtest?.status === 'failed'" class="error-status card">
      <el-icon class="error-icon"><CircleCloseFilled /></el-icon>
      <p class="error-message">{{ backtest.error }}</p>
      <el-button type="primary" @click="runAgain">重新回测</el-button>
    </div>

    <div v-if="backtest?.status === 'completed' && result" class="result-content">
      <div class="metrics-grid">
        <div class="metric-card card">
          <span class="label">总收益</span>
          <PriceCell
            :value="result.metrics.total_return"
            :change="result.metrics.total_return"
            :decimals="2"
            show-sign
            class="value"
          />
        </div>
        <div class="metric-card card">
          <span class="label">年化收益</span>
          <PriceCell
            :value="result.metrics.annual_return"
            :change="result.metrics.annual_return"
            :decimals="2"
            show-sign
            class="value"
          />
        </div>
        <div class="metric-card card">
          <span class="label">最大回撤</span>
          <span class="value danger">{{ formatPercent(result.metrics.max_drawdown) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">夏普比率</span>
          <span class="value">{{ formatNumber(result.metrics.sharpe_ratio, 2) }}</span>
        </div>
        <div class="metric-card card">
          <span class="label">胜率</span>
          <span class="value">{{ formatPercent(result.metrics.win_rate) }}</span>
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
          <span class="label">最终资金</span>
          <span class="value">{{ formatNumber(result.metrics.end_capital, 2) }}</span>
        </div>
      </div>

      <div class="chart-section card">
        <div class="card-header">
          <h3 class="card-title">收益曲线</h3>
        </div>
        <EquityCurve :data="result.equity_curve" height="400px" />
      </div>

      <div class="trades-section card">
        <div class="card-header">
          <h3 class="card-title">交易记录</h3>
          <span class="trade-count">共 {{ result.trades.length }} 笔</span>
        </div>
        <el-table :data="result.trades" stripe max-height="400">
          <el-table-column prop="timestamp" label="时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.timestamp) }}
            </template>
          </el-table-column>
          <el-table-column prop="side" label="方向" width="80">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === 'buy' ? '买入' : '卖出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="price" label="价格" width="120" align="right">
            <template #default="{ row }">
              {{ formatPrice(row.price) }}
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="120" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.quantity, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="commission" label="手续费" width="100" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.commission, 4) }}
            </template>
          </el-table-column>
          <el-table-column prop="pnl" label="盈亏" width="120" align="right">
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
          <el-table-column prop="pnl_percent" label="盈亏%" width="100" align="right">
            <template #default="{ row }">
              <PriceCell
                v-if="row.pnl_percent !== undefined"
                :value="row.pnl_percent"
                :change="row.pnl_percent"
                :decimals="2"
                show-sign
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="details-section card">
        <div class="card-header">
          <h3 class="card-title">详细指标</h3>
        </div>
        <div class="details-grid">
          <div class="detail-item">
            <span class="label">索提诺比率</span>
            <span class="value">{{ formatNumber(result.metrics.sortino_ratio, 2) }}</span>
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
            <span class="value">{{ formatPercent(result.metrics.avg_trade_return) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">平均盈利</span>
            <span class="value success">{{ formatPercent(result.metrics.avg_win) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">平均亏损</span>
            <span class="value danger">{{ formatPercent(result.metrics.avg_loss) }}</span>
          </div>
          <div class="detail-item">
            <span class="label">最大连胜</span>
            <span class="value">{{ result.metrics.max_consecutive_wins }}</span>
          </div>
          <div class="detail-item">
            <span class="label">最大连亏</span>
            <span class="value">{{ result.metrics.max_consecutive_losses }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import EquityCurve from '@/components/charts/EquityCurve.vue'
import { formatDateTime, formatPrice, formatNumber, formatPercent } from '@/utils/format'
import { getBacktestStatus, getBacktestResult, exportBacktestResult } from '@/api/backtest'
import { useNotification } from '@/composables/useNotification'
import type { BacktestRun, BacktestResult } from '@/types'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const { toastSuccess, toastError } = useNotification()

const loading = ref(true)
const backtest = ref<BacktestRun | null>(null)
const result = ref<BacktestResult | null>(null)

let pollingTimer: ReturnType<typeof setInterval> | null = null

async function loadBacktest() {
  try {
    const response = await getBacktestStatus(props.id)
    backtest.value = response.data

    if (backtest.value.status === 'completed') {
      await loadResult()
      stopPolling()
    } else if (backtest.value.status === 'running') {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (error) {
    console.error('Failed to load backtest:', error)
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
        exchange: backtest.value.config.exchange,
        symbol: backtest.value.config.symbol,
      },
    })
  }
}

async function exportResult() {
  try {
    const response = await exportBacktestResult(props.id, 'csv')
    window.open(response.data.download_url, '_blank')
    toastSuccess('导出成功')
  } catch (error) {
    toastError('导出失败')
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

    .trade-count {
      font-size: 12px;
      color: #909399;
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

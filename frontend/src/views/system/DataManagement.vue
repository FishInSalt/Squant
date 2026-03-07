<template>
  <div class="data-management">
    <div class="page-header">
      <h1 class="page-title">数据管理</h1>
    </div>

    <!-- Download Section -->
    <div class="card download-section">
      <div class="card-header">
        <h3 class="card-title">下载历史数据</h3>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleDownload"
      >
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="交易所" prop="exchange">
              <el-select
                v-model="form.exchange"
                placeholder="选择交易所"
                style="width: 100%"
                @change="handleExchangeChange"
              >
                <el-option
                  v-for="e in EXCHANGE_OPTIONS"
                  :key="e.value"
                  :label="e.label"
                  :value="e.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="交易对" prop="symbol">
              <el-select
                v-model="form.symbol"
                placeholder="输入搜索交易对"
                filterable
                :loading="symbolsLoading"
                style="width: 100%"
              >
                <el-option
                  v-for="s in symbolOptions"
                  :key="s"
                  :label="s"
                  :value="s"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label="时间周期" prop="timeframe">
              <el-select v-model="form.timeframe" style="width: 100%">
                <el-option
                  v-for="tf in TIMEFRAME_OPTIONS"
                  :key="tf.value"
                  :label="tf.label"
                  :value="tf.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="时间范围" prop="dateRange">
              <el-date-picker
                v-model="form.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DDTHH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <div class="form-actions">
          <el-button
            type="primary"
            :loading="downloadStarting"
            @click="handleDownload"
          >
            <el-icon><Download /></el-icon>
            开始下载
          </el-button>
        </div>
      </el-form>
    </div>

    <!-- Active Downloads -->
    <div v-if="downloadTasks.length > 0" class="card active-downloads">
      <div class="card-header">
        <h3 class="card-title">下载任务</h3>
      </div>

      <el-table :data="downloadTasks" stripe>
        <el-table-column prop="exchange" label="交易所" width="100">
          <template #default="{ row }">
            {{ formatExchangeName(row.exchange) }}
          </template>
        </el-table-column>
        <el-table-column prop="symbol" label="交易对" width="130" />
        <el-table-column prop="timeframe" label="周期" width="80" />
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }">
            <div class="progress-cell">
              <el-progress
                :percentage="Math.round(row.progress)"
                :status="getProgressStatus(row.status)"
                :stroke-width="16"
                text-inside
              />
              <span v-if="row.downloaded_candles" class="progress-detail">
                {{ row.downloaded_candles }}
                <span v-if="row.total_candles"> / {{ row.total_candles }}</span>
                根K线
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="错误" min-width="150">
          <template #default="{ row }">
            <span v-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'downloading' || row.status === 'pending'"
              type="danger"
              size="small"
              @click="handleCancel(row.id)"
            >
              取消
            </el-button>
            <el-button
              v-if="row.status === 'failed'"
              type="primary"
              size="small"
              @click="handleRetry(row)"
            >
              重试
            </el-button>
            <el-button
              v-if="row.status === 'completed' || row.status === 'failed'"
              type="info"
              size="small"
              @click="handleRemoveTask(row.id)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Historical Data Table -->
    <div class="card data-table-section">
      <div class="card-header">
        <h3 class="card-title">已下载数据</h3>
        <el-button size="small" @click="loadHistoricalData">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <el-table
        :data="historicalData"
        stripe
        v-loading="dataLoading"
        empty-text="暂无历史数据"
      >
        <el-table-column prop="exchange" label="交易所" width="100">
          <template #default="{ row }">
            {{ formatExchangeName(row.exchange) }}
          </template>
        </el-table-column>
        <el-table-column prop="symbol" label="交易对" width="130" />
        <el-table-column prop="timeframe" label="周期" width="80" />
        <el-table-column prop="candle_count" label="K线数量" width="120" align="right">
          <template #default="{ row }">
            {{ row.candle_count.toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="数据范围" min-width="280">
          <template #default="{ row }">
            <span v-if="row.start_date && row.end_date">
              {{ formatDateTime(row.start_date) }} ~ {{ formatDateTime(row.end_date) }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Download, Refresh } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  downloadHistoricalData,
  getDownloadTasks,
  cancelDownloadTask,
  removeDownloadTask,
  getHistoricalDataList,
  deleteHistoricalData,
  getExchangeSymbols,
} from '@/api/system'
import { useNotification } from '@/composables/useNotification'
import { formatExchangeName, formatDateTime } from '@/utils/format'
import { TIMEFRAME_OPTIONS, EXCHANGE_OPTIONS } from '@/utils/constants'
import type { DataDownloadTask, HistoricalData } from '@/types'

const { toastSuccess, toastError, confirmDelete } = useNotification()

// Form state
const formRef = ref<FormInstance>()
const downloadStarting = ref(false)

const form = reactive({
  exchange: 'okx',
  symbol: '',
  timeframe: '1h',
  dateRange: null as [string, string] | null,
})

const rules: FormRules = {
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  symbol: [{ required: true, message: '请选择交易对', trigger: 'change' }],
  timeframe: [{ required: true, message: '请选择时间周期', trigger: 'change' }],
  dateRange: [{ required: true, message: '请选择时间范围', trigger: 'change' }],
}

// Symbol loading
const symbolOptions = ref<string[]>([])
const symbolsLoading = ref(false)

async function loadSymbols() {
  if (!form.exchange) return
  symbolsLoading.value = true
  try {
    const res = await getExchangeSymbols(form.exchange)
    symbolOptions.value = res.data || []
  } catch {
    symbolOptions.value = []
  } finally {
    symbolsLoading.value = false
  }
}

function handleExchangeChange() {
  form.symbol = ''
  loadSymbols()
}

// Download tasks
const downloadTasks = ref<DataDownloadTask[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

async function loadTasks() {
  try {
    const res = await getDownloadTasks()
    downloadTasks.value = res.data || []
  } catch {
    // Silent fail on polling
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(loadTasks, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function handleDownload() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid || !form.dateRange) return

  downloadStarting.value = true
  try {
    await downloadHistoricalData({
      exchange: form.exchange,
      symbol: form.symbol,
      timeframe: form.timeframe,
      start_date: form.dateRange[0],
      end_date: form.dateRange[1],
    })
    toastSuccess('下载任务已创建')
    await loadTasks()
    startPolling()
  } catch {
    toastError('创建下载任务失败')
  } finally {
    downloadStarting.value = false
  }
}

async function handleCancel(taskId: string) {
  try {
    await cancelDownloadTask(taskId)
    toastSuccess('下载任务已取消')
    await loadTasks()
  } catch {
    toastError('取消下载任务失败')
  }
}

async function handleRetry(task: DataDownloadTask) {
  try {
    await removeDownloadTask(task.id)
    await downloadHistoricalData({
      exchange: task.exchange,
      symbol: task.symbol,
      timeframe: task.timeframe,
      start_date: task.start_date,
      end_date: task.end_date,
    })
    toastSuccess('已重新创建下载任务')
    await loadTasks()
    startPolling()
  } catch {
    toastError('重试失败')
  }
}

async function handleRemoveTask(taskId: string) {
  try {
    await removeDownloadTask(taskId)
    await loadTasks()
  } catch {
    toastError('删除任务记录失败')
  }
}

function getProgressStatus(status: string) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

function getStatusType(status: string): 'info' | 'warning' | 'primary' | 'success' | 'danger' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'downloading') return 'primary'
  return 'info'
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '等待中',
    downloading: '下载中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

// Historical data
const historicalData = ref<HistoricalData[]>([])
const dataLoading = ref(false)

async function loadHistoricalData() {
  dataLoading.value = true
  try {
    const res = await getHistoricalDataList()
    historicalData.value = res.data || []
  } catch {
    toastError('加载历史数据列表失败')
  } finally {
    dataLoading.value = false
  }
}

async function handleDelete(item: HistoricalData) {
  const confirmed = await confirmDelete(
    `${formatExchangeName(item.exchange)} ${item.symbol} ${item.timeframe} 的历史数据`
  )
  if (!confirmed) return

  try {
    await deleteHistoricalData(item.id)
    toastSuccess('数据已删除')
    await loadHistoricalData()
  } catch {
    toastError('删除失败')
  }
}

// Watch for active downloads to manage polling
watch(
  downloadTasks,
  (tasks) => {
    const hasActive = tasks.some(
      (t) => t.status === 'downloading' || t.status === 'pending'
    )
    if (hasActive) {
      startPolling()
    } else {
      stopPolling()
      // Refresh historical data when downloads complete
      loadHistoricalData()
    }
  },
  { deep: true }
)

// Lifecycle
onMounted(() => {
  loadSymbols()
  loadTasks()
  loadHistoricalData()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.data-management {
  .page-header {
    margin-bottom: 24px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .card {
    margin-bottom: 20px;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;

    .card-title {
      font-size: 16px;
      font-weight: 600;
      margin: 0;
    }
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }

  .progress-cell {
    .progress-detail {
      display: block;
      margin-top: 4px;
      font-size: 12px;
      color: #909399;
    }
  }

  .error-text {
    color: #f56c6c;
    font-size: 12px;
  }
}
</style>

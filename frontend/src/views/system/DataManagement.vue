<template>
  <div class="data-management">
    <div class="page-header">
      <h1 class="page-title">数据管理</h1>
    </div>

    <div class="download-form card">
      <div class="card-header">
        <h3 class="card-title">下载历史数据</h3>
      </div>

      <el-form :model="downloadForm" label-position="top">
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="交易所">
              <el-select v-model="downloadForm.exchange" style="width: 100%">
                <el-option label="Binance" value="binance" />
                <el-option label="OKX" value="okx" />
                <el-option label="Bybit" value="bybit" />
              </el-select>
            </el-form-item>
          </el-col>

          <el-col :span="6">
            <el-form-item label="交易对">
              <el-select
                v-model="downloadForm.symbol"
                filterable
                remote
                :remote-method="searchSymbols"
                :loading="searchingSymbols"
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

          <el-col :span="6">
            <el-form-item label="时间周期">
              <el-select v-model="downloadForm.timeframe" style="width: 100%">
                <el-option label="1分钟" value="1m" />
                <el-option label="5分钟" value="5m" />
                <el-option label="15分钟" value="15m" />
                <el-option label="1小时" value="1h" />
                <el-option label="4小时" value="4h" />
                <el-option label="1天" value="1d" />
              </el-select>
            </el-form-item>
          </el-col>

          <el-col :span="6">
            <el-form-item label="时间范围">
              <el-date-picker
                v-model="downloadForm.dateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button
            type="primary"
            :loading="submitting"
            @click="handleDownload"
            :disabled="!isFormValid"
          >
            <el-icon><Download /></el-icon>
            开始下载
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="tasks-panel card">
      <div class="card-header">
        <h3 class="card-title">下载任务</h3>
        <el-button size="small" @click="loadTasks">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="symbol" label="交易对" width="120" />
        <el-table-column prop="exchange" label="交易所" width="100">
          <template #default="{ row }">
            {{ formatExchangeName(row.exchange) }}
          </template>
        </el-table-column>
        <el-table-column prop="timeframe" label="周期" width="80" />
        <el-table-column label="时间范围" width="200">
          <template #default="{ row }">
            {{ row.start_date }} ~ {{ row.end_date }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              v-if="row.status === 'downloading'"
              :percentage="row.progress || 0"
              :stroke-width="8"
            />
            <span v-else-if="row.status === 'completed'" class="completed-text">
              已完成 ({{ formatNumber(row.downloaded_candles || row.total_candles || 0, 0) }} 条)
            </span>
            <span v-else-if="row.status === 'failed'" class="error-text">
              {{ row.error }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'downloading'"
              size="small"
              type="danger"
              @click="handleCancel(row)"
            >
              取消
            </el-button>
            <el-button
              v-else-if="row.status === 'failed'"
              size="small"
              @click="handleRetry(row)"
            >
              重试
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="data-list card">
      <div class="card-header">
        <h3 class="card-title">已下载数据</h3>
        <el-input
          v-model="searchQuery"
          placeholder="搜索..."
          prefix-icon="Search"
          clearable
          style="width: 200px"
        />
      </div>

      <el-table :data="filteredDataList" v-loading="loadingData" stripe>
        <el-table-column prop="symbol" label="交易对" width="120" />
        <el-table-column prop="exchange" label="交易所" width="100">
          <template #default="{ row }">
            {{ formatExchangeName(row.exchange) }}
          </template>
        </el-table-column>
        <el-table-column prop="timeframe" label="周期" width="80" />
        <el-table-column label="数据范围" width="200">
          <template #default="{ row }">
            {{ row.start_date }} ~ {{ row.end_date }}
          </template>
        </el-table-column>
        <el-table-column prop="candle_count" label="记录数" width="120" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.candle_count, 0) }}
          </template>
        </el-table-column>
        <el-table-column prop="file_size" label="文件大小" width="100" align="right">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              size="small"
              type="danger"
              @click="handleDeleteData(row)"
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { formatDateTime, formatNumber, formatExchangeName } from '@/utils/format'
import {
  getDownloadTasks,
  startDownload,
  cancelDownload,
  getDownloadedData,
  deleteDownloadedData,
  searchSymbols as apiSearchSymbols,
} from '@/api/system'
import { useNotification } from '@/composables/useNotification'
import type { DataDownloadTask, HistoricalData } from '@/types'

type DownloadTask = DataDownloadTask
type DataRecord = HistoricalData

const { toastSuccess, toastError, confirmDelete } = useNotification()

const loading = ref(false)
const loadingData = ref(false)
const submitting = ref(false)
const searchingSymbols = ref(false)
const tasks = ref<DownloadTask[]>([])
const dataList = ref<DataRecord[]>([])
const symbolOptions = ref<string[]>([])
const searchQuery = ref('')

const downloadForm = reactive({
  exchange: 'binance',
  symbol: '',
  timeframe: '1h',
  dateRange: [] as string[],
})

const isFormValid = computed(() => {
  return (
    downloadForm.exchange &&
    downloadForm.symbol &&
    downloadForm.timeframe &&
    downloadForm.dateRange.length === 2
  )
})

const filteredDataList = computed(() => {
  if (!searchQuery.value) return dataList.value
  const query = searchQuery.value.toLowerCase()
  return dataList.value.filter(
    (d) =>
      d.symbol.toLowerCase().includes(query) ||
      d.exchange.toLowerCase().includes(query)
  )
})

function getStatusTagType(status: string) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'downloading':
      return 'primary'
    case 'failed':
      return 'danger'
    default:
      return 'warning'
  }
}

function getStatusLabel(status: string) {
  switch (status) {
    case 'pending':
      return '等待中'
    case 'downloading':
      return '下载中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    default:
      return status
  }
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

async function searchSymbols(query: string) {
  if (!query || query.length < 2) {
    symbolOptions.value = []
    return
  }

  searchingSymbols.value = true
  try {
    const response = await apiSearchSymbols(downloadForm.exchange, query)
    symbolOptions.value = response.data
  } catch (error) {
    console.error('Failed to search symbols:', error)
  } finally {
    searchingSymbols.value = false
  }
}

async function loadTasks() {
  loading.value = true
  try {
    const response = await getDownloadTasks()
    tasks.value = response.data
  } catch (error) {
    console.error('Failed to load tasks:', error)
  } finally {
    loading.value = false
  }
}

async function loadDataList() {
  loadingData.value = true
  try {
    const response = await getDownloadedData()
    dataList.value = response.data
  } catch (error) {
    console.error('Failed to load data list:', error)
  } finally {
    loadingData.value = false
  }
}

async function handleDownload() {
  submitting.value = true
  try {
    await startDownload({
      exchange: downloadForm.exchange,
      symbol: downloadForm.symbol,
      timeframe: downloadForm.timeframe,
      start_date: downloadForm.dateRange[0],
      end_date: downloadForm.dateRange[1],
    })
    toastSuccess('下载任务已创建')
    loadTasks()
  } catch (error) {
    toastError('创建下载任务失败')
  } finally {
    submitting.value = false
  }
}

async function handleCancel(task: DownloadTask) {
  try {
    await cancelDownload(task.id)
    toastSuccess('已取消下载')
    loadTasks()
  } catch (error) {
    toastError('取消失败')
  }
}

async function handleRetry(task: DownloadTask) {
  submitting.value = true
  try {
    await startDownload({
      exchange: task.exchange,
      symbol: task.symbol,
      timeframe: task.timeframe,
      start_date: task.start_date,
      end_date: task.end_date,
    })
    toastSuccess('重试任务已创建')
    loadTasks()
  } catch (error) {
    toastError('重试失败')
  } finally {
    submitting.value = false
  }
}

async function handleDeleteData(data: DataRecord) {
  const confirmed = await confirmDelete('该数据')
  if (!confirmed) return

  try {
    await deleteDownloadedData(data.id)
    toastSuccess('数据已删除')
    loadDataList()
  } catch (error) {
    toastError('删除失败')
  }
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadTasks()
  loadDataList()
  // 自动刷新任务状态
  refreshTimer = setInterval(loadTasks, 5000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
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

  .download-form {
    margin-bottom: 24px;
  }

  .tasks-panel {
    margin-bottom: 24px;

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  }

  .data-list {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  }

  .completed-text {
    color: #4caf50;
    font-size: 13px;
  }

  .error-text {
    color: #ff4d4f;
    font-size: 13px;
  }
}
</style>

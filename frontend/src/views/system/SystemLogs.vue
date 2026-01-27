<template>
  <div class="system-logs">
    <div class="page-header">
      <h1 class="page-title">系统日志</h1>
      <el-button @click="handleExport" :loading="exporting">
        <el-icon><Download /></el-icon>
        导出日志
      </el-button>
    </div>

    <div class="filter-bar card">
      <el-form :inline="true" :model="filter">
        <el-form-item label="日志级别">
          <el-select
            v-model="filter.level"
            placeholder="全部"
            clearable
            style="width: 120px"
          >
            <el-option
              v-for="l in levelOptions"
              :key="l.value"
              :label="l.label"
              :value="l.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="模块">
          <el-select
            v-model="filter.module"
            placeholder="全部"
            clearable
            style="width: 150px"
          >
            <el-option
              v-for="m in moduleOptions"
              :key="m"
              :label="m"
              :value="m"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filter.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 380px"
          />
        </el-form-item>

        <el-form-item label="搜索">
          <el-input
            v-model="filter.search"
            placeholder="搜索日志内容..."
            clearable
            style="width: 200px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadLogs">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="logs-panel card">
      <div class="card-header">
        <div class="header-left">
          <el-checkbox v-model="autoRefresh">自动刷新</el-checkbox>
          <span v-if="autoRefresh" class="refresh-hint">(每5秒)</span>
        </div>
        <el-button size="small" @click="loadLogs">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <el-table
        :data="logs"
        v-loading="loading"
        :row-class-name="getRowClassName"
        stripe
        max-height="600"
      >
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            <span class="timestamp">{{ formatDateTime(row.timestamp) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="level" label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="getLevelTagType(row.level)" size="small">
              {{ row.level.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="module" label="模块" width="150">
          <template #default="{ row }">
            <span class="module-name">{{ row.module }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="message" label="消息" min-width="400">
          <template #default="{ row }">
            <div class="log-message">
              {{ row.message }}
              <el-button
                v-if="row.extra"
                link
                size="small"
                @click="showDetail(row)"
              >
                详情
              </el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="source" label="来源" width="120">
          <template #default="{ row }">
            <span class="source">{{ row.source || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[50, 100, 200, 500]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadLogs"
          @current-change="loadLogs"
        />
      </div>
    </div>

    <!-- 日志详情对话框 -->
    <el-dialog v-model="detailVisible" title="日志详情" width="600px">
      <div v-if="selectedLog" class="log-detail">
        <div class="detail-row">
          <span class="label">时间:</span>
          <span class="value">{{ formatDateTime(selectedLog.timestamp) }}</span>
        </div>
        <div class="detail-row">
          <span class="label">级别:</span>
          <el-tag :type="getLevelTagType(selectedLog.level)" size="small">
            {{ selectedLog.level.toUpperCase() }}
          </el-tag>
        </div>
        <div class="detail-row">
          <span class="label">模块:</span>
          <span class="value">{{ selectedLog.module }}</span>
        </div>
        <div class="detail-row">
          <span class="label">消息:</span>
          <span class="value">{{ selectedLog.message }}</span>
        </div>
        <div v-if="selectedLog.source" class="detail-row">
          <span class="label">来源:</span>
          <span class="value">{{ selectedLog.source }}</span>
        </div>
        <div v-if="selectedLog.extra" class="detail-row extra">
          <span class="label">附加信息:</span>
          <pre class="extra-content">{{ JSON.stringify(selectedLog.extra, null, 2) }}</pre>
        </div>
        <div v-if="selectedLog.traceback" class="detail-row traceback">
          <span class="label">堆栈跟踪:</span>
          <pre class="traceback-content">{{ selectedLog.traceback }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted } from 'vue'
import { formatDateTime } from '@/utils/format'
import { getSystemLogs, exportSystemLogs } from '@/api/system'
import { useNotification } from '@/composables/useNotification'

interface LogEntry {
  id: string
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  module: string
  message: string
  source?: string
  extra?: Record<string, unknown>
  traceback?: string
}

const { toastSuccess, toastError } = useNotification()

const loading = ref(false)
const exporting = ref(false)
const autoRefresh = ref(false)
const logs = ref<LogEntry[]>([])
const detailVisible = ref(false)
const selectedLog = ref<LogEntry | null>(null)

const pagination = reactive({
  page: 1,
  pageSize: 100,
  total: 0,
})

const filter = reactive({
  level: '',
  module: '',
  dateRange: [] as string[],
  search: '',
})

const levelOptions = [
  { value: 'debug', label: 'DEBUG' },
  { value: 'info', label: 'INFO' },
  { value: 'warning', label: 'WARNING' },
  { value: 'error', label: 'ERROR' },
  { value: 'critical', label: 'CRITICAL' },
]

const moduleOptions = [
  'system',
  'api',
  'market',
  'strategy',
  'backtest',
  'paper',
  'live',
  'order',
  'risk',
  'account',
  'websocket',
]

function getLevelTagType(level: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  switch (level) {
    case 'debug':
      return 'info'
    case 'info':
      return 'primary'
    case 'warning':
      return 'warning'
    case 'error':
      return 'danger'
    case 'critical':
      return 'danger'
    default:
      return 'info'
  }
}

function getRowClassName({ row }: { row: LogEntry }) {
  if (row.level === 'error' || row.level === 'critical') {
    return 'error-row'
  }
  if (row.level === 'warning') {
    return 'warning-row'
  }
  return ''
}

async function loadLogs() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filter.level) params.level = filter.level
    if (filter.module) params.module = filter.module
    if (filter.search) params.search = filter.search
    if (filter.dateRange.length === 2) {
      params.start_time = filter.dateRange[0]
      params.end_time = filter.dateRange[1]
    }

    const response = await getSystemLogs(params as any)
    logs.value = response.data.items
    pagination.total = response.data.total
  } catch (error) {
    console.error('Failed to load logs:', error)
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filter.level = ''
  filter.module = ''
  filter.dateRange = []
  filter.search = ''
  pagination.page = 1
  loadLogs()
}

function showDetail(log: LogEntry) {
  selectedLog.value = log
  detailVisible.value = true
}

async function handleExport() {
  exporting.value = true
  try {
    const params: Record<string, unknown> = {}
    if (filter.level) params.level = filter.level
    if (filter.module) params.module = filter.module
    if (filter.search) params.search = filter.search
    if (filter.dateRange.length === 2) {
      params.start_time = filter.dateRange[0]
      params.end_time = filter.dateRange[1]
    }

    const response = await exportSystemLogs(params as any)

    // 创建下载链接
    const blob = new Blob([response.data], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `system_logs_${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    toastSuccess('日志已导出')
  } catch (error) {
    toastError('导出失败')
  } finally {
    exporting.value = false
  }
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

watch(autoRefresh, (value) => {
  if (value) {
    refreshTimer = setInterval(loadLogs, 5000)
  } else if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})

onMounted(() => {
  loadLogs()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style lang="scss" scoped>
.system-logs {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .filter-bar {
    margin-bottom: 16px;
    padding: 16px;

    :deep(.el-form-item) {
      margin-bottom: 0;
    }
  }

  .logs-panel {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;

      .header-left {
        display: flex;
        align-items: center;
        gap: 8px;

        .refresh-hint {
          font-size: 12px;
          color: #909399;
        }
      }
    }

    :deep(.error-row) {
      background-color: #fff2f0 !important;
    }

    :deep(.warning-row) {
      background-color: #fffbe6 !important;
    }

    .timestamp {
      font-family: monospace;
      font-size: 12px;
    }

    .module-name {
      font-weight: 500;
    }

    .log-message {
      word-break: break-word;
    }

    .source {
      font-size: 12px;
      color: #909399;
    }

    .pagination {
      display: flex;
      justify-content: flex-end;
      margin-top: 16px;
    }
  }

  .log-detail {
    .detail-row {
      display: flex;
      margin-bottom: 12px;

      .label {
        width: 80px;
        color: #909399;
        flex-shrink: 0;
      }

      .value {
        flex: 1;
      }

      &.extra,
      &.traceback {
        flex-direction: column;

        .label {
          margin-bottom: 8px;
        }
      }

      .extra-content,
      .traceback-content {
        background: #f5f7fa;
        padding: 12px;
        border-radius: 4px;
        font-size: 12px;
        overflow-x: auto;
        margin: 0;
      }

      .traceback-content {
        color: #ff4d4f;
      }
    }
  }
}
</style>

<template>
  <div class="strategy-detail" v-loading="loading">
    <div class="page-header" v-if="strategy">
      <div class="header-left">
        <el-button icon="ArrowLeft" @click="goBack">返回</el-button>
        <div class="strategy-info">
          <h1 class="strategy-name">{{ strategy.name }}</h1>
          <StatusBadge :status="strategy.is_valid ? 'active' : 'error'" />
        </div>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="goToBacktest">
          <el-icon><Histogram /></el-icon>
          回测
        </el-button>
        <el-button @click="goToPaper">
          <el-icon><Monitor /></el-icon>
          模拟交易
        </el-button>
        <el-button @click="goToLive">
          <el-icon><Connection /></el-icon>
          实盘交易
        </el-button>
        <el-button type="danger" @click="handleDelete">
          <el-icon><Delete /></el-icon>
          删除
        </el-button>
      </div>
    </div>

    <div class="content-grid" v-if="strategy">
      <div class="main-content">
        <div class="card info-card">
          <div class="card-header">
            <h3 class="card-title">基本信息</h3>
          </div>
          <div class="info-grid">
            <div class="info-item">
              <span class="label">策略名称</span>
              <span class="value">{{ strategy.name }}</span>
            </div>
            <div class="info-item">
              <span class="label">版本</span>
              <span class="value">v{{ strategy.version }}</span>
            </div>
            <div class="info-item">
              <span class="label">作者</span>
              <span class="value">{{ strategy.author || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="label">类名</span>
              <span class="value text-mono">{{ strategy.class_name }}</span>
            </div>
            <div class="info-item">
              <span class="label">文件名</span>
              <span class="value text-mono">{{ strategy.filename }}</span>
            </div>
            <div class="info-item">
              <span class="label">创建时间</span>
              <span class="value">{{ formatDateTime(strategy.created_at) }}</span>
            </div>
            <div class="info-item">
              <span class="label">更新时间</span>
              <span class="value">{{ formatDateTime(strategy.updated_at) }}</span>
            </div>
          </div>
          <div class="description" v-if="strategy.description">
            <h4>描述</h4>
            <p>{{ strategy.description }}</p>
          </div>
        </div>

        <div class="card code-card">
          <div class="card-header">
            <h3 class="card-title">策略代码</h3>
          </div>
          <pre class="code-preview"><code>{{ strategyCode }}</code></pre>
        </div>
      </div>

      <div class="side-content">
        <div class="card params-card">
          <div class="card-header">
            <h3 class="card-title">参数配置</h3>
          </div>
          <div v-if="strategy.params_schema?.properties" class="params-list">
            <div
              v-for="(param, key) in strategy.params_schema.properties"
              :key="key"
              class="param-item"
            >
              <div class="param-header">
                <span class="param-name">{{ param.title || key }}</span>
                <el-tag size="small" type="info">{{ param.type }}</el-tag>
              </div>
              <p class="param-description" v-if="param.description">
                {{ param.description }}
              </p>
              <div class="param-meta">
                <span v-if="param.default !== undefined">
                  默认值: {{ param.default }}
                </span>
                <span v-if="param.minimum !== undefined">
                  最小值: {{ param.minimum }}
                </span>
                <span v-if="param.maximum !== undefined">
                  最大值: {{ param.maximum }}
                </span>
                <span v-if="param.enum">
                  可选值: {{ param.enum.join(', ') }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="empty-params">
            <p>该策略没有可配置的参数</p>
          </div>
        </div>

        <div class="card history-card">
          <div class="card-header">
            <h3 class="card-title">回测历史</h3>
          </div>
          <div v-if="backtestHistory.length > 0" class="history-list">
            <div
              v-for="backtest in backtestHistory"
              :key="backtest.backtest_id"
              class="history-item"
              @click="goToBacktestResult(backtest.backtest_id)"
            >
              <StatusBadge :status="backtest.status as any" />
              <span class="time">{{ formatRelativeTime(backtest.created_at) }}</span>
            </div>
          </div>
          <div v-else class="empty-history">
            <p>暂无回测记录</p>
          </div>
        </div>
      </div>
    </div>

    <ConfirmDialog
      v-model="showDeleteDialog"
      title="删除策略"
      :message="`确定要删除策略 '${strategy?.name}' 吗？此操作不可恢复。`"
      type="danger"
      :loading="deleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStrategyStore } from '@/stores/strategy'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { formatDateTime, formatRelativeTime } from '@/utils/format'
import { getStrategyCode, getStrategyBacktests } from '@/api/strategy'
import { useNotification } from '@/composables/useNotification'
import type { Strategy } from '@/types'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError } = useNotification()

const loading = ref(false)
const strategy = ref<Strategy | null>(null)
const strategyCode = ref('')
const backtestHistory = ref<{ backtest_id: string; created_at: string; status: string }[]>([])
const showDeleteDialog = ref(false)
const deleteLoading = ref(false)

async function loadStrategy() {
  loading.value = true
  try {
    strategy.value = await strategyStore.loadStrategy(props.id)

    if (strategy.value) {
      // 加载代码
      const codeResponse = await getStrategyCode(props.id)
      strategyCode.value = codeResponse.data.code

      // 加载回测历史
      const historyResponse = await getStrategyBacktests(props.id, 10)
      backtestHistory.value = historyResponse.data
    }
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.back()
}

function goToBacktest() {
  router.push({ path: '/trading/backtest', query: { strategy_id: props.id } })
}

function goToPaper() {
  router.push({ path: '/trading/paper', query: { strategy_id: props.id } })
}

function goToLive() {
  router.push({ path: '/trading/live', query: { strategy_id: props.id } })
}

function goToBacktestResult(backtestId: string) {
  router.push(`/trading/backtest/${backtestId}/result`)
}

function handleDelete() {
  showDeleteDialog.value = true
}

async function confirmDelete() {
  deleteLoading.value = true
  try {
    const success = await strategyStore.deleteStrategy(props.id)
    if (success) {
      toastSuccess('策略已删除')
      router.push('/strategy/list')
    } else {
      toastError('删除失败')
    }
  } finally {
    deleteLoading.value = false
    showDeleteDialog.value = false
  }
}

onMounted(() => {
  loadStrategy()
})
</script>

<style lang="scss" scoped>
.strategy-detail {
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

    .strategy-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .strategy-name {
      font-size: 24px;
      font-weight: 600;
      margin: 0;
    }

    .header-right {
      display: flex;
      gap: 12px;
    }
  }

  .content-grid {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 24px;
  }

  .info-card {
    .info-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }

    .info-item {
      display: flex;
      flex-direction: column;
      gap: 4px;

      .label {
        font-size: 12px;
        color: #909399;
      }

      .value {
        font-size: 14px;
        font-weight: 500;
      }
    }

    .description {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid #ebeef5;

      h4 {
        font-size: 14px;
        margin: 0 0 8px;
      }

      p {
        margin: 0;
        color: #606266;
        line-height: 1.6;
      }
    }
  }

  .code-card {
    margin-top: 24px;

    .code-preview {
      max-height: 500px;
      overflow: auto;
      background: #f5f7fa;
      padding: 16px;
      border-radius: 4px;
      font-size: 13px;
      line-height: 1.6;
    }
  }

  .params-card {
    .params-list {
      max-height: 400px;
      overflow-y: auto;
    }

    .param-item {
      padding: 12px 0;
      border-bottom: 1px solid #ebeef5;

      &:last-child {
        border-bottom: none;
      }

      .param-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
      }

      .param-name {
        font-weight: 500;
      }

      .param-description {
        font-size: 12px;
        color: #909399;
        margin: 4px 0;
      }

      .param-meta {
        font-size: 12px;
        color: #909399;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
    }

    .empty-params {
      color: #909399;
      text-align: center;
      padding: 24px 0;
    }
  }

  .history-card {
    margin-top: 24px;

    .history-list {
      max-height: 300px;
      overflow-y: auto;
    }

    .history-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 0;
      cursor: pointer;
      border-bottom: 1px solid #ebeef5;

      &:last-child {
        border-bottom: none;
      }

      &:hover {
        background: #f5f7fa;
        margin: 0 -16px;
        padding: 8px 16px;
      }

      .time {
        font-size: 12px;
        color: #909399;
      }
    }

    .empty-history {
      color: #909399;
      text-align: center;
      padding: 24px 0;
    }
  }
}
</style>

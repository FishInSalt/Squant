<template>
  <div class="strategy-list">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">策略库</h1>
        <el-radio-group v-model="statusFilter" size="small" @change="handleStatusChange">
          <el-radio-button value="active">活跃</el-radio-button>
          <el-radio-button value="archived">已归档</el-radio-button>
        </el-radio-group>
      </div>
      <div class="header-actions">
        <el-input
          v-model="searchQuery"
          placeholder="搜索策略..."
          prefix-icon="Search"
          clearable
          style="width: 240px"
          @input="handleSearch"
        />
        <el-button type="primary" @click="goToUpload">
          <el-icon><Upload /></el-icon>
          上传策略
        </el-button>
      </div>
    </div>

    <div class="strategy-grid" v-loading="loading">
      <div
        v-for="strategy in strategies"
        :key="strategy.id"
        class="strategy-card card"
        @click="goToDetail(strategy.id)"
      >
        <div class="card-header">
          <h3 class="strategy-name">{{ strategy.name }}</h3>
          <StatusBadge
            :status="strategy.status === 'active' ? 'active' : 'archived'"
          />
        </div>

        <p class="strategy-description">{{ strategy.description || '暂无描述' }}</p>

        <div class="strategy-meta">
          <span class="meta-item">
            <el-icon><Clock /></el-icon>
            {{ formatRelativeTime(strategy.updated_at) }}
          </span>
          <span class="meta-item">
            <el-icon><Document /></el-icon>
            v{{ strategy.version }}
          </span>
        </div>

        <div v-if="statusFilter === 'active'" class="card-actions" @click.stop>
          <el-button size="small" type="primary" @click="goToBacktest(strategy.id)">
            回测
          </el-button>
          <el-button size="small" @click="goToPaper(strategy.id)">
            模拟
          </el-button>
          <el-button size="small" @click="goToLive(strategy.id)">
            实盘
          </el-button>
          <el-button size="small" type="danger" @click="handleDelete(strategy)">
            删除
          </el-button>
        </div>
        <div v-else class="card-actions card-actions--archived" @click.stop>
          <span class="archived-time">归档于 {{ formatRelativeTime(strategy.updated_at) }}</span>
        </div>
      </div>
    </div>

    <div v-if="strategies.length === 0 && !loading" class="empty-state card">
      <el-icon class="empty-icon"><Document /></el-icon>
      <p class="empty-text">{{ statusFilter === 'active' ? '暂无策略' : '暂无归档策略' }}</p>
      <el-button v-if="statusFilter === 'active'" type="primary" @click="goToUpload">
        上传策略
      </el-button>
    </div>

    <div class="pagination" v-if="pagination.total > pagination.pageSize">
      <el-pagination
        v-model:current-page="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        layout="prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>

    <ConfirmDialog
      v-model="showDeleteDialog"
      title="删除策略"
      :message="`确定要删除策略 '${strategyToDelete?.name}' 吗？此操作不可恢复。`"
      type="danger"
      :loading="deleteLoading"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStrategyStore } from '@/stores/strategy'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { formatRelativeTime } from '@/utils/format'
import { useNotification } from '@/composables/useNotification'
import { getLiveSessions } from '@/api/live'
import { getPaperSessions } from '@/api/paper'
import type { Strategy } from '@/types'
import { debounce } from 'lodash-es'

const router = useRouter()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError } = useNotification()

const loading = computed(() => strategyStore.loading)
const strategies = computed(() => {
  if (!searchQuery.value) return strategyStore.strategies
  const q = searchQuery.value.toLowerCase()
  return strategyStore.strategies.filter(
    (s) => s.name.toLowerCase().includes(q) || s.description?.toLowerCase().includes(q)
  )
})
const pagination = computed(() => strategyStore.pagination)

const searchQuery = ref('')
const statusFilter = ref<'active' | 'archived'>('active')
const showDeleteDialog = ref(false)
const strategyToDelete = ref<Strategy | null>(null)
const deleteLoading = ref(false)

const handleSearch = debounce(() => {
  if (searchQuery.value) {
    // Load all strategies for complete local filtering
    strategyStore.loadStrategies({ page: 1, pageSize: 100, status: statusFilter.value })
  } else {
    // Reset to normal pagination
    strategyStore.setPage(1)
    strategyStore.loadStrategies({ status: statusFilter.value })
  }
}, 300)

function handleStatusChange() {
  searchQuery.value = ''
  strategyStore.setPage(1)
  strategyStore.loadStrategies({ status: statusFilter.value })
}

function handlePageChange(page: number) {
  strategyStore.setPage(page)
  strategyStore.loadStrategies({ status: statusFilter.value })
}

function goToUpload() {
  router.push('/strategy/upload')
}

function goToDetail(id: string) {
  router.push(`/strategy/${id}`)
}

function goToBacktest(id: string) {
  router.push({ path: '/trading/backtest', query: { strategy_id: id } })
}

function goToPaper(id: string) {
  router.push({ path: '/trading/paper', query: { strategy_id: id } })
}

function goToLive(id: string) {
  router.push({ path: '/trading/live', query: { strategy_id: id } })
}

async function handleDelete(strategy: Strategy) {
  // 检查是否有运行中的会话使用该策略
  try {
    const [liveRes, paperRes] = await Promise.all([
      getLiveSessions({ strategy_id: strategy.id, status: 'running', page: 1, page_size: 1 }),
      getPaperSessions({ strategy_id: strategy.id, status: 'running', page: 1, page_size: 1 }),
    ])
    const runningCount = (liveRes.data.total || 0) + (paperRes.data.total || 0)
    if (runningCount > 0) {
      toastError(`策略「${strategy.name}」有 ${runningCount} 个运行中的会话，请先停止后再删除`)
      return
    }
  } catch (e) {
    // 检查失败时仍允许尝试删除（后端会做最终校验）
    console.warn('Failed to check running sessions:', e)
  }

  strategyToDelete.value = strategy
  showDeleteDialog.value = true
}

async function confirmDelete() {
  if (!strategyToDelete.value) return

  deleteLoading.value = true
  try {
    const success = await strategyStore.deleteStrategy(strategyToDelete.value.id)
    if (success) {
      toastSuccess('策略已删除')
      showDeleteDialog.value = false
    } else {
      toastError('删除失败')
    }
  } finally {
    deleteLoading.value = false
  }
}

onMounted(() => {
  strategyStore.loadStrategies({ status: statusFilter.value })
})
</script>

<style lang="scss" scoped>
.strategy-list {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .header-actions {
    display: flex;
    gap: 12px;
  }

  .strategy-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }

  .strategy-card {
    cursor: pointer;
    transition: box-shadow 0.2s, transform 0.2s;

    &:hover {
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
      transform: translateY(-2px);
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }

    .strategy-name {
      font-size: 16px;
      font-weight: 600;
      margin: 0;
    }

    .strategy-description {
      font-size: 14px;
      color: #606266;
      margin: 0 0 12px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .strategy-meta {
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
      font-size: 12px;
      color: #909399;

      .meta-item {
        display: flex;
        align-items: center;
        gap: 4px;
      }
    }

    .card-actions {
      display: flex;
      gap: 8px;
      padding-top: 12px;
      border-top: 1px solid #ebeef5;

      &--archived {
        justify-content: flex-end;
      }

      .archived-time {
        font-size: 12px;
        color: #909399;
      }
    }
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 60px;

    .empty-icon {
      font-size: 48px;
      color: #dcdfe6;
      margin-bottom: 16px;
    }

    .empty-text {
      color: #909399;
      margin-bottom: 16px;
    }
  }

  .pagination {
    display: flex;
    justify-content: center;
    margin-top: 24px;
  }
}
</style>

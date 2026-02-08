<template>
  <div class="strategy-list">
    <div class="page-header">
      <h1 class="page-title">策略库</h1>
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
            :status="strategy.status === 'active' ? 'active' : 'error'"
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

        <div class="card-actions" @click.stop>
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
      </div>
    </div>

    <div v-if="strategies.length === 0 && !loading" class="empty-state card">
      <el-icon class="empty-icon"><Document /></el-icon>
      <p class="empty-text">暂无策略</p>
      <el-button type="primary" @click="goToUpload">
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
import type { Strategy } from '@/types'
import { debounce } from 'lodash-es'

const router = useRouter()
const strategyStore = useStrategyStore()
const { toastSuccess, toastError } = useNotification()

const loading = computed(() => strategyStore.loading)
const strategies = computed(() => strategyStore.strategies)
const pagination = computed(() => strategyStore.pagination)

const searchQuery = ref('')
const showDeleteDialog = ref(false)
const strategyToDelete = ref<Strategy | null>(null)
const deleteLoading = ref(false)

const handleSearch = debounce(() => {
  strategyStore.setSearchQuery(searchQuery.value)
  strategyStore.setPage(1)
  strategyStore.loadStrategies()
}, 300)

function handlePageChange(page: number) {
  strategyStore.setPage(page)
  strategyStore.loadStrategies()
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

function handleDelete(strategy: Strategy) {
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
  strategyStore.loadStrategies()
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

  .page-title {
    font-size: 20px;
    font-weight: 600;
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

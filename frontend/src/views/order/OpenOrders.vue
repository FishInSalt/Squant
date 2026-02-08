<template>
  <div class="open-orders">
    <div class="page-header">
      <h1 class="page-title">当前挂单</h1>
      <div class="header-actions">
        <el-button type="danger" :disabled="selectedOrders.length === 0" @click="cancelSelected">
          取消选中 ({{ selectedOrders.length }})
        </el-button>
        <el-button type="danger" @click="cancelAll">
          取消全部
        </el-button>
      </div>
    </div>

    <div class="filter-bar card">
      <el-form :inline="true" :model="filter">
        <el-form-item label="交易所">
          <el-select v-model="filter.exchange" placeholder="全部" clearable style="width: 140px">
            <el-option
              v-for="e in exchanges"
              :key="e"
              :label="formatExchangeName(e)"
              :value="e"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="交易对">
          <el-input v-model="filter.symbol" placeholder="搜索交易对" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="filter.side" placeholder="全部" clearable style="width: 100px">
            <el-option label="买入" value="buy" />
            <el-option label="卖出" value="sell" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadOrders">查询</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="orders-table card">
      <el-table
        :data="orders"
        v-loading="loading"
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="50" />

        <el-table-column prop="symbol" label="交易对" width="130">
          <template #default="{ row }">
            <div class="symbol-cell">
              <span class="symbol">{{ row.symbol }}</span>
              <el-tag size="small" type="info">{{ formatExchangeName(row.exchange) }}</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="side" label="方向" width="80">
          <template #default="{ row }">
            <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
              {{ formatOrderSide(row.side) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="type" label="类型" width="80">
          <template #default="{ row }">
            {{ formatOrderType(row.type) }}
          </template>
        </el-table-column>

        <el-table-column prop="price" label="价格" width="120" align="right">
          <template #default="{ row }">
            {{ row.price ? formatPrice(row.price) : '市价' }}
          </template>
        </el-table-column>

        <el-table-column prop="amount" label="数量" width="120" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.amount, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="filled" label="已成交" width="120" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.filled, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="remaining_amount" label="剩余" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.remaining_amount, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <StatusBadge :status="row.status" />
          </template>
        </el-table-column>

        <el-table-column prop="strategy_name" label="策略" width="120">
          <template #default="{ row }">
            {{ row.strategy_name || '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link @click="cancelOrder(row.id)">
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useMarketStore } from '@/stores/market'
import StatusBadge from '@/components/common/StatusBadge.vue'
import {
  formatExchangeName,
  formatOrderSide,
  formatOrderType,
  formatPrice,
  formatNumber,
  formatDateTime,
} from '@/utils/format'
import { getOpenOrders, cancelOrder as apiCancelOrder, cancelOrders, cancelAllOrders } from '@/api/order'
import { useNotification } from '@/composables/useNotification'
import type { Order } from '@/types'

const marketStore = useMarketStore()
const { toastSuccess, toastError, confirmDanger } = useNotification()

const loading = ref(false)
const orders = ref<Order[]>([])
const selectedOrders = ref<Order[]>([])

const filter = reactive({
  exchange: '',
  symbol: '',
  side: '',
})

const exchanges = computed(() => marketStore.exchanges)

async function loadOrders() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (filter.exchange) params.exchange = filter.exchange
    if (filter.symbol) params.symbol = filter.symbol
    if (filter.side) params.side = filter.side

    const response = await getOpenOrders(params as any)
    orders.value = response.data
  } catch (error) {
    console.error('Failed to load orders:', error)
  } finally {
    loading.value = false
  }
}

function handleSelectionChange(selection: Order[]) {
  selectedOrders.value = selection
}

async function cancelOrder(id: string) {
  const confirmed = await confirmDanger('确定要取消该订单吗？')
  if (!confirmed) return

  try {
    await apiCancelOrder(id)
    toastSuccess('订单已取消')
    loadOrders()
  } catch (error) {
    toastError('取消失败')
  }
}

async function cancelSelected() {
  if (selectedOrders.value.length === 0) return

  const confirmed = await confirmDanger(`确定要取消选中的 ${selectedOrders.value.length} 个订单吗？`)
  if (!confirmed) return

  try {
    const ids = selectedOrders.value.map((o) => o.id)
    await cancelOrders(ids)
    toastSuccess('订单已取消')
    loadOrders()
  } catch (error) {
    toastError('取消失败')
  }
}

async function cancelAll() {
  if (orders.value.length === 0) return

  const confirmed = await confirmDanger(`确定要取消全部 ${orders.value.length} 个挂单吗？`)
  if (!confirmed) return

  try {
    const params: Record<string, unknown> = {}
    if (filter.exchange) params.exchange = filter.exchange
    if (filter.symbol) params.symbol = filter.symbol

    await cancelAllOrders(params as any)
    toastSuccess('已取消全部挂单')
    loadOrders()
  } catch (error) {
    toastError('取消失败')
  }
}

onMounted(() => {
  marketStore.loadExchanges()
  loadOrders()
})
</script>

<style lang="scss" scoped>
.open-orders {
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

  .header-actions {
    display: flex;
    gap: 12px;
  }

  .filter-bar {
    margin-bottom: 16px;
    padding: 16px;

    :deep(.el-form-item) {
      margin-bottom: 0;
    }
  }

  .symbol-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;

    .symbol {
      font-weight: 500;
    }
  }
}
</style>

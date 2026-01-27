<template>
  <div class="order-history">
    <div class="page-header">
      <h1 class="page-title">历史订单</h1>
      <el-button @click="exportOrders">
        <el-icon><Download /></el-icon>
        导出
      </el-button>
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
        <el-form-item label="状态">
          <el-select v-model="filter.status" placeholder="全部" clearable style="width: 120px">
            <el-option
              v-for="s in statusOptions"
              :key="s.value"
              :label="s.label"
              :value="s.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filter.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadOrders">查询</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="orders-table card">
      <el-table :data="orders" v-loading="loading" stripe>
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

        <el-table-column prop="price" label="委托价" width="120" align="right">
          <template #default="{ row }">
            {{ row.price ? formatPrice(row.price) : '市价' }}
          </template>
        </el-table-column>

        <el-table-column prop="avg_fill_price" label="成交均价" width="120" align="right">
          <template #default="{ row }">
            {{ row.avg_fill_price ? formatPrice(row.avg_fill_price) : '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="quantity" label="委托数量" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.quantity, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="filled_quantity" label="成交数量" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.filled_quantity, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="commission" label="手续费" width="100" align="right">
          <template #default="{ row }">
            {{ row.commission ? formatNumber(row.commission, 6) : '-' }}
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

        <el-table-column prop="filled_at" label="成交时间" width="160">
          <template #default="{ row }">
            {{ row.filled_at ? formatDateTime(row.filled_at) : '-' }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :total="pagination.total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadOrders"
          @current-change="loadOrders"
        />
      </div>
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
import { ORDER_STATUS_OPTIONS } from '@/utils/constants'
import { getOrderHistory, exportOrders as apiExportOrders } from '@/api/order'
import { useNotification } from '@/composables/useNotification'
import type { Order } from '@/types'

const marketStore = useMarketStore()
const { toastSuccess, toastError } = useNotification()

const loading = ref(false)
const orders = ref<Order[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const filter = reactive({
  exchange: '',
  symbol: '',
  side: '',
  status: '',
  dateRange: [] as string[],
})

const exchanges = computed(() => marketStore.exchanges)
const statusOptions = ORDER_STATUS_OPTIONS

async function loadOrders() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filter.exchange) params.exchange = filter.exchange
    if (filter.symbol) params.symbol = filter.symbol
    if (filter.side) params.side = filter.side
    if (filter.status) params.status = filter.status
    if (filter.dateRange.length === 2) {
      params.start_date = filter.dateRange[0]
      params.end_date = filter.dateRange[1]
    }

    const response = await getOrderHistory(params as any)
    orders.value = response.data.items
    pagination.total = response.data.total
  } catch (error) {
    console.error('Failed to load orders:', error)
  } finally {
    loading.value = false
  }
}

async function exportOrders() {
  try {
    const params: Record<string, unknown> = {}
    if (filter.exchange) params.exchange = filter.exchange
    if (filter.symbol) params.symbol = filter.symbol
    if (filter.side) params.side = filter.side
    if (filter.status) params.status = filter.status
    if (filter.dateRange.length === 2) {
      params.start_date = filter.dateRange[0]
      params.end_date = filter.dateRange[1]
    }

    const response = await apiExportOrders(params as any, 'csv')
    // 验证下载 URL 是否来自可信域名
    const downloadUrl = response.data.download_url
    try {
      const url = new URL(downloadUrl, window.location.origin)
      const allowedHosts = [window.location.host, 'localhost']
      if (!allowedHosts.some(host => url.host === host || url.host.endsWith('.' + host))) {
        throw new Error('Invalid download URL')
      }
      window.open(url.href, '_blank')
      toastSuccess('导出成功')
    } catch {
      toastError('下载链接无效')
    }
  } catch (error) {
    toastError('导出失败')
  }
}

onMounted(() => {
  marketStore.loadExchanges()
  loadOrders()
})
</script>

<style lang="scss" scoped>
.order-history {
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

  .symbol-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;

    .symbol {
      font-weight: 500;
    }
  }

  .pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
  }
}
</style>

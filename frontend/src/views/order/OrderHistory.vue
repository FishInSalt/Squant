<template>
  <div class="order-history">
    <div class="page-header">
      <h1 class="page-title">历史订单</h1>
      <div class="header-actions">
        <el-button :icon="Download" @click="exportCSV">导出</el-button>
      </div>
    </div>

    <div class="filter-bar card">
      <el-form :inline="true" :model="filter">
        <el-form-item label="账户">
          <el-select v-model="filter.account_id" placeholder="全部" clearable style="width: 200px">
            <el-option
              v-for="acc in accounts"
              :key="acc.id"
              :label="acc.name"
              :value="acc.id"
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
      <el-table :data="orders" v-loading="loading" stripe style="cursor: pointer;" @row-click="handleRowClick">
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

        <el-table-column prop="avg_price" label="成交均价" width="120" align="right">
          <template #default="{ row }">
            {{ row.avg_price ? formatPrice(row.avg_price) : '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="amount" label="委托数量" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.amount, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="filled" label="成交数量" width="100" align="right">
          <template #default="{ row }">
            {{ formatNumber(row.filled, 4) }}
          </template>
        </el-table-column>

        <el-table-column prop="commission" label="手续费" width="100" align="right">
          <template #default="{ row }">
            {{ row.commission ? formatNumber(row.commission, 6) : '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <StatusBadge :status="row.status" context="order" />
          </template>
        </el-table-column>

        <el-table-column prop="account_name" label="账户" width="120">
          <template #default="{ row }">
            {{ row.account_name || '-' }}
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

        <el-table-column prop="updated_at" label="更新时间" width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
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

    <el-dialog v-model="detailVisible" title="订单详情" width="750px" destroy-on-close>
      <template v-if="selectedOrder">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="交易对">{{ selectedOrder.symbol }}</el-descriptions-item>
          <el-descriptions-item label="账户">{{ selectedOrder.account_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="交易所">{{ formatExchangeName(selectedOrder.exchange) }}</el-descriptions-item>
          <el-descriptions-item label="方向">
            <el-tag :type="selectedOrder.side === 'buy' ? 'success' : 'danger'" size="small">
              {{ formatOrderSide(selectedOrder.side) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="类型">{{ formatOrderType(selectedOrder.type) }}</el-descriptions-item>
          <el-descriptions-item label="委托价">{{ selectedOrder.price ? formatPrice(selectedOrder.price) : '市价' }}</el-descriptions-item>
          <el-descriptions-item label="成交均价">{{ selectedOrder.avg_price ? formatPrice(selectedOrder.avg_price) : '-' }}</el-descriptions-item>
          <el-descriptions-item label="委托数量">{{ formatNumber(selectedOrder.amount, 4) }}</el-descriptions-item>
          <el-descriptions-item label="成交数量">{{ formatNumber(selectedOrder.filled, 4) }}</el-descriptions-item>
          <el-descriptions-item label="剩余数量">{{ formatNumber(selectedOrder.remaining_amount, 4) }}</el-descriptions-item>
          <el-descriptions-item label="手续费">
            {{ selectedOrder.commission ? `${formatNumber(selectedOrder.commission, 6)} ${selectedOrder.commission_asset || ''}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <StatusBadge :status="selectedOrder.status" context="order" />
          </el-descriptions-item>
          <el-descriptions-item label="策略">{{ selectedOrder.strategy_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{ formatDateTime(selectedOrder.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间" :span="2">{{ formatDateTime(selectedOrder.updated_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="selectedOrder.reject_reason" label="拒绝原因" :span="2">{{ selectedOrder.reject_reason }}</el-descriptions-item>
          <el-descriptions-item v-if="selectedOrder.exchange_oid" label="交易所订单ID" :span="2">{{ selectedOrder.exchange_oid }}</el-descriptions-item>
        </el-descriptions>

        <template v-if="selectedOrder.trades && selectedOrder.trades.length > 0">
          <h4 style="margin: 16px 0 8px;">逐笔成交</h4>
          <el-table :data="selectedOrder.trades" size="small" border>
            <el-table-column label="成交ID" width="130">
              <template #default="{ row }">
                {{ row.exchange_tid ? row.exchange_tid.substring(0, 12) + '...' : '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="price" label="价格" width="120" />
            <el-table-column prop="amount" label="数量" width="100" />
            <el-table-column label="手续费" width="120">
              <template #default="{ row }">
                {{ row.fee }} {{ row.fee_currency || '' }}
              </template>
            </el-table-column>
            <el-table-column prop="taker_or_maker" label="类型" width="80" />
            <el-table-column label="时间" min-width="170">
              <template #default="{ row }">
                {{ new Date(row.timestamp).toLocaleString() }}
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="selectedOrder.corrections && selectedOrder.corrections.length > 0">
          <h4 style="margin: 16px 0 8px;">修正记录</h4>
          <el-timeline>
            <el-timeline-item
              v-for="(c, i) in selectedOrder.corrections"
              :key="i"
              :timestamp="new Date(c.timestamp).toLocaleString()"
              placement="top"
            >
              <p style="margin: 0;">{{ c.reason }}</p>
              <p v-for="(ch, j) in c.changes" :key="j" style="margin: 2px 0; color: #666; font-size: 12px;">
                {{ ch.field }}: {{ ch.before }} → {{ ch.after }}
              </p>
            </el-timeline-item>
          </el-timeline>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Download } from '@element-plus/icons-vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import {
  formatExchangeName,
  formatOrderSide,
  formatOrderType,
  formatOrderStatus,
  formatPrice,
  formatNumber,
  formatDateTime,
} from '@/utils/format'
import { ORDER_STATUS_OPTIONS } from '@/utils/constants'
import { getOrderHistory } from '@/api/order'
import { getAccounts } from '@/api/account'
import { useNotification } from '@/composables/useNotification'
import type { Order, ExchangeAccount } from '@/types'

const { toastError } = useNotification()

const loading = ref(false)
const orders = ref<Order[]>([])
const accounts = ref<ExchangeAccount[]>([])
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})

const filter = reactive({
  account_id: '',
  symbol: '',
  side: '',
  status: '',
  dateRange: [] as string[],
})

const statusOptions = ORDER_STATUS_OPTIONS

async function loadOrders() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filter.account_id) params.account_id = filter.account_id
    if (filter.symbol) params.symbol = filter.symbol
    if (filter.side) params.side = filter.side
    if (filter.status) params.status = filter.status
    if (filter.dateRange.length === 2) {
      params.start_time = filter.dateRange[0]
      params.end_time = filter.dateRange[1]
    }

    const response = await getOrderHistory(params as any)
    orders.value = response.data.items
    pagination.total = response.data.total
  } catch (error) {
    console.error('Failed to load orders:', error)
    toastError('加载历史订单失败')
  } finally {
    loading.value = false
  }
}

const selectedOrder = ref<Order | null>(null)
const detailVisible = ref(false)

function handleRowClick(row: Order) {
  selectedOrder.value = row
  detailVisible.value = true
}

function exportCSV() {
  if (!orders.value.length) {
    toastError('没有可导出的数据')
    return
  }

  const headers = ['时间', '交易对', '方向', '价格', '数量', '状态']
  const rows = orders.value.map((o) => [
    formatDateTime(o.created_at),
    o.symbol,
    formatOrderSide(o.side),
    o.price ? String(o.price) : '市价',
    String(o.amount),
    formatOrderStatus(o.status),
  ])

  const csvContent = [headers, ...rows]
    .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const BOM = '\uFEFF'
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const date = new Date().toISOString().slice(0, 10)
  const link = document.createElement('a')
  link.href = url
  link.download = `order-history-${date}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function loadAccounts() {
  try {
    const response = await getAccounts()
    accounts.value = response.data
  } catch (error) {
    console.error('Failed to load accounts:', error)
  }
}

onMounted(() => {
  loadAccounts()
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

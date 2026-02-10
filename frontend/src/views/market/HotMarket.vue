<template>
  <div class="hot-market">
    <div class="page-header">
      <h1 class="page-title">热门行情</h1>
      <div class="header-actions">
        <el-tooltip
          v-if="wsServiceUnavailable"
          content="后端无法连接交易所 WebSocket，实时数据不可用。数据通过 REST API 获取。"
          placement="bottom"
        >
          <el-tag type="warning" size="small">数据延迟</el-tag>
        </el-tooltip>
        <el-tag v-else-if="wsExchangeSwitching" type="warning" size="small">
          切换中...
        </el-tag>
        <el-tag v-else :type="wsConnected ? 'success' : 'danger'" size="small">
          {{ wsConnected ? '实时' : '离线' }}
        </el-tag>
        <el-select
          :model-value="selectedExchange"
          placeholder="选择交易所"
          style="width: 120px"
          :disabled="exchangeSwitching"
          :loading="exchangeSwitching"
          @change="handleExchangeChange"
        >
          <el-option
            v-for="ex in supportedExchanges"
            :key="ex"
            :label="formatExchangeName(ex)"
            :value="ex"
          />
        </el-select>
        <el-input
          v-model="searchQuery"
          placeholder="搜索交易对..."
          prefix-icon="Search"
          clearable
          style="width: 200px"
        />
      </div>
    </div>

    <el-alert
      v-if="loadError"
      title="无法获取行情数据"
      type="error"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    >
      <el-button type="primary" link @click="loadData">重试</el-button>
    </el-alert>

    <div class="card">
      <el-table
        ref="tableRef"
        :data="paginatedTickers"
        :row-key="(row: Ticker) => `${row.exchange}:${row.symbol}`"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="handleRowClick"
        @sort-change="handleSortChange"
      >
        <el-table-column prop="symbol" label="交易对" width="150" fixed sortable="custom">
          <template #default="{ row }">
            <div class="symbol-cell">
              <span class="symbol-name">{{ row.symbol }}</span>
              <el-button
                :icon="isInWatchlist(row.exchange, row.symbol) ? 'StarFilled' : 'Star'"
                link
                :type="isInWatchlist(row.exchange, row.symbol) ? 'warning' : 'default'"
                @click.stop="toggleWatchlist(row)"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="last_price" label="最新价" width="140" align="right" sortable="custom">
          <template #default="{ row }">
            <PriceCell
              :value="row.last_price"
              :change="row.change_24h"
            />
          </template>
        </el-table-column>

        <el-table-column prop="change_percent_24h" label="24h涨跌" width="120" align="right" sortable="custom">
          <template #default="{ row }">
            <span :class="getChangeClass(row.change_percent_24h)">
              {{ formatChangePercent(row.change_percent_24h) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="high_24h" label="24h最高" width="140" align="right" sortable="custom">
          <template #default="{ row }">
            {{ formatPrice(row.high_24h) }}
          </template>
        </el-table-column>

        <el-table-column prop="low_24h" label="24h最低" width="140" align="right" sortable="custom">
          <template #default="{ row }">
            {{ formatPrice(row.low_24h) }}
          </template>
        </el-table-column>

        <el-table-column prop="volume_24h" label="24h成交量" width="140" align="right" sortable="custom">
          <template #default="{ row }">
            {{ formatVolume(row.volume_24h) }}
          </template>
        </el-table-column>

        <el-table-column prop="quote_volume_24h" label="24h成交额" width="150" align="right" sortable="custom">
          <template #default="{ row }">
            {{ formatQuoteVolume(row.quote_volume_24h) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="goToChart(row)">
              K线
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="filteredTickers.length"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useMarketStore } from '@/stores/market'
import { useWebSocketStore } from '@/stores/websocket'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatPrice, formatVolume, formatExchangeName } from '@/utils/format'
import type { Ticker } from '@/types'

const router = useRouter()
const marketStore = useMarketStore()
const wsStore = useWebSocketStore()

const tableRef = ref()
const searchQuery = ref('')
const loading = ref(false)
const loadError = ref(false)
const sortProp = ref('quote_volume_24h')
const sortOrder = ref<'ascending' | 'descending'>('descending')
const currentPage = ref(1)
const pageSize = ref(50)

// WebSocket 连接状态
const wsConnected = computed(() => wsStore.isConnected)
const wsServiceUnavailable = computed(() => wsStore.serviceUnavailable)
const wsExchangeSwitching = computed(() => wsStore.exchangeSwitching)

// Exchange state from store (readonly - changes handled by @change event)
const selectedExchange = computed(() => marketStore.currentExchange)
const supportedExchanges = computed(() => marketStore.supportedExchanges)
const exchangeSwitching = computed(() => marketStore.exchangeSwitching)
const tickers = computed(() => marketStore.tickerList)
const isInWatchlist = computed(() => marketStore.isInWatchlist)

// 格式化涨跌幅
function formatChangePercent(value: number): string {
  if (value === 0 || isNaN(value)) return '0.00%'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

// 格式化成交额
function formatQuoteVolume(value: number | string | null | undefined): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (!num || isNaN(num) || num === 0) return '0'
  if (num >= 1e9) return `${(num / 1e9).toFixed(2)}B`
  if (num >= 1e6) return `${(num / 1e6).toFixed(2)}M`
  if (num >= 1e3) return `${(num / 1e3).toFixed(2)}K`
  return num.toFixed(2)
}

// 获取涨跌颜色类
function getChangeClass(value: number): string {
  if (value > 0) return 'price-up'
  if (value < 0) return 'price-down'
  return 'price-neutral'
}

// 判断是否为 USD 类计价货币
function isUsdQuote(symbol: string): boolean {
  const quote = symbol.split('/')[1]?.toUpperCase() || ''
  return quote === 'USDT' || quote === 'USD' || quote === 'USDC'
}

// 过滤和排序后的数据
const filteredTickers = computed(() => {
  let result = [...tickers.value]

  // 过滤：只保留 USD 类计价货币且成交额大于 0 的交易对
  result = result.filter((t) => isUsdQuote(t.symbol) && t.quote_volume_24h > 0)

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toUpperCase()
    result = result.filter((t) => t.symbol.toUpperCase().includes(query))
  }

  // 排序 - 始终按 sortProp 排序
  const prop = sortProp.value as keyof Ticker
  const isAsc = sortOrder.value === 'ascending'

  result.sort((a, b) => {
    const aVal = a[prop]
    const bVal = b[prop]

    // 字符串排序（交易对名称）
    if (prop === 'symbol') {
      const comparison = String(aVal).localeCompare(String(bVal))
      return isAsc ? comparison : -comparison
    }

    // 数字排序 - 确保使用数字比较
    const aNum = typeof aVal === 'number' ? aVal : (parseFloat(String(aVal)) || 0)
    const bNum = typeof bVal === 'number' ? bVal : (parseFloat(String(bVal)) || 0)

    // 降序：大的在前；升序：小的在前
    return isAsc ? (aNum - bNum) : (bNum - aNum)
  })

  return result
})

// 分页后的数据
const paginatedTickers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredTickers.value.slice(start, end)
})

// 当前页需要订阅的 symbols
const subscribedSymbols = computed(() => {
  return paginatedTickers.value.map((t) => t.symbol)
})

async function loadData() {
  loading.value = true
  loadError.value = false
  try {
    await marketStore.loadAllTickers()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function handleExchangeChange(exchange: string | number | boolean | undefined) {
  if (typeof exchange !== 'string') return
  currentPage.value = 1
  loading.value = true
  try {
    await marketStore.switchExchange(exchange)
    // WebSocket will automatically reconnect to new exchange via backend
    updateWsSubscriptions()
    ElMessage.success(`已切换到 ${formatExchangeName(exchange)}`)
  } catch (error: unknown) {
    console.error('Failed to switch exchange:', error)
    // Extract error message from axios error or generic Error
    let errorMsg = '未知错误'
    if (error && typeof error === 'object') {
      const axiosError = error as { response?: { data?: { message?: string } }; message?: string }
      errorMsg = axiosError.response?.data?.message || axiosError.message || '未知错误'
    }
    // Note: API interceptor already shows a generic error, this provides more context
    ElMessage.error(`切换到 ${formatExchangeName(exchange)} 失败: ${errorMsg}`)
  } finally {
    loading.value = false
  }
}

function handleSortChange({ prop, order }: { prop: string; order: 'ascending' | 'descending' | null }) {
  sortProp.value = prop || 'quote_volume_24h'
  sortOrder.value = order || 'descending'
  currentPage.value = 1
}

function handleSizeChange() {
  currentPage.value = 1
}

function handleCurrentChange() {
  // 页码变化时更新 WebSocket 订阅
  updateWsSubscriptions()
}

function handleRowClick(row: Ticker) {
  goToChart(row)
}

function goToChart(row: Ticker) {
  router.push({
    name: 'ChartDetail',
    params: { exchange: row.exchange, symbol: row.symbol },
  })
}

function toggleWatchlist(row: Ticker) {
  if (isInWatchlist.value(row.exchange, row.symbol)) {
    marketStore.removeFromWatchlist(row.exchange, row.symbol)
  } else {
    marketStore.addToWatchlist(row.exchange, row.symbol)
  }
}

// WebSocket 订阅管理
let unsubscribeWs: (() => void) | null = null

function updateWsSubscriptions() {
  // 取消之前的订阅
  if (unsubscribeWs) {
    unsubscribeWs()
    unsubscribeWs = null
  }

  // 订阅当前页的 symbols
  const symbols = subscribedSymbols.value
  if (symbols.length > 0) {
    unsubscribeWs = wsStore.subscribeToTickers(symbols)
  }
}

// 监听当前页 symbol 列表变化，更新订阅
// 仅在 symbol 集合真正变化时才重订阅（避免 ticker 数据更新触发无意义的全量重订阅）
let lastSubscribedKey = ''
watch(subscribedSymbols, (symbols) => {
  const key = symbols.join(',')
  if (key === lastSubscribedKey) return
  lastSubscribedKey = key
  updateWsSubscriptions()
})

// 当搜索变化时，重置到第一页
watch(searchQuery, () => {
  currentPage.value = 1
})

onMounted(async () => {
  // 先加载当前交易所配置
  await marketStore.loadCurrentExchange()

  // 加载自选列表（用于显示星标状态）
  await marketStore.loadWatchlist()

  // 加载初始数据
  await loadData()

  // 等待下一个tick确保表格已渲染
  await nextTick()

  // 确保表格显示正确的排序状态
  if (tableRef.value) {
    tableRef.value.sort(sortProp.value, sortOrder.value)
  }

  // 连接 WebSocket 并订阅
  wsStore.connect()
  updateWsSubscriptions()

  // Start REST API polling as fallback for infrequent WebSocket updates
  // OKX doesn't send frequent updates for less active pairs
  marketStore.startPolling()
})

onUnmounted(() => {
  if (unsubscribeWs) {
    unsubscribeWs()
  }
  // Stop polling when leaving the page
  marketStore.stopPolling()
})
</script>

<style lang="scss" scoped>
.hot-market {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
  }

  .header-actions {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }

  .symbol-cell {
    display: flex;
    align-items: center;
    gap: 8px;

    .symbol-name {
      font-weight: 500;
    }
  }

  .pagination-wrapper {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #ebeef5;
  }

  .price-up {
    color: #00c853;
    font-weight: 500;
  }

  .price-down {
    color: #ff1744;
    font-weight: 500;
  }

  .price-neutral {
    color: #909399;
  }

  :deep(.el-table__row) {
    cursor: pointer;
  }

  // 排序图标样式优化
  :deep(.el-table .caret-wrapper) {
    height: 24px;
  }

  :deep(.el-table .sort-caret) {
    border-width: 4px;
  }

  :deep(.el-table .ascending .sort-caret.ascending) {
    border-bottom-color: var(--el-color-primary);
  }

  :deep(.el-table .descending .sort-caret.descending) {
    border-top-color: var(--el-color-primary);
  }
}
</style>

<template>
  <div class="hot-market">
    <div class="page-header">
      <h1 class="page-title">热门行情</h1>
      <div class="header-actions">
        <el-select
          v-model="selectedExchange"
          placeholder="选择交易所"
          style="width: 150px"
          @change="handleExchangeChange"
        >
          <el-option
            v-for="exchange in exchanges"
            :key="exchange"
            :label="formatExchangeName(exchange)"
            :value="exchange"
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

    <div class="card">
      <el-table
        :data="filteredTickers"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="handleRowClick"
      >
        <el-table-column prop="symbol" label="交易对" width="150" fixed>
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

        <el-table-column prop="last_price" label="最新价" width="140" align="right">
          <template #default="{ row }">
            <PriceCell
              :value="row.last_price"
              :change="row.change_24h"
            />
          </template>
        </el-table-column>

        <el-table-column prop="change_percent_24h" label="24h涨跌" width="120" align="right">
          <template #default="{ row }">
            <PriceCell
              :value="row.change_percent_24h"
              :change="row.change_24h"
              :decimals="2"
              show-sign
            />
          </template>
        </el-table-column>

        <el-table-column prop="high_24h" label="24h最高" width="140" align="right">
          <template #default="{ row }">
            {{ formatPrice(row.high_24h) }}
          </template>
        </el-table-column>

        <el-table-column prop="low_24h" label="24h最低" width="140" align="right">
          <template #default="{ row }">
            {{ formatPrice(row.low_24h) }}
          </template>
        </el-table-column>

        <el-table-column prop="volume_24h" label="24h成交量" width="140" align="right">
          <template #default="{ row }">
            {{ formatVolume(row.volume_24h) }}
          </template>
        </el-table-column>

        <el-table-column prop="quote_volume_24h" label="24h成交额" width="140" align="right">
          <template #default="{ row }">
            {{ formatLargeNumber(row.quote_volume_24h) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="goToChart(row)">
              K线
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMarketStore } from '@/stores/market'
import { useWebSocketStore } from '@/stores/websocket'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatPrice, formatVolume, formatLargeNumber, formatExchangeName } from '@/utils/format'
import type { Ticker } from '@/types'

const router = useRouter()
const marketStore = useMarketStore()
const wsStore = useWebSocketStore()

const selectedExchange = ref('binance')
const searchQuery = ref('')
const loading = ref(false)

const exchanges = computed(() => marketStore.exchanges)
const tickers = computed(() => marketStore.tickerList)
const isInWatchlist = computed(() => marketStore.isInWatchlist)

const filteredTickers = computed(() => {
  let result = tickers.value.filter((t) => t.exchange === selectedExchange.value)

  if (searchQuery.value) {
    const query = searchQuery.value.toUpperCase()
    result = result.filter((t) => t.symbol.toUpperCase().includes(query))
  }

  // 按成交额排序
  return result.sort((a, b) => b.quote_volume_24h - a.quote_volume_24h)
})

async function loadData() {
  loading.value = true
  try {
    await marketStore.loadHotTickers(selectedExchange.value, 100)
  } finally {
    loading.value = false
  }
}

function handleExchangeChange() {
  loadData()
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

// 订阅行情更新
let unsubscribe: (() => void) | null = null

onMounted(async () => {
  if (exchanges.value.length === 0) {
    await marketStore.loadExchanges()
  }
  if (exchanges.value.length > 0 && !exchanges.value.includes(selectedExchange.value)) {
    selectedExchange.value = exchanges.value[0]
  }

  await loadData()

  // 订阅 WebSocket 更新
  wsStore.connect()
  const symbols = filteredTickers.value.slice(0, 50).map((t) => t.symbol)
  unsubscribe = wsStore.subscribeToTickers(selectedExchange.value, symbols)
})

onUnmounted(() => {
  if (unsubscribe) {
    unsubscribe()
  }
})
</script>

<style lang="scss" scoped>
.hot-market {
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

  .symbol-cell {
    display: flex;
    align-items: center;
    gap: 8px;

    .symbol-name {
      font-weight: 500;
    }
  }

  :deep(.el-table__row) {
    cursor: pointer;
  }
}
</style>

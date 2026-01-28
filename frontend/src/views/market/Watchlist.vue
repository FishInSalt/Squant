<template>
  <div class="watchlist">
    <div class="page-header">
      <h1 class="page-title">自选行情</h1>
    </div>

    <div class="card" v-if="watchlist.length > 0">
      <el-table
        :data="watchlistTickers"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="handleRowClick"
      >
        <el-table-column prop="symbol" label="交易对" width="150" fixed>
          <template #default="{ row }">
            <div class="symbol-cell">
              <span class="symbol-name">{{ row.symbol }}</span>
              <el-tag size="small" type="info">{{ formatExchangeName(row.exchange) }}</el-tag>
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

        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="goToChart(row)">
              K线
            </el-button>
            <el-button type="danger" link @click.stop="removeFromWatchlist(row)">
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else class="empty-state card">
      <el-icon class="empty-icon"><Star /></el-icon>
      <p class="empty-text">暂无自选交易对</p>
      <el-button type="primary" @click="goToHotMarket">
        去添加
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMarketStore } from '@/stores/market'
import { useWebSocketStore } from '@/stores/websocket'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatPrice, formatVolume, formatExchangeName } from '@/utils/format'
import type { Ticker } from '@/types'

const router = useRouter()
const marketStore = useMarketStore()
const wsStore = useWebSocketStore()

const loading = ref(false)

const watchlist = computed(() => marketStore.watchlist)
const watchlistTickers = computed(() => marketStore.watchlistTickers)

async function loadWatchlistData() {
  if (watchlist.value.length === 0) return

  loading.value = true
  try {
    // 收集所有自选的交易对
    const symbols = watchlist.value.map((item) => item.symbol)
    await marketStore.loadTickers(symbols)
  } finally {
    loading.value = false
  }
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

function removeFromWatchlist(row: Ticker) {
  marketStore.removeFromWatchlist(row.exchange, row.symbol)
}

function goToHotMarket() {
  router.push('/market/hot')
}

// 订阅行情更新
let unsubscribe: (() => void) | null = null

onMounted(async () => {
  await loadWatchlistData()

  // 订阅 WebSocket 更新
  wsStore.connect()
  const symbols = watchlist.value.map((item) => item.symbol)
  if (symbols.length > 0) {
    unsubscribe = wsStore.subscribeToTickers(symbols)
  }
})

onUnmounted(() => {
  if (unsubscribe) {
    unsubscribe()
  }
})
</script>

<style lang="scss" scoped>
.watchlist {
  .page-header {
    margin-bottom: 16px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 600;
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
}
</style>

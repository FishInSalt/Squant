<template>
  <div class="chart-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button icon="ArrowLeft" @click="goBack">返回</el-button>
        <div class="symbol-info">
          <h1 class="symbol-name">{{ symbol }}</h1>
          <el-tag size="small" type="info">{{ formatExchangeName(exchange) }}</el-tag>
          <el-button
            :icon="isInWatchlist ? 'StarFilled' : 'Star'"
            :type="isInWatchlist ? 'warning' : 'default'"
            circle
            @click="toggleWatchlist"
          />
        </div>
      </div>
      <div class="header-right">
        <el-button-group>
          <el-button
            v-for="tf in timeframeOptions"
            :key="tf.value"
            :type="selectedTimeframe === tf.value ? 'primary' : 'default'"
            @click="selectedTimeframe = tf.value"
          >
            {{ tf.label }}
          </el-button>
        </el-button-group>
      </div>
    </div>

    <div class="price-bar card" v-if="ticker">
      <div class="price-item main">
        <PriceCell
          :value="ticker.last_price"
          :change="ticker.change_24h"
          class="current-price"
        />
        <div class="change">
          <PriceCell
            :value="ticker.change_24h"
            :change="ticker.change_24h"
            show-sign
          />
          <span class="separator">/</span>
          <PriceCell
            :value="ticker.change_percent_24h"
            :change="ticker.change_24h"
            :decimals="2"
            show-sign
          />
        </div>
      </div>
      <div class="price-item">
        <span class="label">24h最高</span>
        <span class="value">{{ formatPrice(ticker.high_24h) }}</span>
      </div>
      <div class="price-item">
        <span class="label">24h最低</span>
        <span class="value">{{ formatPrice(ticker.low_24h) }}</span>
      </div>
      <div class="price-item">
        <span class="label">24h成交量</span>
        <span class="value">{{ formatVolume(ticker.volume_24h) }}</span>
      </div>
      <div class="price-item">
        <span class="label">24h成交额</span>
        <span class="value">{{ formatLargeNumber(ticker.quote_volume_24h) }}</span>
      </div>
    </div>

    <div class="chart-container card">
      <div class="chart-toolbar">
        <span class="toolbar-label">指标:</span>
        <el-checkbox-group v-model="selectedIndicators" @change="handleIndicatorChange">
          <el-checkbox label="MA">MA</el-checkbox>
          <el-checkbox label="EMA">EMA</el-checkbox>
          <el-checkbox label="BOLL">BOLL</el-checkbox>
          <el-checkbox label="MACD">MACD</el-checkbox>
          <el-checkbox label="RSI">RSI</el-checkbox>
          <el-checkbox label="KDJ">KDJ</el-checkbox>
        </el-checkbox-group>
        <span class="toolbar-spacer"></span>
        <span class="realtime-status" :class="{ active: lastCandleUpdate }">
          <el-icon v-if="wsStore.isConnected" color="#67C23A"><CircleCheckFilled /></el-icon>
          <el-icon v-else color="#909399"><CircleCloseFilled /></el-icon>
          <span v-if="lastCandleUpdate">最后更新: {{ lastCandleUpdate }}</span>
          <span v-else>等待实时数据...</span>
        </span>
      </div>
      <KLineChart
        ref="chartRef"
        :data="candles"
        :indicators="selectedIndicators"
        height="600px"
      />
    </div>

    <div class="actions card">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMarketStore } from '@/stores/market'
import { useWebSocketStore, type CandleUpdate } from '@/stores/websocket'
import KLineChart from '@/components/charts/KLineChart.vue'
import PriceCell from '@/components/common/PriceCell.vue'
import { formatPrice, formatVolume, formatLargeNumber, formatExchangeName } from '@/utils/format'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { getCandles, getTicker } from '@/api/market'
import { addRecentSymbol } from '@/utils/storage'
import type { Candle, Ticker, Timeframe } from '@/types'

const props = defineProps<{
  exchange: string
  symbol: string
}>()

const router = useRouter()
const route = useRoute()
const marketStore = useMarketStore()
const wsStore = useWebSocketStore()

const chartRef = ref<InstanceType<typeof KLineChart> | null>(null)
const candles = ref<Candle[]>([])
const ticker = ref<Ticker | null>(null)
const selectedTimeframe = ref<Timeframe>('1h')
const selectedIndicators = ref(['MA', 'VOL'])
const loading = ref(false)
const lastCandleUpdate = ref<string>('')  // 调试：最近的 K 线更新时间

const timeframeOptions = [
  { label: '1分', value: '1m' as Timeframe },
  { label: '5分', value: '5m' as Timeframe },
  { label: '15分', value: '15m' as Timeframe },
  { label: '1时', value: '1h' as Timeframe },
  { label: '4时', value: '4h' as Timeframe },
  { label: '1天', value: '1d' as Timeframe },
]

const isInWatchlist = computed(() =>
  marketStore.isInWatchlist(props.exchange, props.symbol)
)

async function loadCandles() {
  loading.value = true
  try {
    const response = await getCandles(
      props.symbol,
      selectedTimeframe.value,
      300  // Backend limit is 300 max
    )
    candles.value = response.data.candles
  } catch (error) {
    console.error('Failed to load candles:', error)
  } finally {
    loading.value = false
  }
}

async function loadTicker() {
  try {
    const response = await getTicker(props.symbol)
    ticker.value = response.data
  } catch (error) {
    console.error('Failed to load ticker:', error)
  }
}

function handleIndicatorChange() {
  // 指标变化由 KLineChart 组件处理
}

function toggleWatchlist() {
  if (isInWatchlist.value) {
    marketStore.removeFromWatchlist(props.exchange, props.symbol)
  } else {
    marketStore.addToWatchlist(props.exchange, props.symbol)
  }
}

function goBack() {
  router.back()
}

function goToBacktest() {
  router.push({
    path: '/trading/backtest',
    query: { exchange: props.exchange, symbol: props.symbol },
  })
}

function goToPaper() {
  router.push({
    path: '/trading/paper',
    query: { exchange: props.exchange, symbol: props.symbol },
  })
}

function goToLive() {
  router.push({
    path: '/trading/live',
    query: { exchange: props.exchange, symbol: props.symbol },
  })
}

// 监听 market store 中的 ticker 更新 (使用标准格式 BTC/USDT)
const storeTicker = computed(() => marketStore.getTicker(props.exchange, toStandardSymbol(props.symbol)))
watch(storeTicker, (newTicker) => {
  if (newTicker) {
    ticker.value = newTicker
  }
}, { immediate: true })

// 切换时间周期时重新加载数据并更新订阅
watch(selectedTimeframe, (newTf, oldTf) => {
  loadCandles()
  // 更新 K 线订阅
  if (oldTf) {
    const standardSymbol = toStandardSymbol(props.symbol)
    const oldChannel = `candle:${standardSymbol}:${oldTf}`
    wsStore.offCandle(oldChannel, handleCandleUpdate)
    wsStore.unsubscribe(oldChannel)
  }
  subscribeToCandles()
})

let unsubscribeTicker: (() => void) | null = null

// 处理 K 线实时更新
function handleCandleUpdate(candle: CandleUpdate) {
  lastCandleUpdate.value = new Date().toLocaleTimeString()
  if (chartRef.value) {
    chartRef.value.updateCandle({
      timestamp: candle.timestamp,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: candle.volume,
    })
  }
}

// 将 symbol 从 URL 格式 (BTC-USDT) 转换为标准格式 (BTC/USDT)
function toStandardSymbol(symbol: string): string {
  return symbol.replace('-', '/')
}

// 订阅 K 线数据
function subscribeToCandles() {
  const standardSymbol = toStandardSymbol(props.symbol)
  const channel = `candle:${standardSymbol}:${selectedTimeframe.value}`
  wsStore.subscribe(channel)
  wsStore.onCandle(channel, handleCandleUpdate)
}

onMounted(async () => {
  addRecentSymbol(props.exchange, props.symbol)
  await Promise.all([loadCandles(), loadTicker()])

  // 连接 WebSocket
  wsStore.connect()

  // 订阅 Ticker 更新
  unsubscribeTicker = wsStore.subscribeToTickers([toStandardSymbol(props.symbol)])

  // 订阅 K 线实时更新
  subscribeToCandles()
})

onUnmounted(() => {
  // 取消 Ticker 订阅
  if (unsubscribeTicker) {
    unsubscribeTicker()
  }

  // 取消 K 线订阅
  const standardSymbol = toStandardSymbol(props.symbol)
  const channel = `candle:${standardSymbol}:${selectedTimeframe.value}`
  wsStore.offCandle(channel, handleCandleUpdate)
  wsStore.unsubscribe(channel)
})
</script>

<style lang="scss" scoped>
.chart-detail {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;

    .header-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .symbol-info {
      display: flex;
      align-items: center;
      gap: 8px;

      .symbol-name {
        font-size: 24px;
        font-weight: 600;
        margin: 0;
      }
    }
  }

  .price-bar {
    display: flex;
    align-items: center;
    gap: 32px;
    padding: 16px 24px;
    margin-bottom: 16px;

    .price-item {
      display: flex;
      flex-direction: column;
      gap: 4px;

      &.main {
        .current-price {
          font-size: 24px;
          font-weight: 600;
        }

        .change {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 14px;

          .separator {
            color: #909399;
          }
        }
      }

      .label {
        font-size: 12px;
        color: #909399;
      }

      .value {
        font-size: 14px;
        font-weight: 500;
      }
    }
  }

  .chart-container {
    margin-bottom: 16px;

    .chart-toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      border-bottom: 1px solid #ebeef5;

      .toolbar-label {
        color: #909399;
        font-size: 14px;
      }

      .toolbar-spacer {
        flex: 1;
      }

      .realtime-status {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: #909399;

        &.active {
          color: #67C23A;
        }

        .el-icon {
          font-size: 14px;
        }
      }
    }
  }

  .actions {
    display: flex;
    gap: 12px;
    padding: 16px;
  }
}
</style>

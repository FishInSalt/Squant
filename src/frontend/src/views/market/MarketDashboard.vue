<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useMarketStore } from '@/stores/market'
import TickerCard from '@/components/market/TickerCard.vue'
import KLineChart from '@/components/charts/KLineChart.vue'
import { POPULAR_SYMBOLS, CANDLE_INTERVALS, type CandleInterval } from '@/utils'
import { ElSelect, ElOption, ElTag, ElButton } from 'element-plus'
import { RefreshRight } from '@element-plus/icons-vue'

// ========== 状态 ==========
const marketStore = useMarketStore()

const currentSymbol = ref<string>('BTC-USDT')
const interval = ref<CandleInterval>('1h')
const loading = ref(false)

// 自动刷新定时器
let refreshInterval: number | null = null
const REFRESH_INTERVAL = 30000 // 30秒刷新一次

// ========== 计算属性 ==========
const currentTicker = computed(() => {
  return marketStore.getTicker(currentSymbol.value)
})

const kLineData = computed(() => {
  return marketStore.getKLines(currentSymbol.value, interval.value)
})

const isPositive = computed(() => {
  return (currentTicker.value?.priceChangePercent || 0) >= 0
})

const formattedPrice = computed(() => {
  const price = currentTicker.value?.lastPrice || 0
  const decimals = price < 1 ? 6 : 2
  return price.toFixed(decimals)
})

const formattedChange = computed(() => {
  const change = currentTicker.value?.priceChangePercent || 0
  const sign = change >= 0 ? '+' : ''
  return `${sign}${change.toFixed(2)}%`
})

// ========== 方法 ==========

/**
 * 加载行情数据
 */
const loadData = async () => {
  loading.value = true
  try {
    await Promise.all([
      marketStore.fetchTickers(),
      marketStore.fetchKLines(currentSymbol.value, interval.value)
    ])
  } catch (error: any) {
    ElMessage.error(error.message || '加载行情数据失败，请检查网络连接')
    console.error('Failed to load market data:', error)
  } finally {
    loading.value = false
  }
}

/**
 * 启动自动刷新
 */
const startAutoRefresh = () => {
  // 清除已存在的定时器
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }

  // 每 30 秒刷新一次数据
  refreshInterval = window.setInterval(() => {
    loadData().catch((error) => {
      console.error('Auto-refresh failed:', error)
      // 静默失败，不显示错误消息
    })
  }, REFRESH_INTERVAL)

  console.log(`Auto-refresh started (${REFRESH_INTERVAL / 1000}s interval)`)
}

/**
 * 停止自动刷新
 */
const stopAutoRefresh = () => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
    console.log('Auto-refresh stopped')
  }
}

/**
 * 切换交易对
 */
const handleSymbolChange = async (symbol: string) => {
  currentSymbol.value = symbol
  try {
    await marketStore.fetchKLines(symbol, interval.value)
  } catch (error: any) {
    ElMessage.error(error.message || '加载K线数据失败')
  }
}

/**
 * 切换时间周期
 */
const handleIntervalChange = async (int: CandleInterval) => {
  interval.value = int
  try {
    await marketStore.fetchKLines(currentSymbol.value, int)
  } catch (error: any) {
    ElMessage.error(error.message || '加载K线数据失败')
  }
}

// ========== 生命周期 ==========
onMounted(() => {
  // 初始加载
  loadData()
  // 启动自动刷新
  startAutoRefresh()
})

onUnmounted(() => {
  // 组件卸载时停止自动刷新
  stopAutoRefresh()
})
</script>

<template>
  <div class="market-dashboard" v-loading="loading">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">行情看板</h2>
      </div>
      <div class="header-right">
        <ElSelect
          v-model="currentSymbol"
          placeholder="选择交易对"
          @change="handleSymbolChange"
          size="large"
          style="width: 200px"
        >
          <ElOption
            v-for="s in POPULAR_SYMBOLS"
            :key="s.value"
            :label="s.label"
            :value="s.value"
          />
        </ElSelect>
        <ElButton
          :icon="RefreshRight"
          @click="loadData"
          :loading="loading"
          circle
          size="large"
          title="刷新数据"
        />
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="dashboard-content">
      <!-- 左侧：行情列表 -->
      <div class="market-list">
        <div class="section-title">
          <h3>热门币种</h3>
        </div>
        <div class="ticker-list">
          <TickerCard
            v-for="s in POPULAR_SYMBOLS"
            :key="s.value"
            :ticker="marketStore.getTicker(s.value)"
            :active="currentSymbol === s.value"
            @click="handleSymbolChange(s.value)"
          />
        </div>
      </div>

      <!-- 中间：K线图 -->
      <div class="chart-section">
        <!-- 当前交易对信息 -->
        <div class="symbol-info">
          <h3 class="symbol-name">{{ currentSymbol.replace('-', '/') }}</h3>
          <div class="price-info">
            <span 
              class="price" 
              :class="{ positive: isPositive, negative: !isPositive }"
            >
              {{ formattedPrice }}
            </span>
            <ElTag
              v-if="currentTicker"
              :type="isPositive ? 'success' : 'danger'"
              size="large"
            >
              {{ formattedChange }}
            </ElTag>
          </div>
        </div>

        <!-- K线图 -->
        <div class="chart-container">
          <div class="interval-selector">
            <ElButton
              v-for="int in CANDLE_INTERVALS"
              :key="int"
              :type="interval === int ? 'primary' : 'default'"
              size="small"
              @click="handleIntervalChange(int)"
            >
              {{ int }}
            </ElButton>
          </div>
          <KLineChart
            :data="kLineData"
            :height="400"
            :symbol="currentSymbol"
          />
        </div>
      </div>

      <!-- 右侧：占位（后续添加买卖盘、成交记录） -->
      <div class="info-section">
        <div class="section-title">
          <h3>市场信息</h3>
        </div>
        <div class="info-content" v-if="currentTicker">
          <div class="info-row">
            <span class="label">24h 成交量</span>
            <span class="value">{{ (currentTicker.volume ?? 0).toFixed(2) }}</span>
          </div>
          <div class="info-row">
            <span class="label">24h 成交额</span>
            <span class="value">{{ (currentTicker.quoteVolume ?? 0).toFixed(2) }} USDT</span>
          </div>
          <div class="info-row">
            <span class="label">开盘价</span>
            <span class="value">{{ (currentTicker.openPrice ?? 0).toFixed(2) }}</span>
          </div>
          <div class="info-row">
            <span class="label">24小时前价格</span>
            <span class="value">{{ (currentTicker.prevClosePrice ?? 0).toFixed(2) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.market-dashboard {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;

    .header-left {
      .page-title {
        margin: 0;
        font-size: 24px;
        font-weight: 600;
      }
    }
  }

  .dashboard-content {
    display: grid;
    grid-template-columns: 280px 1fr 300px;
    gap: 20px;
  }

  .market-list {
    .section-title {
      margin-bottom: 16px;

      h3 {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
      }
    }

    .ticker-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: calc(100vh - 200px);
      overflow-y: auto;
    }
  }

  .chart-section {
    .symbol-info {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;

      .symbol-name {
        margin: 0;
        font-size: 24px;
        font-weight: 600;
      }

      .price-info {
        display: flex;
        align-items: center;
        gap: 16px;

        .price {
          font-size: 28px;
          font-weight: 700;

          &.positive {
            color: #67c23a;
          }

          &.negative {
            color: #f56c6c;
          }
        }
      }
    }

    .chart-container {
      margin-bottom: 20px;

      .interval-selector {
        display: flex;
        gap: 8px;
        margin-bottom: 12px;
        flex-wrap: wrap;
      }
    }
  }

  .info-section {
    .section-title {
      margin-bottom: 16px;

      h3 {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
      }
    }

    .info-content {
      display: flex;
      flex-direction: column;
      gap: 16px;

      .info-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px;
        background: #fff;
        border-radius: 8px;

        .label {
          font-size: 14px;
          color: #909399;
        }

        .value {
          font-size: 16px;
          font-weight: 600;
          color: #303133;
        }
      }
    }
  }
}

// 响应式设计
@media (max-width: 1400px) {
  .market-dashboard {
    .dashboard-content {
      grid-template-columns: 1fr;
    }

    .market-list {
      display: none;
    }

    .info-section {
      display: none;
    }
  }
}
</style>

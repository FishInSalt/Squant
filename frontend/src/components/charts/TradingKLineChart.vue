<template>
  <div class="trading-kline">
    <div class="indicator-toolbar">
      <span class="toolbar-label">指标：</span>
      <div v-for="ind in INDICATOR_DEFS" :key="ind.key" class="indicator-item">
        <el-check-tag
          :checked="activeIndicators.includes(ind.key)"
          @change="toggleIndicator(ind.key)"
        >
          {{ ind.label }}
        </el-check-tag>
        <el-popover
          v-if="activeIndicators.includes(ind.key)"
          trigger="click"
          :width="300"
          placement="bottom-start"
        >
          <template #reference>
            <el-icon class="param-icon"><Setting /></el-icon>
          </template>
          <div class="param-form">
            <div class="param-header">{{ ind.label }} 参数</div>
            <template v-if="ind.dynamicCount">
              <div v-for="(val, i) in indicatorParams[ind.key]" :key="i" class="param-row">
                <span class="param-label">{{ getDynLabel(ind, i) }}</span>
                <el-input-number
                  v-model="indicatorParams[ind.key][i]"
                  :min="1"
                  :max="500"
                  :step="1"
                  size="small"
                  @change="onDynamicParamChange(ind.key)"
                />
                <el-icon
                  v-if="indicatorParams[ind.key].length > 1"
                  class="remove-btn"
                  @click="removeParam(ind.key, i)"
                ><CircleClose /></el-icon>
              </div>
              <el-button
                v-if="indicatorParams[ind.key].length < (ind.maxCount ?? 8)"
                size="small"
                text
                type="primary"
                :icon="Plus"
                @click="addParam(ind.key)"
              >
                添加
              </el-button>
            </template>
            <template v-else>
              <div v-for="(p, i) in ind.params" :key="i" class="param-row">
                <span class="param-label">{{ p.label }}</span>
                <el-input-number
                  v-model="indicatorParams[ind.key][i]"
                  :min="p.min"
                  :max="p.max"
                  :step="p.step"
                  size="small"
                  @change="onParamChange(ind.key)"
                />
              </div>
            </template>
            <el-button size="small" text type="info" @click="resetParams(ind.key)">
              恢复默认
            </el-button>
          </div>
        </el-popover>
      </div>
      <span class="toolbar-spacer"></span>
      <div v-if="hoveredTrades.length > 0" class="trade-info">
        <div v-for="(t, i) in hoveredTrades" :key="i" class="trade-item">
          <span class="trade-tag" :class="t.type">{{ t.type === 'buy' ? '买入' : '卖出' }}</span>
          <span class="trade-field">{{ t.price }}</span>
          <span class="trade-sep">&times;</span>
          <span class="trade-field">{{ t.amount }}</span>
          <template v-if="t.pnl != null">
            <span class="trade-pnl" :class="t.pnl >= 0 ? 'profit' : 'loss'">
              {{ t.pnl >= 0 ? '+' : '' }}{{ t.pnl.toFixed(2) }}
              ({{ t.pnlPct != null ? (t.pnlPct >= 0 ? '+' : '') + t.pnlPct.toFixed(2) + '%' : '' }})
            </span>
          </template>
        </div>
      </div>
      <span v-if="isLoadingMore" class="loading-hint">
        <el-icon class="is-loading"><Loading /></el-icon>
        加载中...
      </span>
    </div>
    <div ref="chartContainer" class="kline-container" :style="{ height: computedHeight }"></div>
    <div class="navigation-bar" v-if="candleData.length > 0">
      <span class="nav-label">{{ navDateLabel }}</span>
      <el-slider
        v-model="navPosition"
        :min="0"
        :max="candleData.length - 1"
        :step="1"
        :show-tooltip="false"
        @input="onNavInput"
      />
      <span class="nav-tip">拖动滑块定位 · 滚轮缩放</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { init, dispose, registerOverlay, LoadDataType, type Chart } from 'klinecharts'
import { Loading, Setting, Plus, CircleClose } from '@element-plus/icons-vue'
import type { Trade } from '@/types'
import { getCandles } from '@/api/market'
import { useWebSocketStore, type CandleUpdate } from '@/stores/websocket'
import { INDICATOR_DEFS, getDefaultParams, getIndicatorDef, getDynamicParamLabel, suggestNewPeriod, type IndicatorParams } from './indicatorConfig'

const SUB_PANE_HEIGHT = 120
const INITIAL_CANDLE_COUNT = 300

interface Props {
  symbol: string
  timeframe: string
  trades?: Trade[]
  openTrade?: { entry_time: string; entry_price: number; amount: number } | null
  realtime?: boolean
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px',
  realtime: false,
})

const wsStore = useWebSocketStore()

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null

// Data
const candleData = ref<{ timestamp: number; open: number; high: number; low: number; close: number; volume: number }[]>([])
const isLoadingMore = ref(false)

// Navigation slider
const navPosition = ref(0)

// Indicators
const activeIndicators = ref<string[]>(['MA', 'VOL'])
const indicatorParams = ref<IndicatorParams>(getDefaultParams())

const subPaneCount = computed(() =>
  activeIndicators.value.filter((name) => getIndicatorDef(name)?.paneId != null).length
)

const computedHeight = computed(() => {
  const base = parseInt(props.height) || 500
  return `${base + subPaneCount.value * SUB_PANE_HEIGHT}px`
})

// Trade tooltip state
interface TradeTooltip {
  type: 'buy' | 'sell'
  price: number
  amount: number
  time: string
  pnl?: number
  pnlPct?: number
}
const tradeInfoMap = ref<Map<number, TradeTooltip[]>>(new Map())
const hoveredTrades = ref<TradeTooltip[]>([])

// Track last trades length to avoid unnecessary rebuilds
let lastTradesLength = 0

// Navigation helpers
let suppressSync = false

function formatNavDate(ts: number): string {
  const d = new Date(ts)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const navDateLabel = computed(() => {
  if (candleData.value.length === 0) return ''
  const idx = Math.min(navPosition.value, candleData.value.length - 1)
  return formatNavDate(candleData.value[idx]?.timestamp ?? 0)
})

function syncNavFromChart() {
  if (!chart || suppressSync) return
  const range = chart.getVisibleRange()
  const mid = Math.round((range.from + range.to) / 2)
  const maxIdx = candleData.value.length - 1
  navPosition.value = Math.max(0, Math.min(mid, maxIdx))
}

function onNavInput(val: number | number[]) {
  if (!chart || Array.isArray(val)) return
  suppressSync = true
  chart.scrollToDataIndex(val)
  setTimeout(() => { suppressSync = false }, 60)
}

// Price precision
function calculatePricePrecision(price: number): number {
  if (price >= 10000) return 2
  if (price >= 1000) return 3
  if (price >= 100) return 4
  if (price >= 1) return 5
  if (price >= 0.1) return 6
  if (price >= 0.01) return 7
  return 8
}

// Trade overlay registration
let overlaysRegistered = false

function registerTradeOverlays() {
  if (overlaysRegistered) return
  overlaysRegistered = true

  registerOverlay({
    name: 'buyMarker',
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates }: any) => {
      if (!coordinates[0]) return []
      const { x, y } = coordinates[0]
      const s = 4
      const gap = 6
      return [
        {
          type: 'polygon',
          attrs: {
            coordinates: [
              { x: x - s, y: y + gap + s * 2 },
              { x: x + s, y: y + gap + s * 2 },
              { x, y: y + gap },
            ],
          },
          styles: { style: 'fill', color: '#00C853', borderColor: '#00C853', borderSize: 1 },
        },
        {
          type: 'text',
          attrs: { x, y: y + gap + s * 2 + 10, text: 'B', align: 'center', baseline: 'middle' },
          styles: { color: '#00C853', size: 9, family: 'Arial', backgroundColor: 'transparent' },
        },
      ]
    },
  } as any)

  registerOverlay({
    name: 'sellMarker',
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates }: any) => {
      if (!coordinates[0]) return []
      const { x, y } = coordinates[0]
      const s = 4
      const gap = 6
      return [
        {
          type: 'text',
          attrs: { x, y: y - gap - s * 2 - 10, text: 'S', align: 'center', baseline: 'middle' },
          styles: { color: '#FF1744', size: 9, family: 'Arial', backgroundColor: 'transparent' },
        },
        {
          type: 'polygon',
          attrs: {
            coordinates: [
              { x: x - s, y: y - gap - s * 2 },
              { x: x + s, y: y - gap - s * 2 },
              { x, y: y - gap },
            ],
          },
          styles: { style: 'fill', color: '#FF1744', borderColor: '#FF1744', borderSize: 1 },
        },
      ]
    },
  } as any)
}

// Chart initialization
function initChart() {
  if (!chartContainer.value || candleData.value.length === 0) return

  registerTradeOverlays()

  const styles: any = {
    grid: {
      show: true,
      horizontal: { show: true, size: 1, color: '#EDEDED', style: 'dashed' },
      vertical: { show: true, size: 1, color: '#EDEDED', style: 'dashed' },
    },
    candle: {
      type: 'candle_solid',
      bar: {
        upColor: '#00C853',
        downColor: '#FF1744',
        noChangeColor: '#909399',
        upBorderColor: '#00C853',
        downBorderColor: '#FF1744',
        noChangeBorderColor: '#909399',
        upWickColor: '#00C853',
        downWickColor: '#FF1744',
        noChangeWickColor: '#909399',
      },
      tooltip: { showRule: 'follow_cross', showType: 'standard' },
    },
    indicator: {
      tooltip: { showRule: 'follow_cross', showType: 'standard' },
    },
    xAxis: {
      show: true,
      axisLine: { show: true, color: '#DDDDDD' },
      tickLine: { show: true, color: '#DDDDDD' },
      tickText: { show: true, color: '#909399' },
    },
    yAxis: {
      show: true,
      axisLine: { show: true, color: '#DDDDDD' },
      tickLine: { show: true, color: '#DDDDDD' },
      tickText: { show: true, color: '#909399' },
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: { show: true, style: 'dashed', color: '#909399' },
        text: { show: true, color: '#FFFFFF', backgroundColor: '#1890FF' },
      },
      vertical: {
        show: true,
        line: { show: true, style: 'dashed', color: '#909399' },
        text: { show: true, color: '#FFFFFF', backgroundColor: '#1890FF' },
      },
    },
  }

  chart = init(chartContainer.value, { styles })
  chart!.setLeftMinVisibleBarCount(1)
  chart!.setRightMinVisibleBarCount(1)

  // Set precision
  const latestPrice = candleData.value[candleData.value.length - 1].close
  const pricePrecision = calculatePricePrecision(latestPrice)
  const latestVolume = candleData.value[candleData.value.length - 1].volume
  const volumePrecision = latestVolume >= 1 ? 2 : 6
  chart!.setPriceVolumePrecision(pricePrecision, volumePrecision)

  // Load data with lazy loading support
  chart!.setLoadDataCallback(({ type, data, callback }) => {
    if (type === LoadDataType.Forward && data) {
      loadOlderCandles(data.timestamp).then((candles) => {
        callback(candles, candles.length >= 300)
      }).catch(() => {
        callback([], true)
      })
    } else {
      callback([], false)
    }
  })

  chart!.applyNewData(candleData.value, true)

  // Add indicators
  activeIndicators.value.forEach((ind) => addIndicator(ind))

  // Trade markers
  rebuildTradeMarkers()

  // Init slider
  navPosition.value = candleData.value.length - 1

  // Crosshair hover
  chart!.subscribeAction('onCrosshairChange' as any, (data: any) => {
    if (data?.kLineData) {
      hoveredTrades.value = tradeInfoMap.value.get(data.kLineData.timestamp) ?? []
    } else {
      hoveredTrades.value = []
    }
  })

  // Keep slider in sync
  chart!.subscribeAction('onZoom' as any, () => syncNavFromChart())
  chart!.subscribeAction('onScroll' as any, () => syncNavFromChart())
}

async function loadOlderCandles(beforeTimestamp: number): Promise<{ timestamp: number; open: number; high: number; low: number; close: number; volume: number }[]> {
  isLoadingMore.value = true
  try {
    const response = await getCandles(props.symbol, props.timeframe as any, 300, beforeTimestamp)
    const newCandles = response.data.candles
    // Prepend to our data store
    if (newCandles.length > 0) {
      candleData.value = [...newCandles, ...candleData.value]
    }
    return newCandles
  } catch {
    return []
  } finally {
    isLoadingMore.value = false
  }
}

// Indicator management
function addIndicator(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  const isStack = !def.paneId
  const params = indicatorParams.value[name]
  chart.createIndicator(
    { name: def.key, calcParams: params } as any,
    isStack,
    { id: paneId, ...(def.paneId ? { height: SUB_PANE_HEIGHT } : {}) },
  )
  if (def.colors) {
    chart.overrideIndicator({
      name: def.key,
      styles: {
        lines: def.colors.map((color) => ({
          style: 'solid',
          smooth: false,
          size: 1,
          dashedValue: [2, 2],
          color,
        })),
      },
    } as any, paneId)
  }
}

function removeIndicator(name: string) {
  const def = getIndicatorDef(name)
  if (chart && def) {
    const paneId = def.paneId ?? 'candle_pane'
    chart.removeIndicator(paneId, def.key)
  }
}

function toggleIndicator(name: string) {
  const idx = activeIndicators.value.indexOf(name)
  if (idx >= 0) {
    activeIndicators.value.splice(idx, 1)
    removeIndicator(name)
  } else {
    activeIndicators.value.push(name)
    addIndicator(name)
  }
}

// Indicator parameter editing
function getDynLabel(def: { paramPrefix?: string; key: string }, index: number): string {
  return getDynamicParamLabel(def as any, index)
}

function onParamChange(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  const params = indicatorParams.value[name]
  chart.overrideIndicator({ name: def.key, calcParams: params } as any, paneId)
}

function onDynamicParamChange(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  chart.removeIndicator(paneId, def.key)
  addIndicator(name)
}

function addParam(name: string) {
  const def = getIndicatorDef(name)
  if (!def) return
  const current = indicatorParams.value[name]
  const newPeriod = suggestNewPeriod(def, current)
  indicatorParams.value[name] = [...current, newPeriod]
  onDynamicParamChange(name)
}

function removeParam(name: string, index: number) {
  const current = indicatorParams.value[name]
  if (current.length <= 1) return
  indicatorParams.value[name] = current.filter((_, i) => i !== index)
  onDynamicParamChange(name)
}

function resetParams(name: string) {
  const def = getIndicatorDef(name)
  if (!def) return
  indicatorParams.value[name] = def.params.map((p) => p.default)
  if (def.dynamicCount) {
    onDynamicParamChange(name)
  } else {
    onParamChange(name)
  }
}

// Trade markers
function rebuildTradeMarkers() {
  const hasTrades = props.trades && props.trades.length > 0
  const hasOpenTrade = !!props.openTrade
  if (!chart || (!hasTrades && !hasOpenTrade)) {
    tradeInfoMap.value = new Map()
    hoveredTrades.value = []
    return
  }

  chart.removeOverlay({ name: 'buyMarker' })
  chart.removeOverlay({ name: 'sellMarker' })

  const data = candleData.value
  if (data.length === 0) {
    tradeInfoMap.value = new Map()
    return
  }

  const lowMap = new Map<number, number>()
  const highMap = new Map<number, number>()
  for (const c of data) {
    lowMap.set(c.timestamp, c.low)
    highMap.set(c.timestamp, c.high)
  }

  const minTs = data[0].timestamp
  const maxTs = data[data.length - 1].timestamp
  const sortedTs = data.map(c => c.timestamp)

  function findClosestTs(ts: number): number {
    let lo = 0, hi = sortedTs.length - 1
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (sortedTs[mid] < ts) lo = mid + 1
      else hi = mid
    }
    const candidates = [sortedTs[lo], sortedTs[Math.max(0, lo - 1)]]
    let best = candidates[0]
    for (const c of candidates) {
      if (Math.abs(c - ts) < Math.abs(best - ts)) best = c
    }
    return best
  }

  function snapTs(ts: number): number {
    return lowMap.has(ts) ? ts : findClosestTs(ts)
  }

  const overlays: any[] = []
  const newTradeMap = new Map<number, TradeTooltip[]>()

  function addToMap(candleTs: number, info: TradeTooltip) {
    if (!newTradeMap.has(candleTs)) newTradeMap.set(candleTs, [])
    newTradeMap.get(candleTs)!.push(info)
  }

  for (const trade of (props.trades ?? [])) {
    const entryTs = new Date(trade.entry_time).getTime()
    if (entryTs >= minTs && entryTs <= maxTs) {
      const snapped = snapTs(entryTs)
      overlays.push({
        name: 'buyMarker',
        lock: true,
        points: [{ timestamp: entryTs, value: lowMap.get(snapped) ?? 0 }],
      })
      addToMap(snapped, {
        type: 'buy',
        price: trade.entry_price,
        amount: trade.amount,
        time: trade.entry_time,
      })
    }

    if (trade.exit_time && trade.exit_price) {
      const exitTs = new Date(trade.exit_time).getTime()
      if (exitTs >= minTs && exitTs <= maxTs) {
        const snapped = snapTs(exitTs)
        overlays.push({
          name: 'sellMarker',
          lock: true,
          points: [{ timestamp: exitTs, value: highMap.get(snapped) ?? 0 }],
        })
        addToMap(snapped, {
          type: 'sell',
          price: trade.exit_price!,
          amount: trade.amount,
          time: trade.exit_time,
          pnl: trade.pnl,
          pnlPct: trade.pnl_pct,
        })
      }
    }
  }

  // Open trade: draw buy marker for current position entry
  if (props.openTrade) {
    const entryTs = new Date(props.openTrade.entry_time).getTime()
    if (entryTs >= minTs && entryTs <= maxTs) {
      const snapped = snapTs(entryTs)
      overlays.push({
        name: 'buyMarker',
        lock: true,
        points: [{ timestamp: entryTs, value: lowMap.get(snapped) ?? 0 }],
      })
      addToMap(snapped, {
        type: 'buy',
        price: props.openTrade.entry_price,
        amount: props.openTrade.amount,
        time: props.openTrade.entry_time,
      })
    }
  }

  tradeInfoMap.value = newTradeMap
  if (overlays.length > 0) {
    chart.createOverlay(overlays)
  }
}

// WebSocket subscription
let currentChannel: string | null = null

function subscribeWs() {
  if (!props.realtime || !props.symbol || !props.timeframe) return
  const channel = `candle:${props.symbol}:${props.timeframe}`
  if (currentChannel === channel) return
  unsubscribeWs()
  currentChannel = channel
  wsStore.subscribe(channel)
  wsStore.onCandle(channel, handleCandleUpdate)
}

function unsubscribeWs() {
  if (currentChannel) {
    wsStore.offCandle(currentChannel, handleCandleUpdate)
    wsStore.unsubscribe(currentChannel)
    currentChannel = null
  }
}

function handleCandleUpdate(candle: CandleUpdate) {
  if (!chart) return
  const kd = {
    timestamp: candle.timestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
  }
  chart.updateData(kd)
  // Update local data store
  const last = candleData.value[candleData.value.length - 1]
  if (last && last.timestamp === kd.timestamp) {
    candleData.value[candleData.value.length - 1] = kd
  } else if (!last || kd.timestamp > last.timestamp) {
    candleData.value.push(kd)
  }
}

// Load initial candles
async function loadInitialCandles() {
  try {
    const response = await getCandles(props.symbol, props.timeframe as any, INITIAL_CANDLE_COUNT)
    candleData.value = response.data.candles
    await nextTick()
    initChart()
  } catch (error) {
    console.error('Failed to load candles:', error)
  }
}

// Watch realtime prop
watch(() => props.realtime, (newVal) => {
  if (newVal) {
    wsStore.connect()
    subscribeWs()
  } else {
    unsubscribeWs()
  }
})

// Watch trades count and open trade to rebuild chart markers
watch(
  () => [props.trades?.length ?? 0, props.openTrade?.entry_time ?? null] as const,
  () => {
    lastTradesLength = props.trades?.length ?? 0
    if (chart) rebuildTradeMarkers()
  },
)

// Resize on sub-pane count change
watch(computedHeight, () => {
  nextTick(() => chart?.resize())
})

onMounted(async () => {
  await loadInitialCandles()
  if (props.realtime) {
    wsStore.connect()
    subscribeWs()
  }
})

onUnmounted(() => {
  unsubscribeWs()
  if (chartContainer.value) {
    dispose(chartContainer.value)
  }
})
</script>

<style lang="scss" scoped>
.trading-kline {
  .indicator-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 0;
    flex-wrap: wrap;

    .toolbar-label {
      font-size: 13px;
      color: #909399;
    }

    .indicator-item {
      display: inline-flex;
      align-items: center;
      gap: 2px;

      .param-icon {
        font-size: 14px;
        color: #909399;
        cursor: pointer;
        transition: color 0.2s;

        &:hover {
          color: #409EFF;
        }
      }
    }

    .toolbar-spacer {
      flex: 1;
    }

    .trade-info {
      display: flex;
      align-items: center;
      gap: 8px;

      .trade-item {
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 12px;
        color: #606266;
        white-space: nowrap;
      }

      .trade-tag {
        display: inline-block;
        padding: 0 5px;
        border-radius: 2px;
        font-size: 11px;
        font-weight: 600;
        line-height: 18px;

        &.buy {
          color: #fff;
          background: #00C853;
        }

        &.sell {
          color: #fff;
          background: #FF1744;
        }
      }

      .trade-field {
        font-weight: 500;
        font-variant-numeric: tabular-nums;
      }

      .trade-sep {
        color: #C0C4CC;
      }

      .trade-pnl {
        font-weight: 500;
        font-variant-numeric: tabular-nums;

        &.profit {
          color: #00C853;
        }

        &.loss {
          color: #FF1744;
        }
      }
    }

    .loading-hint {
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: #909399;
    }
  }

  .kline-container {
    width: 100%;
    background: #fff;
    border-radius: 4px;
  }

  .navigation-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 4px 0;

    .nav-label {
      font-size: 12px;
      color: #606266;
      white-space: nowrap;
      min-width: 72px;
      font-variant-numeric: tabular-nums;
    }

    .nav-tip {
      font-size: 11px;
      color: #C0C4CC;
      white-space: nowrap;
    }

    :deep(.el-slider) {
      flex: 1;

      .el-slider__runway {
        height: 4px;
        background-color: #E4E7ED;
      }

      .el-slider__bar {
        height: 4px;
        background-color: transparent;
      }

      .el-slider__button {
        width: 14px;
        height: 14px;
      }
    }
  }
}

.param-form {
  .param-header {
    font-size: 13px;
    font-weight: 500;
    color: #303133;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid #f0f0f0;
  }

  .param-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;

    .param-label {
      font-size: 12px;
      color: #606266;
      min-width: 40px;
      font-weight: 500;
    }

    :deep(.el-input-number) {
      flex: 1;
    }

    .remove-btn {
      flex-shrink: 0;
      font-size: 16px;
      color: #C0C4CC;
      cursor: pointer;
      transition: color 0.2s;

      &:hover {
        color: #F56C6C;
      }
    }
  }

  > .el-button {
    margin-top: 6px;
    width: 100%;
  }
}
</style>

<template>
  <div class="backtest-kline">
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
            <!-- Dynamic-count indicators: variable number of lines -->
            <template v-if="ind.dynamicCount">
              <div v-for="(val, i) in indicatorParams[ind.key]" :key="i" class="param-row">
                <span class="param-label">{{ getDynamicLabel(ind, i) }}</span>
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
                >
                  <CircleClose />
                </el-icon>
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
            <!-- Fixed-count indicators: standard params -->
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
          <span class="trade-time">{{ formatTradeTime(t.time) }}</span>
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
    <div class="navigation-bar" v-if="allCandles.length > 0">
      <span class="nav-label">{{ navDateLabel }}</span>
      <el-slider
        v-model="navPosition"
        :min="0"
        :max="allCandles.length - 1"
        :step="1"
        :show-tooltip="false"
        @input="onNavInput"
      />
      <span class="nav-tip">拖动滑块定位 · 滚轮缩放 · 滑动加载</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { init, dispose, registerOverlay, type Chart } from 'klinecharts'
import { Setting, Loading, Plus, CircleClose } from '@element-plus/icons-vue'
import type { Candle, Trade, Fill } from '@/types'
import { INDICATOR_DEFS, getDefaultParams, getIndicatorDef, getDynamicParamLabel, suggestNewPeriod, type IndicatorParams } from './indicatorConfig'

// --- Constants ---
const LOAD_TRIGGER = 50     // Distance from edge (in bars) to trigger loading
const MAX_LOADED = 5000     // Max candles kept in memory
const SUB_PANE_HEIGHT = 120 // Fixed height for sub-pane indicators (px)

interface Props {
  candles: Candle[]           // Initial data from parent
  trades?: Trade[]
  fills?: Fill[]
  height?: string
  totalCount?: number         // Total candles in backtest (for knowing if more exists)
  onLoadMore?: (params: { before?: number; after?: number }) => Promise<Candle[]>
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px',
})

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null

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

// --- Trade tooltip state ---
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

// --- Sliding window state ---
const allCandles = ref<Candle[]>([])
const isLoadingMore = ref(false)
let hasMoreBefore = true
let hasMoreAfter = false  // Initial load gets the tail, so no more after

function formatNavDate(ts: number): string {
  const d = new Date(ts)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatTradeTime(iso: string): string {
  const d = new Date(iso)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${m}-${day} ${h}:${min}`
}

const navDateLabel = computed(() => {
  if (allCandles.value.length === 0) return ''
  const idx = Math.min(navPosition.value, allCandles.value.length - 1)
  return formatNavDate(allCandles.value[idx]?.timestamp ?? 0)
})

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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

function calculatePricePrecision(price: number): number {
  if (price >= 10000) return 2
  if (price >= 1000) return 3
  if (price >= 100) return 4
  if (price >= 1) return 5
  if (price >= 0.1) return 6
  if (price >= 0.01) return 7
  return 8
}

// Prevent feedback loop: slider → chart scroll → chart event → slider overwrite
let suppressSync = false

/** Sync slider position from chart's current visible range */
function syncNavFromChart() {
  if (!chart || suppressSync) return
  const range = chart.getVisibleRange()
  const mid = Math.round((range.from + range.to) / 2)
  const maxIdx = allCandles.value.length - 1
  navPosition.value = Math.max(0, Math.min(mid, maxIdx))
}

/** Scroll chart to slider position (keeps current zoom level) */
function onNavInput(val: number | number[]) {
  if (!chart || Array.isArray(val)) return
  suppressSync = true
  chart.scrollToDataIndex(val)
  setTimeout(() => { suppressSync = false }, 60)
}

// --- Scroll-based lazy loading ---
async function checkAndLoadMore() {
  if (!chart || isLoadingMore.value || !props.onLoadMore) return

  const dataLen = allCandles.value.length
  if (dataLen === 0) return

  const range = chart.getVisibleRange()

  // Scroll left — load older data
  if (range.from <= LOAD_TRIGGER && hasMoreBefore) {
    await loadMoreData('before')
  }
  // Scroll right — load newer data
  else if (range.to >= dataLen - LOAD_TRIGGER && hasMoreAfter) {
    await loadMoreData('after')
  }
}

async function loadMoreData(direction: 'before' | 'after') {
  if (!chart || !props.onLoadMore || isLoadingMore.value) return

  isLoadingMore.value = true

  // Save current viewport anchor timestamp
  const range = chart.getVisibleRange()
  const anchorIdx = Math.max(0, range.from)
  const anchorTs = allCandles.value[anchorIdx]?.timestamp

  try {
    let newCandles: Candle[]
    if (direction === 'before') {
      const oldestTs = allCandles.value[0].timestamp
      newCandles = await props.onLoadMore({ before: oldestTs })
    } else {
      const newestTs = allCandles.value[allCandles.value.length - 1].timestamp
      newCandles = await props.onLoadMore({ after: newestTs })
    }

    if (newCandles.length === 0) {
      if (direction === 'before') hasMoreBefore = false
      else hasMoreAfter = false
      return
    }

    // Merge data
    if (direction === 'before') {
      allCandles.value = [...newCandles, ...allCandles.value]
      // Trim from tail if too large
      if (allCandles.value.length > MAX_LOADED) {
        allCandles.value = allCandles.value.slice(0, MAX_LOADED)
        hasMoreAfter = true
      }
    } else {
      allCandles.value = [...allCandles.value, ...newCandles]
      // Trim from head if too large
      if (allCandles.value.length > MAX_LOADED) {
        allCandles.value = allCandles.value.slice(allCandles.value.length - MAX_LOADED)
        hasMoreBefore = true
      }
    }

    // Check if we've reached the boundary
    if (newCandles.length < 500) {
      if (direction === 'before') hasMoreBefore = false
      else hasMoreAfter = false
    }

    // Refresh chart
    refreshChartData()

    // Restore viewport position
    if (anchorTs) {
      chart!.scrollToTimestamp(anchorTs)
    }
  } catch (error) {
    console.error('Failed to load more candles:', error)
  } finally {
    isLoadingMore.value = false
  }
}

/** Re-apply data and overlays to chart without disposing */
function refreshChartData() {
  if (!chart) return

  const klineData = allCandles.value.map((c) => ({
    timestamp: c.timestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }))
  chart.applyNewData(klineData)

  // Rebuild trade markers with updated data
  rebuildTradeMarkers()
}

function initChart() {
  if (!chartContainer.value || allCandles.value.length === 0) return

  registerTradeOverlays()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  // Allow scrolling far left/right and zooming out much further
  chart!.setLeftMinVisibleBarCount(1)
  chart!.setRightMinVisibleBarCount(1)

  // Set precision
  const latestPrice = allCandles.value[allCandles.value.length - 1].close
  const pricePrecision = calculatePricePrecision(latestPrice)
  const latestVolume = allCandles.value[allCandles.value.length - 1].volume
  const volumePrecision = latestVolume >= 1 ? 2 : 6
  chart!.setPriceVolumePrecision(pricePrecision, volumePrecision)

  // Load data
  const klineData = allCandles.value.map((c) => ({
    timestamp: c.timestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }))
  chart!.applyNewData(klineData)

  // Add indicators
  activeIndicators.value.forEach((ind) => addIndicator(ind))

  // Add trade markers
  rebuildTradeMarkers()

  // Initialize slider to the end of data (chart default view)
  navPosition.value = allCandles.value.length - 1

  // Show trade info on crosshair hover
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart!.subscribeAction('onCrosshairChange' as any, (data: any) => {
    if (data?.kLineData) {
      hoveredTrades.value = tradeInfoMap.value.get(data.kLineData.timestamp) ?? []
    } else {
      hoveredTrades.value = []
    }
  })

  // Keep slider in sync + detect scroll for lazy loading
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart!.subscribeAction('onZoom' as any, () => {
    syncNavFromChart()
    checkAndLoadMore()
  })
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart!.subscribeAction('onScroll' as any, () => {
    syncNavFromChart()
    checkAndLoadMore()
  })
}

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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

function onParamChange(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  const params = indicatorParams.value[name]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart.overrideIndicator({ name: def.key, calcParams: params } as any, paneId)
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

// --- Dynamic-count indicator helpers ---
function getDynamicLabel(def: { paramPrefix?: string; key: string }, index: number): string {
  return getDynamicParamLabel(def as any, index)
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

/** Re-create indicator when line count changes (overrideIndicator can't change line count) */
function onDynamicParamChange(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  // Remove and re-add to apply new line count
  chart.removeIndicator(paneId, def.key)
  addIndicator(name)
}

/** Rebuild trade markers and tooltip map based on current allCandles data */
function rebuildTradeMarkers() {
  const hasFills = props.fills && props.fills.length > 0
  const hasTrades = props.trades && props.trades.length > 0
  if (!chart || (!hasFills && !hasTrades)) {
    tradeInfoMap.value = new Map()
    hoveredTrades.value = []
    return
  }

  // Remove existing trade overlays
  chart.removeOverlay({ name: 'buyMarker' })
  chart.removeOverlay({ name: 'sellMarker' })

  const data = allCandles.value
  if (data.length === 0) {
    tradeInfoMap.value = new Map()
    return
  }

  // Build timestamp → low/high price maps from current data
  const lowMap = new Map<number, number>()
  const highMap = new Map<number, number>()
  for (const c of data) {
    lowMap.set(c.timestamp, c.low)
    highMap.set(c.timestamp, c.high)
  }

  // Time range of loaded data
  const minTs = data[0].timestamp
  const maxTs = data[data.length - 1].timestamp

  // Find closest candle timestamp via binary search
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

  function findLow(ts: number): number {
    return lowMap.get(snapTs(ts)) ?? 0
  }

  function findHigh(ts: number): number {
    return highMap.get(snapTs(ts)) ?? 0
  }

  const overlays: any[] = []
  const newTradeMap = new Map<number, TradeTooltip[]>()

  function addToMap(candleTs: number, info: TradeTooltip) {
    if (!newTradeMap.has(candleTs)) newTradeMap.set(candleTs, [])
    newTradeMap.get(candleTs)!.push(info)
  }

  // Use fills as marker source when available (shows every individual fill);
  // otherwise fall back to trades (entry/exit only)
  if (hasFills) {
    for (const fill of props.fills!) {
      const ts = new Date(fill.timestamp).getTime()
      if (ts < minTs || ts > maxTs) continue
      const snapped = snapTs(ts)
      const isBuy = fill.side === 'buy'
      overlays.push({
        name: isBuy ? 'buyMarker' : 'sellMarker',
        lock: true,
        points: [{ timestamp: ts, value: isBuy ? findLow(ts) : findHigh(ts) }],
      })
      addToMap(snapped, {
        type: fill.side as 'buy' | 'sell',
        price: fill.price,
        amount: fill.amount,
        time: fill.timestamp,
      })
    }
  } else {
    for (const trade of props.trades!) {
      const entryTs = new Date(trade.entry_time).getTime()

      // Only add markers within loaded data range
      if (entryTs >= minTs && entryTs <= maxTs) {
        const snapped = snapTs(entryTs)
        overlays.push({
          name: 'buyMarker',
          lock: true,
          points: [{ timestamp: entryTs, value: findLow(entryTs) }],
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
            points: [{ timestamp: exitTs, value: findHigh(exitTs) }],
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
  }

  tradeInfoMap.value = newTradeMap

  if (overlays.length > 0) {
    chart.createOverlay(overlays)
  }
}

// Resize chart when sub-pane count changes container height
watch(computedHeight, () => {
  nextTick(() => chart?.resize())
})

// Watch for initial data from parent (reference change only, not deep)
watch(() => props.candles, (newCandles) => {
  if (newCandles.length === 0) return

  // Reset window state
  allCandles.value = [...newCandles]
  hasMoreBefore = (props.totalCount ?? newCandles.length) > newCandles.length
  hasMoreAfter = false

  // Dispose and recreate chart
  if (chart && chartContainer.value) {
    dispose(chartContainer.value)
    chart = null
  }
  nextTick(() => initChart())
})

// Watch for trades/fills change (rebuild markers)
watch(() => [props.trades, props.fills], () => {
  if (chart) {
    rebuildTradeMarkers()
  }
}, { deep: true })

onMounted(() => {
  if (props.candles.length > 0) {
    allCandles.value = [...props.candles]
    hasMoreBefore = (props.totalCount ?? props.candles.length) > props.candles.length
    hasMoreAfter = false
  }
  initChart()
})

onUnmounted(() => {
  if (chartContainer.value) {
    dispose(chartContainer.value)
  }
})
</script>

<style lang="scss" scoped>
.backtest-kline {
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

      .trade-time {
        color: #909399;
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

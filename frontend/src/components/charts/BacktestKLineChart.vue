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
          :width="220"
          placement="bottom-start"
        >
          <template #reference>
            <el-icon class="param-icon"><Setting /></el-icon>
          </template>
          <div class="param-form">
            <div class="param-header">{{ ind.label }} 参数</div>
            <div v-for="(p, i) in ind.params" :key="i" class="param-row">
              <span class="param-label">{{ p.label }}</span>
              <el-input-number
                v-model="indicatorParams[ind.key][i]"
                :min="p.min"
                :max="p.max"
                :step="p.step"
                size="small"
                controls-position="right"
                @change="onParamChange(ind.key)"
              />
            </div>
            <el-button size="small" text type="info" @click="resetParams(ind.key)">
              恢复默认
            </el-button>
          </div>
        </el-popover>
      </div>
    </div>
    <div ref="chartContainer" class="kline-container" :style="{ height }"></div>
    <div class="navigation-bar" v-if="candles.length > 0">
      <span class="nav-label">{{ navDateLabel }}</span>
      <el-slider
        v-model="navPosition"
        :min="0"
        :max="candles.length - 1"
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
import { init, dispose, registerOverlay, type Chart } from 'klinecharts'
import { Setting } from '@element-plus/icons-vue'
import type { Candle, Trade } from '@/types'
import { INDICATOR_DEFS, getDefaultParams, getIndicatorDef, type IndicatorParams } from './indicatorConfig'

interface Props {
  candles: Candle[]
  trades?: Trade[]
  height?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px',
})

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null

// Navigation slider: single position index
const navPosition = ref(0)

const activeIndicators = ref<string[]>(['MA', 'VOL'])
const indicatorParams = ref<IndicatorParams>(getDefaultParams())

function formatNavDate(ts: number): string {
  const d = new Date(ts)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const navDateLabel = computed(() => {
  if (props.candles.length === 0) return ''
  const idx = Math.min(navPosition.value, props.candles.length - 1)
  return formatNavDate(props.candles[idx]?.timestamp ?? 0)
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
      const gap = 6  // below the low price anchor
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
      const gap = 6  // above the high price anchor
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
  const maxIdx = props.candles.length - 1
  navPosition.value = Math.max(0, Math.min(mid, maxIdx))
}

/** Scroll chart to slider position (keeps current zoom level) */
function onNavInput(val: number | number[]) {
  if (!chart || Array.isArray(val)) return
  suppressSync = true
  chart.scrollToDataIndex(val)
  setTimeout(() => { suppressSync = false }, 60)
}

function initChart() {
  if (!chartContainer.value || props.candles.length === 0) return

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
  const latestPrice = props.candles[props.candles.length - 1].close
  const pricePrecision = calculatePricePrecision(latestPrice)
  const latestVolume = props.candles[props.candles.length - 1].volume
  const volumePrecision = latestVolume >= 1 ? 2 : 6
  chart!.setPriceVolumePrecision(pricePrecision, volumePrecision)

  // Load data
  const klineData = props.candles.map((c) => ({
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
  addTradeMarkers()

  // Initialize slider to the end of data (chart default view)
  navPosition.value = props.candles.length - 1

  // Keep slider in sync when user zooms/scrolls directly on chart
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart!.subscribeAction('onZoom' as any, () => syncNavFromChart())
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart!.subscribeAction('onScroll' as any, () => syncNavFromChart())
}

function addIndicator(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  const isStack = !def.paneId
  const params = indicatorParams.value[name]
  chart.createIndicator({ name: def.key, calcParams: params } as any, isStack, { id: paneId })
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
  onParamChange(name)
}

function addTradeMarkers() {
  if (!chart || !props.trades || props.trades.length === 0) return

  // Build timestamp → low/high price maps from candle data
  const lowMap = new Map<number, number>()
  const highMap = new Map<number, number>()
  for (const c of props.candles) {
    lowMap.set(c.timestamp, c.low)
    highMap.set(c.timestamp, c.high)
  }

  // Find closest candle timestamp via binary search
  const sortedTs = props.candles.map(c => c.timestamp).sort((a, b) => a - b)
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

  function findLow(ts: number): number {
    const closest = lowMap.has(ts) ? ts : findClosestTs(ts)
    return lowMap.get(closest) ?? 0
  }

  function findHigh(ts: number): number {
    const closest = highMap.has(ts) ? ts : findClosestTs(ts)
    return highMap.get(closest) ?? 0
  }

  const overlays: any[] = []

  for (const trade of props.trades) {
    const entryTs = new Date(trade.entry_time).getTime()
    overlays.push({
      name: 'buyMarker',
      lock: true,
      points: [{ timestamp: entryTs, value: findLow(entryTs) }],
    })

    if (trade.exit_time && trade.exit_price) {
      const exitTs = new Date(trade.exit_time).getTime()
      overlays.push({
        name: 'sellMarker',
        lock: true,
        points: [{ timestamp: exitTs, value: findHigh(exitTs) }],
      })
    }
  }

  chart.createOverlay(overlays)
}

watch(() => [props.candles, props.trades], () => {
  if (chart && chartContainer.value) {
    dispose(chartContainer.value)
    chart = null
  }
  nextTick(() => initChart())
}, { deep: true })

onMounted(() => {
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
    margin-bottom: 8px;
  }

  .param-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;

    .param-label {
      font-size: 12px;
      color: #606266;
      min-width: 40px;
    }

    :deep(.el-input-number) {
      width: 130px;
    }
  }

  .el-button {
    margin-top: 4px;
    width: 100%;
  }
}
</style>

<template>
  <div ref="chartContainer" class="kline-chart" :style="{ height: height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { init, dispose, type Chart } from 'klinecharts'
import type { Candle } from '@/types'
import { getIndicatorDef, type IndicatorParams } from './indicatorConfig'

interface Props {
  data: Candle[]
  height?: string
  indicators?: string[]
  indicatorParams?: IndicatorParams
}

const props = withDefaults(defineProps<Props>(), {
  height: '500px',
  indicators: () => ['MA', 'VOL'],
})

const emit = defineEmits<{
  (e: 'crosshair', data: { timestamp: number; price: number } | null): void
}>()

const chartContainer = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null
let indicatorsCreated = false

function calculatePricePrecision(price: number): number {
  if (price >= 10000) return 2
  if (price >= 1000) return 3
  if (price >= 100) return 4
  if (price >= 1) return 5
  if (price >= 0.1) return 6
  if (price >= 0.01) return 7
  return 8
}

function initChart() {
  if (!chartContainer.value) return

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

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart?.subscribeAction('crosshair' as any, (data: any) => {
    if (data?.kLineData) {
      emit('crosshair', { timestamp: data.kLineData.timestamp, price: data.kLineData.close })
    } else {
      emit('crosshair', null)
    }
  })

  if (props.data.length > 0) {
    updateData(props.data)
    props.indicators.forEach((indicator) => addIndicator(indicator))
    indicatorsCreated = true
  }
}

function updateData(candles: Candle[]) {
  if (!chart || candles.length === 0) return

  const latestPrice = candles[candles.length - 1].close
  const pricePrecision = calculatePricePrecision(latestPrice)
  const latestVolume = candles[candles.length - 1].volume
  const volumePrecision = latestVolume >= 1 ? 2 : 6
  chart.setPriceVolumePrecision(pricePrecision, volumePrecision)

  const klineData = candles.map((c) => ({
    timestamp: c.timestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }))
  chart.applyNewData(klineData)
}

function updateCandle(candle: { timestamp: number; open: number; high: number; low: number; close: number; volume: number }) {
  if (!chart) return
  chart.updateData(candle)
}

function addIndicator(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  const isStack = !def.paneId
  const params = props.indicatorParams?.[name]
  chart.createIndicator(
    { name: def.key, ...(params ? { calcParams: params } : {}) } as any,
    isStack,
    { id: paneId },
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

function removeIndicator(name: string, paneId?: string) {
  if (!chart) return
  const def = getIndicatorDef(name)
  const resolvedPaneId = paneId ?? def?.paneId ?? 'candle_pane'
  chart.removeIndicator(resolvedPaneId, name)
}

function overrideIndicatorParams(name: string) {
  const def = getIndicatorDef(name)
  if (!chart || !def) return
  const paneId = def.paneId ?? 'candle_pane'
  const params = props.indicatorParams?.[name]
  if (params) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    chart.overrideIndicator({ name: def.key, calcParams: params } as any, paneId)
  }
}

watch(() => props.data, (newData) => {
  if (newData.length > 0) {
    updateData(newData)
    if (!indicatorsCreated && chart) {
      props.indicators.forEach((indicator) => addIndicator(indicator))
      indicatorsCreated = true
    }
  }
}, { deep: true })

watch(() => props.indicators, (newIndicators, oldIndicators) => {
  if (!chart) return

  const oldSet = new Set(oldIndicators || [])
  const newSet = new Set(newIndicators || [])

  oldIndicators?.forEach((indicator) => {
    if (!newSet.has(indicator)) {
      const def = getIndicatorDef(indicator)
      if (def) {
        const paneId = def.paneId ?? 'candle_pane'
        chart?.removeIndicator(paneId, def.key)
      }
    }
  })

  newIndicators?.forEach((indicator) => {
    if (!oldSet.has(indicator)) {
      addIndicator(indicator)
    }
  })
}, { deep: true })

watch(() => props.indicatorParams, () => {
  if (!chart) return
  props.indicators.forEach((name) => overrideIndicatorParams(name))
}, { deep: true })

onMounted(() => {
  initChart()
})

onUnmounted(() => {
  if (chartContainer.value) {
    dispose(chartContainer.value)
  }
})

defineExpose({
  addIndicator,
  removeIndicator,
  updateData,
  updateCandle,
})
</script>

<style lang="scss" scoped>
.kline-chart {
  width: 100%;
  background: #fff;
  border-radius: 4px;
}
</style>

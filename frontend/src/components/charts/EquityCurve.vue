<template>
  <div ref="chartRef" class="equity-chart" :style="{ height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { EquityPoint, Trade } from '@/types'
import { formatDateTime, formatNumber, formatPrice } from '@/utils/format'

interface Props {
  data: EquityPoint[]
  trades?: Trade[]
  height?: string
  showBenchmark?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: '300px',
  showBenchmark: false,
})

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

function getTimeFormat(data: EquityPoint[]): string {
  if (data.length < 2) return 'YYYY-MM-DD'
  const first = new Date(data[0].time).getTime()
  const last = new Date(data[data.length - 1].time).getTime()
  const spanDays = (last - first) / (1000 * 60 * 60 * 24)
  if (spanDays > 365) return 'YYYY-MM'
  if (spanDays > 30) return 'MM-DD'
  return 'MM-DD HH:mm'
}

/** Build a time→return% map from equity data for marker positioning */
function buildReturnMap(data: EquityPoint[], initialEquity: number): Map<number, number> {
  const map = new Map<number, number>()
  for (const d of data) {
    const ts = new Date(d.time).getTime()
    map.set(ts, (d.equity / initialEquity - 1) * 100)
  }
  return map
}

/** Find closest return % for a given trade time */
function findReturn(tradeTime: string, returnMap: Map<number, number>, sortedKeys: number[]): number | null {
  const target = new Date(tradeTime).getTime()
  // Exact match first
  if (returnMap.has(target)) return returnMap.get(target)!
  // Binary search for closest
  let lo = 0, hi = sortedKeys.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (sortedKeys[mid] < target) lo = mid + 1
    else hi = mid
  }
  // Check neighbors for closest
  const candidates = [sortedKeys[lo], sortedKeys[Math.max(0, lo - 1)]]
  let best = candidates[0]
  for (const c of candidates) {
    if (Math.abs(c - target) < Math.abs(best - target)) best = c
  }
  return returnMap.get(best) ?? null
}

function initChart() {
  if (!chartRef.value) return

  chart = echarts.init(chartRef.value)

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: any) => {
        if (!Array.isArray(params)) {
          // Single scatter point tooltip
          const item = params
          return item.data?.[3] || ''
        }
        const data = params[0]
        const time = formatDateTime(data.axisValue)
        let html = `<div style="font-size: 12px;">${time}</div>`

        params.forEach((item: any) => {
          if (item.seriesType === 'scatter') return
          const color = item.color
          const name = item.seriesName
          const rawValue = Array.isArray(item.value) ? item.value[1] : item.value
          const sign = rawValue > 0 ? '+' : ''
          const value = `${sign}${formatNumber(rawValue, 2)}%`
          html += `<div style="display: flex; align-items: center; gap: 4px;">
            <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ${color};"></span>
            <span>${name}: ${value}</span>
          </div>`
        })

        // Append trade markers at this time
        params.forEach((item: any) => {
          if (item.seriesType !== 'scatter') return
          const tooltip = item.data?.[3]
          if (tooltip) html += tooltip
        })

        return html
      },
    },
    legend: {
      show: false,
      top: 10,
      data: [],
    },
    grid: {
      left: 60,
      right: 20,
      top: 20,
      bottom: 60,
    },
    dataZoom: [
      {
        type: 'slider',
        xAxisIndex: 0,
        height: 20,
        bottom: 8,
        borderColor: '#ddd',
        fillerColor: 'rgba(24, 144, 255, 0.1)',
        handleStyle: { color: '#1890FF' },
      },
      {
        type: 'inside',
        xAxisIndex: 0,
      },
    ],
    xAxis: {
      type: 'time',
      axisLine: {
        lineStyle: { color: '#ddd' },
      },
      axisLabel: {
        color: '#909399',
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: {
        color: '#909399',
        formatter: (value: number) => `${formatNumber(value, 1)}%`,
      },
      splitLine: {
        lineStyle: { color: '#eee', type: 'dashed' },
      },
    },
    series: [
      {
        name: '策略收益',
        type: 'line',
        smooth: false,
        showSymbol: false,
        lineStyle: { width: 2, color: '#1890FF' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
            { offset: 1, color: 'rgba(24, 144, 255, 0.05)' },
          ]),
        },
        data: [],
      },
      {
        name: '基准收益（买入持有）',
        type: 'line',
        smooth: false,
        showSymbol: false,
        lineStyle: { width: 2, color: '#E6A23C', type: 'dashed' },
        data: [],
      },
      {
        name: '买入',
        type: 'scatter',
        symbolSize: 10,
        symbol: 'triangle',
        itemStyle: { color: '#67C23A' },
        z: 10,
        data: [],
      },
      {
        name: '卖出',
        type: 'scatter',
        symbolSize: 10,
        symbol: 'pin',
        itemStyle: { color: '#F56C6C' },
        z: 10,
        data: [],
      },
    ],
  }

  chart.setOption(option)
  updateData(props.data)
}

function updateData(data: EquityPoint[]) {
  if (!chart || data.length === 0) return

  const initialEquity = data[0].equity
  if (!initialEquity || initialEquity === 0) return

  // Convert to return % from initial equity
  const equityData = data.map((d) => [d.time, (d.equity / initialEquity - 1) * 100])

  const hasBenchmark = props.showBenchmark && data.some(d => d.benchmark_equity != null)
  const benchmarkData = hasBenchmark
    ? data.map((d) => {
        const bm = d.benchmark_equity ?? initialEquity
        return [d.time, (bm / initialEquity - 1) * 100]
      })
    : []

  // Build trade markers
  const buyData: any[] = []
  const sellData: any[] = []
  const trades = props.trades
  if (trades && trades.length > 0) {
    const returnMap = buildReturnMap(data, initialEquity)
    const sortedKeys = Array.from(returnMap.keys()).sort((a, b) => a - b)

    for (const t of trades) {
      // Buy marker at entry_time
      const entryReturn = findReturn(t.entry_time, returnMap, sortedKeys)
      if (entryReturn !== null) {
        const tip = `<div style="font-size: 12px; margin-top: 4px; border-top: 1px solid #eee; padding-top: 4px;">
          <span style="color: #67C23A; font-weight: bold;">▲ 买入</span>
          价格 ${formatPrice(t.entry_price)}　数量 ${formatNumber(t.amount, 4)}</div>`
        buyData.push([t.entry_time, entryReturn, t, tip])
      }

      // Sell marker at exit_time
      if (t.exit_time && t.exit_price) {
        const exitReturn = findReturn(t.exit_time, returnMap, sortedKeys)
        if (exitReturn !== null) {
          const pnlSign = t.pnl >= 0 ? '+' : ''
          const pnlColor = t.pnl >= 0 ? '#67C23A' : '#F56C6C'
          const tip = `<div style="font-size: 12px; margin-top: 4px; border-top: 1px solid #eee; padding-top: 4px;">
            <span style="color: #F56C6C; font-weight: bold;">▼ 卖出</span>
            价格 ${formatPrice(t.exit_price)}　盈亏 <span style="color: ${pnlColor}">${pnlSign}${formatNumber(t.pnl, 2)}</span></div>`
          sellData.push([t.exit_time, exitReturn, t, tip])
        }
      }
    }
  }

  const hasTrades = buyData.length > 0 || sellData.length > 0
  const legendData = ['策略收益']
  if (hasBenchmark) legendData.push('基准收益（买入持有）')
  if (hasTrades) { legendData.push('买入'); legendData.push('卖出') }

  const timeFormat = getTimeFormat(data)

  chart.setOption({
    legend: {
      show: hasBenchmark || hasTrades,
      data: legendData,
    },
    grid: {
      top: (hasBenchmark || hasTrades) ? 40 : 20,
    },
    xAxis: {
      axisLabel: {
        formatter: (value: number) => formatDateTime(value, timeFormat),
      },
    },
    series: [
      { data: equityData },
      { data: benchmarkData },
      { data: buyData },
      { data: sellData },
    ],
  })
}

function handleResize() {
  chart?.resize()
}

watch(() => [props.data, props.trades], () => {
  if (!chart) {
    initChart()
    return
  }
  updateData(props.data)
}, { deep: true })

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<style lang="scss" scoped>
.equity-chart {
  width: 100%;
}
</style>

<template>
  <div ref="chartRef" class="equity-chart" :style="{ height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import type { EquityPoint } from '@/types'
import { formatDateTime, formatNumber } from '@/utils/format'

interface Props {
  data: EquityPoint[]
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

function initChart() {
  if (!chartRef.value) return

  chart = echarts.init(chartRef.value)

  const hasBenchmark = props.showBenchmark && props.data.some(d => d.benchmark_equity != null)
  const timeFormat = getTimeFormat(props.data)

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const data = params[0]
        const time = formatDateTime(data.axisValue)
        let html = `<div style="font-size: 12px;">${time}</div>`

        params.forEach((item: any) => {
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

        return html
      },
    },
    legend: {
      show: hasBenchmark,
      top: 10,
      data: ['策略收益', '基准收益（买入持有）'],
    },
    grid: {
      left: 60,
      right: 20,
      top: hasBenchmark ? 40 : 20,
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
        formatter: (value: number) => formatDateTime(value, timeFormat),
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
    ],
  }

  if (hasBenchmark) {
    (option.series as any[]).push({
      name: '基准收益（买入持有）',
      type: 'line',
      smooth: false,
      showSymbol: false,
      lineStyle: { width: 2, color: '#E6A23C', type: 'dashed' },
      data: [],
    })
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

  const series: any[] = [{ data: equityData }]

  const hasBenchmark = props.showBenchmark && data.some(d => d.benchmark_equity != null)
  if (hasBenchmark) {
    const benchmarkData = data.map((d) => {
      const bm = d.benchmark_equity ?? initialEquity
      return [d.time, (bm / initialEquity - 1) * 100]
    })
    series.push({ data: benchmarkData })
  }

  chart.setOption({ series })
}

function handleResize() {
  chart?.resize()
}

watch(() => props.data, () => {
  if (chart) {
    chart.dispose()
    chart = null
  }
  initChart()
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

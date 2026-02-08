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

function initChart() {
  if (!chartRef.value) return

  chart = echarts.init(chartRef.value)

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
          const value = formatNumber(item.value, 2)
          html += `<div style="display: flex; align-items: center; gap: 4px;">
            <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ${color};"></span>
            <span>${name}: ${value}</span>
          </div>`
        })

        return html
      },
    },
    legend: {
      show: props.showBenchmark,
      top: 10,
      data: ['策略收益', '基准收益'],
    },
    grid: {
      left: 60,
      right: 20,
      top: props.showBenchmark ? 40 : 20,
      bottom: 30,
    },
    xAxis: {
      type: 'time',
      axisLine: {
        lineStyle: { color: '#ddd' },
      },
      axisLabel: {
        color: '#909399',
        formatter: (value: number) => formatDateTime(value, 'MM-DD'),
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: {
        color: '#909399',
        formatter: (value: number) => formatNumber(value, 0),
      },
      splitLine: {
        lineStyle: { color: '#eee', type: 'dashed' },
      },
    },
    series: [
      {
        name: '策略收益',
        type: 'line',
        smooth: true,
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

  if (props.showBenchmark) {
    (option.series as any[]).push({
      name: '基准收益',
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 2, color: '#909399', type: 'dashed' },
      data: [],
    })
  }

  chart.setOption(option)
  updateData(props.data)
}

function updateData(data: EquityPoint[]) {
  if (!chart) return

  const equityData = data.map((d) => [d.time, d.equity])
  const benchmarkData: unknown[] = []

  const series: any[] = [{ data: equityData }]
  if (props.showBenchmark) {
    series.push({ data: benchmarkData })
  }

  chart.setOption({ series })
}

function handleResize() {
  chart?.resize()
}

watch(() => props.data, (newData) => {
  updateData(newData)
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

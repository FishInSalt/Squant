<template>
  <div ref="chartRef" class="pie-chart" :style="{ height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'
import { formatNumber } from '@/utils/format'

interface PieDataItem {
  name: string
  value: number
}

interface Props {
  data: PieDataItem[]
  height?: string
  title?: string
  showLegend?: boolean
  roseType?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: '300px',
  title: '',
  showLegend: true,
  roseType: false,
})

const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const colors = [
  '#1890FF',
  '#4CAF50',
  '#FF9800',
  '#FF4D4F',
  '#9C27B0',
  '#00BCD4',
  '#E91E63',
  '#3F51B5',
  '#009688',
  '#FFC107',
]

function initChart() {
  if (!chartRef.value) return

  chart = echarts.init(chartRef.value)

  const total = props.data.reduce((sum, item) => sum + item.value, 0)

  const option: echarts.EChartsOption = {
    title: props.title
      ? {
          text: props.title,
          left: 'center',
          textStyle: { fontSize: 14, fontWeight: 500 },
        }
      : undefined,
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const percent = total > 0 ? ((params.value / total) * 100).toFixed(2) : '0.00'
        return `${params.name}<br/>
          <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ${params.color}; margin-right: 4px;"></span>
          ${formatNumber(params.value, 2)} (${percent}%)`
      },
    },
    legend: {
      show: props.showLegend,
      orient: 'vertical',
      right: 20,
      top: 'center',
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: '#606266', fontSize: 12 },
    },
    color: colors,
    series: [
      {
        type: 'pie',
        radius: props.roseType ? ['30%', '70%'] : ['40%', '70%'],
        center: props.showLegend ? ['40%', '50%'] : ['50%', '50%'],
        roseType: props.roseType ? 'radius' : undefined,
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 4,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          position: 'outside',
          formatter: (params: any) => {
            const percent = total > 0 ? ((params.value / total) * 100).toFixed(1) : '0.0'
            return `${params.name}\n${percent}%`
          },
          fontSize: 11,
          color: '#606266',
        },
        labelLine: {
          show: true,
          length: 10,
          length2: 10,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.2)',
          },
        },
        data: props.data,
      },
    ],
  }

  chart.setOption(option)
}

function updateData(data: PieDataItem[]) {
  if (!chart) return

  chart.setOption({
    series: [{ data }],
  })
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
.pie-chart {
  width: 100%;
}
</style>

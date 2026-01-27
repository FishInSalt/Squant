<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { createChart, type IChartApi, ColorType, CrosshairMode, CandlestickSeries } from 'lightweight-charts'
import type { KLine } from '@/types/market'

interface Props {
  data: KLine[]
  height?: number
  symbol?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: 400
})

const emit = defineEmits<{
  ready: [chart: IChartApi]
}>()

const chartContainer = ref<HTMLElement>()
let chart: IChartApi | null = null
let candleSeries: any = null

// 初始化图表
const initChart = () => {
  if (!chartContainer.value) return

  chart = createChart(chartContainer.value, {
    width: chartContainer.value.clientWidth,
    height: props.height,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: '#333'
    },
    grid: {
      vertLines: { color: '#f0f0f0' },
      horzLines: { color: '#f0f0f0' }
    },
    crosshair: {
      mode: CrosshairMode.Normal
    },
    rightPriceScale: {
      borderColor: '#f0f0f0'
    },
    timeScale: {
      borderColor: '#f0f0f0',
      timeVisible: true,
      secondsVisible: false
    }
   })

    // 添加 K 线系列
    candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350'
    })

  // 加载数据
  candleSeries.setData(props.data)

  // 监听大小变化
  const resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      if (chart) {
        chart.applyOptions({
          width: entry.contentRect.width
        })
      }
    }
  })
  resizeObserver.observe(chartContainer.value)

  // 通知父组件图表已就绪
  emit('ready', chart)
}

// 监听数据变化
watch(() => props.data, (newData) => {
  if (candleSeries) {
    candleSeries.setData(newData)
  }
})

// 监听交易对变化
watch(() => props.symbol, () => {
  if (chart) {
    chart.timeScale().fitContent()
  }
})

onMounted(() => {
  initChart()
})

onUnmounted(() => {
  if (chart) {
    chart.remove()
  }
})
</script>

<template>
  <div ref="chartContainer" class="k-line-chart"></div>
</template>

<style scoped lang="scss">
.k-line-chart {
  width: 100%;
  background: #fff;
  border-radius: 8px;
}
</style>

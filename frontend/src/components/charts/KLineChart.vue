<template>
  <div ref="chartContainer" class="kline-chart" :style="{ height: height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { init, dispose, type Chart } from 'klinecharts'
import type { Candle } from '@/types'

interface Props {
  data: Candle[]
  height?: string
  indicators?: string[]
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
let indicatorsCreated = false  // 跟踪指标是否已创建

const indicatorMapping: Record<string, { name: string; paneId?: string; colors?: string[] }> = {
  // MA: 4 条线 (MA5/MA10/MA30/MA60)
  MA: { name: 'MA', colors: ['#FF9600', '#935EBD', '#2196F3', '#E040FB'] },
  // EMA: 3 条线 (EMA6/EMA12/EMA20)
  EMA: { name: 'EMA', colors: ['#E11D74', '#01C5C4', '#4CAF50'] },
  // BOLL: 3 条线 (MID/UPPER/LOWER)
  BOLL: { name: 'BOLL', colors: ['#FF6D00', '#0D47A1', '#00897B'] },
  VOL: { name: 'VOL', paneId: 'volume' },
  MACD: { name: 'MACD', paneId: 'macd' },
  RSI: { name: 'RSI', paneId: 'rsi' },
  KDJ: { name: 'KDJ', paneId: 'kdj' },
}

/**
 * 根据价格计算合适的小数位数
 * @param price 价格
 * @returns 小数位数
 */
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
      horizontal: {
        show: true,
        size: 1,
        color: '#EDEDED',
        style: 'dashed',
      },
      vertical: {
        show: true,
        size: 1,
        color: '#EDEDED',
        style: 'dashed',
      },
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
      tooltip: {
        showRule: 'follow_cross',
        showType: 'standard',
      },
    },
    indicator: {
      tooltip: {
        showRule: 'follow_cross',
        showType: 'standard',
      },
    },
    xAxis: {
      show: true,
      axisLine: {
        show: true,
        color: '#DDDDDD',
      },
      tickLine: {
        show: true,
        color: '#DDDDDD',
      },
      tickText: {
        show: true,
        color: '#909399',
      },
    },
    yAxis: {
      show: true,
      axisLine: {
        show: true,
        color: '#DDDDDD',
      },
      tickLine: {
        show: true,
        color: '#DDDDDD',
      },
      tickText: {
        show: true,
        color: '#909399',
      },
    },
    crosshair: {
      show: true,
      horizontal: {
        show: true,
        line: {
          show: true,
          style: 'dashed',
          color: '#909399',
        },
        text: {
          show: true,
          color: '#FFFFFF',
          backgroundColor: '#1890FF',
        },
      },
      vertical: {
        show: true,
        line: {
          show: true,
          style: 'dashed',
          color: '#909399',
        },
        text: {
          show: true,
          color: '#FFFFFF',
          backgroundColor: '#1890FF',
        },
      },
    },
  }

  chart = init(chartContainer.value, { styles })

  // 监听十字线
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  chart?.subscribeAction('crosshair' as any, (data: any) => {
    if (data?.kLineData) {
      emit('crosshair', {
        timestamp: data.kLineData.timestamp,
        price: data.kLineData.close,
      })
    } else {
      emit('crosshair', null)
    }
  })

  // 加载数据（指标计算依赖数据，所以先加载数据再创建指标）
  if (props.data.length > 0) {
    updateData(props.data)
    // 数据加载后创建指标，确保 MA 等指标能正确计算
    props.indicators.forEach((indicator) => {
      addIndicator(indicator)
    })
    indicatorsCreated = true
  }
}

function updateData(candles: Candle[]) {
  if (!chart || candles.length === 0) return

  // 根据价格计算合适的精度
  const latestPrice = candles[candles.length - 1].close
  const pricePrecision = calculatePricePrecision(latestPrice)
  // 成交量精度：根据成交量大小动态调整
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

/**
 * 实时更新单根 K 线
 * @param candle K线数据
 */
function updateCandle(candle: { timestamp: number; open: number; high: number; low: number; close: number; volume: number }) {
  if (!chart) return
  chart.updateData(candle)
}

function addIndicator(name: string) {
  const config = indicatorMapping[name]
  if (chart && config) {
    const paneId = config.paneId ?? 'candle_pane'
    const isStack = !config.paneId
    chart.createIndicator(config.name, isStack, { id: paneId })
    // 用 overrideIndicator 设置自定义颜色，避免同类指标颜色重复
    if (config.colors) {
      chart.overrideIndicator({
        name: config.name,
        styles: {
          lines: config.colors.map((color) => ({
            style: 'solid' as const,
            smooth: false,
            size: 1,
            dashedValue: [2, 2],
            color,
          })),
        },
      }, paneId)
    }
  }
}

function removeIndicator(paneId: string) {
  if (chart) {
    chart.removeIndicator(paneId)
  }
}

watch(() => props.data, (newData) => {
  if (newData.length > 0) {
    updateData(newData)
    // 数据首次加载后创建指标
    if (!indicatorsCreated && chart) {
      props.indicators.forEach((indicator) => {
        addIndicator(indicator)
      })
      indicatorsCreated = true
    }
  }
}, { deep: true })

// 监听指标变化
watch(() => props.indicators, (newIndicators, oldIndicators) => {
  if (!chart) return

  const oldSet = new Set(oldIndicators || [])
  const newSet = new Set(newIndicators || [])

  // 移除不再需要的指标
  oldIndicators?.forEach((indicator) => {
    if (!newSet.has(indicator)) {
      const config = indicatorMapping[indicator]
      if (config) {
        if (config.paneId) {
          // 副图指标：移除整个 pane
          chart?.removeIndicator(config.paneId, config.name)
        } else {
          // 主图指标：从主图移除
          chart?.removeIndicator('candle_pane', config.name)
        }
      }
    }
  })

  // 添加新指标
  newIndicators?.forEach((indicator) => {
    if (!oldSet.has(indicator)) {
      addIndicator(indicator)
    }
  })
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

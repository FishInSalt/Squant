<script setup lang="ts">
import { computed } from 'vue'
import type { Ticker } from '@/types/market'
import { formatPrice, formatPercentage, formatVolume } from '@/utils'

interface Props {
  ticker?: Ticker
  active?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  active: false
})

const emit = defineEmits<{
  click: []
}>()

// 计算涨跌幅
const changePercent = computed(() => {
  return props.ticker?.priceChangePercent || 0
})

// 判断是否上涨
const isPositive = computed(() => {
  return changePercent.value >= 0
})

// 格式化价格（根据价格决定小数位数）
const formattedPrice = computed(() => {
  const price = props.ticker?.lastPrice || 0
  const decimals = price < 1 ? 6 : 2
  return formatPrice(price, decimals)
})
</script>

<template>
  <div
    v-if="ticker"
    class="ticker-card"
    :class="{ active, positive: isPositive, negative: !isPositive }"
    @click="emit('click')"
  >
    <div class="ticker-header">
      <span class="symbol">{{ ticker.symbol.replace('-', '/') }}</span>
      <span class="change">
        {{ isPositive ? '+' : '' }}{{ formatPercentage(changePercent) }}
      </span>
    </div>
    <div class="ticker-price">
      {{ formattedPrice }}
    </div>
    <div class="ticker-info">
      <div class="info-item">
        <span class="label">24h 高</span>
        <span class="value">{{ formatPrice(ticker.highPrice, 2) }}</span>
      </div>
      <div class="info-item">
        <span class="label">24h 低</span>
        <span class="value">{{ formatPrice(ticker.lowPrice, 2) }}</span>
      </div>
      <div class="info-item">
        <span class="label">24h 量</span>
        <span class="value">{{ formatVolume(ticker.volume) }}</span>
      </div>
    </div>
  </div>
  <div v-else class="ticker-card empty">
    <div class="ticker-header">
      <span class="symbol">暂无数据</span>
    </div>
    <div class="ticker-price">
      ---
    </div>
  </div>
</template>

<style scoped lang="scss">
.ticker-card {
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s;
  cursor: pointer;
  border: 2px solid transparent;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    transform: translateY(-2px);
  }

  &.active {
    border-color: #409eff;
  }

  .ticker-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .symbol {
      font-size: 16px;
      font-weight: 600;
      color: #303133;
    }

    .change {
      font-size: 14px;
      font-weight: 500;
    }
  }

  .ticker-price {
    font-size: 24px;
    font-weight: 700;
    margin-bottom: 12px;
  }

  .ticker-info {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .info-item {
      display: flex;
      justify-content: space-between;

      .label {
        font-size: 12px;
        color: #909399;
      }

      .value {
        font-size: 14px;
        font-weight: 500;
      }
    }
  }

  &.positive {
    .ticker-price,
    .change {
      color: #67c23a;
    }
  }

  &.negative {
    .ticker-price,
    .change {
      color: #f56c6c;
    }
  }

  &.empty {
    opacity: 0.5;
    pointer-events: none;

    .symbol {
      color: #909399;
    }
  }
}
</style>

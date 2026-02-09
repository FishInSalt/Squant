<template>
  <span :class="[priceClass, flashClass]">
    <span v-if="showSign && change !== 0">{{ change > 0 ? '+' : '' }}</span>
    {{ displayValue }}{{ suffix }}
    <span v-if="showPercent && percent !== undefined" class="percent">
      ({{ percentDisplay }})
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { formatPrice, formatPercent } from '@/utils/format'

interface Props {
  value: number
  change?: number
  percent?: number
  decimals?: number
  showSign?: boolean
  showPercent?: boolean
  neutral?: boolean
  suffix?: string
}

const props = withDefaults(defineProps<Props>(), {
  change: 0,
  decimals: undefined,
  showSign: false,
  showPercent: false,
  neutral: false,
  suffix: '',
})

const priceClass = computed(() => {
  if (props.neutral) return 'price-neutral'
  if (props.change > 0) return 'price-up'
  if (props.change < 0) return 'price-down'
  return 'price-neutral'
})

const displayValue = computed(() => {
  if (props.value === null || props.value === undefined) return '-'
  if (props.decimals !== undefined) {
    return props.value.toFixed(props.decimals)
  }
  return formatPrice(props.value)
})

const percentDisplay = computed(() => {
  if (props.percent === undefined) return ''
  return formatPercent(props.percent)
})

const flashClass = ref('')
let flashTimer: ReturnType<typeof setTimeout> | null = null

watch(() => props.value, (newVal, oldVal) => {
  if (oldVal === undefined || oldVal === null || newVal === oldVal) return
  if (flashTimer) clearTimeout(flashTimer)
  flashClass.value = newVal > oldVal ? 'flash-up' : 'flash-down'
  flashTimer = setTimeout(() => {
    flashClass.value = ''
  }, 600)
})
</script>

<style lang="scss" scoped>
.price-up {
  color: #00C853;
}

.price-down {
  color: #FF1744;
}

.price-neutral {
  color: #909399;
}

.percent {
  font-size: 0.9em;
  margin-left: 4px;
}

.flash-up {
  animation: flash-green 0.6s ease-out;
}

.flash-down {
  animation: flash-red 0.6s ease-out;
}

@keyframes flash-green {
  0% { background-color: rgba(0, 200, 83, 0.3); }
  100% { background-color: transparent; }
}

@keyframes flash-red {
  0% { background-color: rgba(255, 23, 68, 0.3); }
  100% { background-color: transparent; }
}
</style>

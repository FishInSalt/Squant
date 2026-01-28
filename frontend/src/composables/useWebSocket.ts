import { onMounted, onUnmounted } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'

/**
 * WebSocket 连接管理
 */
export function useWebSocket() {
  const wsStore = useWebSocketStore()

  onMounted(() => {
    wsStore.connect()
  })

  return {
    connected: wsStore.isConnected,
    subscribe: wsStore.subscribe,
    unsubscribe: wsStore.unsubscribe,
  }
}

/**
 * 订阅行情更新
 */
export function useTickerSubscription(
  symbols: string | string[],
  autoConnect = true
) {
  const wsStore = useWebSocketStore()
  const symbolList = Array.isArray(symbols) ? symbols : [symbols]
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    if (autoConnect) {
      wsStore.connect()
    }
    unsubscribe = wsStore.subscribeToTickers(symbolList)
  })

  onUnmounted(() => {
    if (unsubscribe) {
      unsubscribe()
    }
  })

  return {
    connected: wsStore.isConnected,
  }
}

/**
 * 订阅 K 线数据
 */
export function useCandleSubscription(
  symbol: string,
  timeframe: string,
  autoConnect = true
) {
  const wsStore = useWebSocketStore()
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    if (autoConnect) {
      wsStore.connect()
    }
    unsubscribe = wsStore.subscribeToCandles(symbol, timeframe)
  })

  onUnmounted(() => {
    if (unsubscribe) {
      unsubscribe()
    }
  })

  return {
    connected: wsStore.isConnected,
  }
}

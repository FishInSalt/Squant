import { onMounted, onUnmounted } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'
import type { WebSocketMessage, RunLog } from '@/types'

// WebSocket 连接管理
export function useWebSocket() {
  const wsStore = useWebSocketStore()

  onMounted(() => {
    wsStore.connect()
  })

  onUnmounted(() => {
    // 不在这里断开连接，因为可能有其他组件还在使用
  })

  return {
    connected: wsStore.isConnected,
    subscribe: wsStore.subscribe,
    unsubscribe: wsStore.unsubscribe,
    send: wsStore.send,
    addMessageHandler: wsStore.addMessageHandler,
    removeMessageHandler: wsStore.removeMessageHandler,
  }
}

// 订阅行情更新
export function useTickerSubscription(
  exchange: string,
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
    unsubscribe = wsStore.subscribeToTickers(exchange, symbolList)
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

// 订阅会话日志
export function useSessionLogs(
  sessionId: string,
  onLog: (log: RunLog) => void,
  autoConnect = true
) {
  const wsStore = useWebSocketStore()
  let unsubscribe: (() => void) | null = null

  onMounted(() => {
    if (autoConnect) {
      wsStore.connect()
    }
    unsubscribe = wsStore.subscribeToSessionLogs(sessionId, onLog)
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

// 自定义消息处理
export function useWebSocketMessage(
  type: string,
  handler: (message: WebSocketMessage) => void,
  autoConnect = true
) {
  const wsStore = useWebSocketStore()

  onMounted(() => {
    if (autoConnect) {
      wsStore.connect()
    }
    wsStore.addMessageHandler(type, handler)
  })

  onUnmounted(() => {
    wsStore.removeMessageHandler(type, handler)
  })

  return {
    connected: wsStore.isConnected,
  }
}

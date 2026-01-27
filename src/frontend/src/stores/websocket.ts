// WebSocket Store

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useWebSocketStore = defineStore('websocket', () => {
  // ========== State ==========
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 5
  const reconnectInterval = 3000 // 3秒

  // ========== Getters ==========
  const isConnecting = computed(() => {
    return ws.value?.readyState === WebSocket.CONNECTING
  })

  const isReady = computed(() => {
    return ws.value?.readyState === WebSocket.OPEN
  })

  // ========== Actions ==========
  /**
   * 连接 WebSocket
   */
  const connect = (url: string) => {
    if (ws.value?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected')
      return
    }

    console.log('Connecting to WebSocket:', url)
    ws.value = new WebSocket(url)

    ws.value.onopen = () => {
      connected.value = true
      reconnectAttempts.value = 0
      console.log('WebSocket connected')
    }

    ws.value.onclose = () => {
      connected.value = false
      console.log('WebSocket disconnected')

      // 自动重连
      if (reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        console.log(`Reconnecting... (${reconnectAttempts.value}/${maxReconnectAttempts})`)
        setTimeout(() => connect(url), reconnectInterval)
      } else {
        console.error('Max reconnect attempts reached')
      }
    }

    ws.value.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.value.onmessage = (event) => {
      handleMessage(event.data)
    }
  }

  /**
   * 断开连接
   */
  const disconnect = () => {
    ws.value?.close()
    ws.value = null
    connected.value = false
    reconnectAttempts.value = 0
    console.log('WebSocket disconnected by user')
  }

  /**
   * 发送消息
   */
  const send = (message: any) => {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket is not connected')
    }
  }

  /**
   * 处理消息
   */
  const handleMessage = (data: string) => {
    try {
      const message = JSON.parse(data)
      console.log('WebSocket message:', message)

      // TODO: 分发到对应的 store
      // switch (message.channel) {
      //   case 'ticker':
      //     const marketStore = useMarketStore()
      //     marketStore.updateTicker(message.data)
      //     break
      // }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error)
    }
  }

  return {
    // State
    ws,
    connected,
    reconnectAttempts,

    // Getters
    isConnecting,
    isReady,

    // Actions
    connect,
    disconnect,
    send
  }
})

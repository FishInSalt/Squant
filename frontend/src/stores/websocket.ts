import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { WebSocketMessage, Ticker, BacktestRun, PaperSession, LiveSession, RunLog } from '@/types'
import { useMarketStore } from './market'
import { useTradingStore } from './trading'

type MessageHandler = (message: WebSocketMessage) => void

export const useWebSocketStore = defineStore('websocket', () => {
  // State
  const socket = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 5
  const baseReconnectDelay = 1000 // 初始重连延迟 1秒
  const maxReconnectDelay = 30000 // 最大重连延迟 30秒
  const subscribedChannels = ref<Set<string>>(new Set())
  const messageHandlers = ref<Map<string, MessageHandler[]>>(new Map())

  // 计算指数退避延迟
  function getReconnectDelay(): number {
    const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts.value)
    return Math.min(delay, maxReconnectDelay)
  }

  // Getters
  const isConnected = computed(() => connected.value)

  // Actions
  function connect() {
    if (socket.value?.readyState === WebSocket.OPEN) {
      return
    }

    const wsUrl = import.meta.env.VITE_WS_BASE_URL || '/ws'
    const fullUrl = wsUrl.startsWith('ws') ? wsUrl : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${wsUrl}`

    socket.value = new WebSocket(fullUrl)

    socket.value.onopen = () => {
      connected.value = true
      reconnectAttempts.value = 0

      // Resubscribe to channels
      subscribedChannels.value.forEach((channel) => {
        send({ type: 'subscribe', channel })
      })
    }

    socket.value.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data)
        handleMessage(message)
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    socket.value.onclose = () => {
      connected.value = false

      // Attempt reconnect with exponential backoff
      if (reconnectAttempts.value < maxReconnectAttempts) {
        const delay = getReconnectDelay()
        reconnectAttempts.value++
        setTimeout(() => {
          connect()
        }, delay)
      }
    }

    socket.value.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  function disconnect() {
    if (socket.value) {
      socket.value.close()
      socket.value = null
    }
    connected.value = false
    subscribedChannels.value.clear()
  }

  function send(data: Record<string, unknown>) {
    if (socket.value?.readyState === WebSocket.OPEN) {
      socket.value.send(JSON.stringify(data))
    }
  }

  function subscribe(channel: string) {
    subscribedChannels.value.add(channel)
    if (connected.value) {
      send({ type: 'subscribe', channel })
    }
  }

  function unsubscribe(channel: string) {
    subscribedChannels.value.delete(channel)
    if (connected.value) {
      send({ type: 'unsubscribe', channel })
    }
  }

  function addMessageHandler(type: string, handler: MessageHandler) {
    if (!messageHandlers.value.has(type)) {
      messageHandlers.value.set(type, [])
    }
    messageHandlers.value.get(type)!.push(handler)
  }

  function removeMessageHandler(type: string, handler: MessageHandler) {
    const handlers = messageHandlers.value.get(type)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index !== -1) {
        handlers.splice(index, 1)
      }
    }
  }

  function handleMessage(message: WebSocketMessage) {
    const marketStore = useMarketStore()
    const tradingStore = useTradingStore()

    // Handle built-in message types
    switch (message.type) {
      case 'ticker':
        marketStore.updateTicker(message.data as Ticker)
        break
      case 'backtest_update':
        tradingStore.updateBacktest(message.data as BacktestRun)
        break
      case 'paper_update':
        tradingStore.updatePaperSession(message.data as PaperSession)
        break
      case 'live_update':
        tradingStore.updateLiveSession(message.data as LiveSession)
        break
      case 'log':
        // Emit to registered handlers
        break
    }

    // Call custom handlers
    const handlers = messageHandlers.value.get(message.type)
    if (handlers) {
      handlers.forEach((handler) => handler(message))
    }

    // Call wildcard handlers
    const wildcardHandlers = messageHandlers.value.get('*')
    if (wildcardHandlers) {
      wildcardHandlers.forEach((handler) => handler(message))
    }
  }

  // Subscribe to specific session logs
  function subscribeToSessionLogs(sessionId: string, onLog: (log: RunLog) => void) {
    const channel = `session:${sessionId}:logs`
    subscribe(channel)

    const handler: MessageHandler = (message) => {
      if (message.channel === channel && message.type === 'log') {
        onLog(message.data as RunLog)
      }
    }

    addMessageHandler('log', handler)

    return () => {
      unsubscribe(channel)
      removeMessageHandler('log', handler)
    }
  }

  // Subscribe to ticker updates for specific symbols
  function subscribeToTickers(exchange: string, symbols: string[]) {
    symbols.forEach((symbol) => {
      subscribe(`ticker:${exchange}:${symbol}`)
    })

    return () => {
      symbols.forEach((symbol) => {
        unsubscribe(`ticker:${exchange}:${symbol}`)
      })
    }
  }

  return {
    // State
    connected,
    reconnectAttempts,
    subscribedChannels,
    // Getters
    isConnected,
    // Actions
    connect,
    disconnect,
    send,
    subscribe,
    unsubscribe,
    addMessageHandler,
    removeMessageHandler,
    subscribeToSessionLogs,
    subscribeToTickers,
  }
})

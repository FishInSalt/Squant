import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { Ticker } from '@/types'
import { useMarketStore } from './market'

/**
 * WebSocket 消息类型
 */
interface WSMessage {
  type: string
  channel?: string
  data?: Record<string, unknown>
  message?: string
}

/**
 * 后端 Ticker 数据格式
 */
interface WSTickerData {
  symbol: string
  last: string
  bid: string | null
  ask: string | null
  bid_size: string | null
  ask_size: string | null
  high_24h: string | null
  low_24h: string | null
  volume_24h: string | null
  volume_quote_24h: string | null
  open_24h: string | null
  timestamp: string
}

/**
 * 后端 Candle 数据格式
 */
interface WSCandleData {
  symbol: string
  timeframe: string
  timestamp: string
  open: string
  high: string
  low: string
  close: string
  volume: string
  is_closed: boolean  // Backend uses is_closed
}

/**
 * 前端 Candle 数据格式
 */
export interface CandleUpdate {
  symbol: string
  timeframe: string
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_closed: boolean  // Whether the candle is finalized
}

// Candle 更新回调类型
type CandleCallback = (candle: CandleUpdate) => void

// 将 candleCallbacks 移到 store 外部，避免热更新时被重置
const candleCallbacks = new Map<string, Set<CandleCallback>>()

export const useWebSocketStore = defineStore('websocket', () => {
  // State
  const socket = ref<WebSocket | null>(null)
  const connected = ref(false)
  const connecting = ref(false)  // 正在连接中标志
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 5
  const baseReconnectDelay = 1000
  const maxReconnectDelay = 30000
  const subscribedChannels = ref<Set<string>>(new Set())
  const pendingSubscriptions = ref<Set<string>>(new Set())
  const serviceUnavailable = ref(false)  // 服务不可用标志（后端 WebSocket 连接失败）
  const serviceUnavailableMessage = ref('')  // 服务不可用消息
  const exchangeSwitching = ref(false)  // 交易所切换中标志
  const switchingFromExchange = ref('')  // 切换前的交易所
  const switchingToExchange = ref('')  // 切换后的交易所

  // 心跳定时器
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  // candleCallbacks 已移到 store 外部，避免热更新时被重置

  // 计算指数退避延迟
  function getReconnectDelay(): number {
    const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts.value)
    return Math.min(delay, maxReconnectDelay)
  }

  // Getters
  const isConnected = computed(() => connected.value)

  /**
   * 连接 WebSocket 网关
   */
  function connect() {
    // 如果已连接或正在连接，不重复连接
    if (connected.value || connecting.value) {
      return
    }

    // 检查 socket 状态
    if (socket.value?.readyState === WebSocket.OPEN ||
        socket.value?.readyState === WebSocket.CONNECTING) {
      return
    }

    // 设置连接中标志
    connecting.value = true

    // 清理之前的连接（已关闭或关闭中的）
    cleanup()

    const wsUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000/api/v1/ws'
    console.debug(`Connecting to WebSocket: ${wsUrl}`)

    try {
      socket.value = new WebSocket(wsUrl)
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      connecting.value = false
      scheduleReconnect()
      return
    }

    socket.value.onopen = () => {
      console.info('WebSocket connected')
      connected.value = true
      connecting.value = false
      reconnectAttempts.value = 0

      // 启动心跳
      startHeartbeat()

      // 重新订阅之前的频道
      subscribedChannels.value.forEach((channel) => {
        sendSubscribe(channel)
      })

      // 处理待订阅的频道
      pendingSubscriptions.value.forEach((channel) => {
        sendSubscribe(channel)
        subscribedChannels.value.add(channel)
      })
      pendingSubscriptions.value.clear()
    }

    socket.value.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data)
        handleMessage(message)
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    socket.value.onclose = (event) => {
      console.debug(`WebSocket closed: code=${event.code}, reason=${event.reason}`)
      connected.value = false
      connecting.value = false
      stopHeartbeat()

      // 4503 是后端返回的服务不可用代码，不需要重连
      if (event.code === 4503) {
        serviceUnavailable.value = true
        console.info('Service unavailable (code 4503), not reconnecting')
        return
      }

      scheduleReconnect()
    }

    socket.value.onerror = (error) => {
      console.warn('WebSocket error:', error)
      // 注意：onerror 后通常会触发 onclose，所以不需要在这里重置 connecting
    }
  }

  /**
   * 断开连接
   */
  function disconnect() {
    connecting.value = false
    cleanup()
    subscribedChannels.value.clear()
    pendingSubscriptions.value.clear()
  }

  /**
   * 清理资源
   */
  function cleanup() {
    stopHeartbeat()

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    if (socket.value) {
      socket.value.onopen = null
      socket.value.onclose = null // 防止触发重连
      socket.value.onerror = null
      socket.value.onmessage = null
      socket.value.close()
      socket.value = null
    }

    connected.value = false
    // 注意：不在这里重置 connecting，由调用者决定
  }

  /**
   * 安排重连
   */
  function scheduleReconnect() {
    // 如果服务不可用，不重连
    if (serviceUnavailable.value) {
      console.info('Service unavailable, not reconnecting')
      return
    }

    if (reconnectAttempts.value >= maxReconnectAttempts) {
      console.warn('Max reconnect attempts reached')
      return
    }

    const delay = getReconnectDelay()
    console.info(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts.value + 1}/${maxReconnectAttempts})`)

    reconnectTimer = setTimeout(() => {
      reconnectAttempts.value++
      connect()
    }, delay)
  }

  /**
   * 启动心跳
   */
  function startHeartbeat() {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => {
      if (socket.value?.readyState === WebSocket.OPEN) {
        socket.value.send('ping')
      }
    }, 30000)
  }

  /**
   * 停止心跳
   */
  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  /**
   * 发送消息
   */
  function send(data: Record<string, unknown>) {
    if (socket.value?.readyState === WebSocket.OPEN) {
      socket.value.send(JSON.stringify(data))
    }
  }

  /**
   * 发送订阅消息
   */
  function sendSubscribe(channel: string) {
    send({ type: 'subscribe', channel })
  }

  /**
   * 发送取消订阅消息
   */
  function sendUnsubscribe(channel: string) {
    send({ type: 'unsubscribe', channel })
  }

  /**
   * 订阅频道
   */
  function subscribe(channel: string) {
    if (subscribedChannels.value.has(channel)) {
      return
    }

    if (connected.value) {
      sendSubscribe(channel)
      subscribedChannels.value.add(channel)
    } else {
      // 连接未建立，加入待订阅列表
      pendingSubscriptions.value.add(channel)
      // 尝试连接
      connect()
    }
  }

  /**
   * 取消订阅频道
   */
  function unsubscribe(channel: string) {
    if (!subscribedChannels.value.has(channel)) {
      pendingSubscriptions.value.delete(channel)
      return
    }

    if (connected.value) {
      sendUnsubscribe(channel)
    }
    subscribedChannels.value.delete(channel)
  }

  /**
   * 处理收到的消息
   */
  function handleMessage(message: WSMessage) {
    const marketStore = useMarketStore()

    switch (message.type) {
      case 'pong':
        // 心跳响应，忽略
        break

      case 'subscribed':
        console.debug(`Subscribed to ${message.channel}`)
        break

      case 'unsubscribed':
        console.debug(`Unsubscribed from ${message.channel}`)
        break

      case 'error':
        console.warn(`WebSocket error: ${message.message}`)
        // 检查是否是服务不可用错误
        if ((message as { code?: string }).code === 'STREAM_UNAVAILABLE') {
          serviceUnavailable.value = true
          serviceUnavailableMessage.value = message.message || '实时数据服务不可用'
          console.warn('Real-time data service unavailable, will not reconnect')
        }
        break

      case 'ticker':
        if (message.data) {
          const tickerUpdate = transformTicker(message.data as unknown as WSTickerData)
          // Only update price fields, preserve volume data from REST API
          // WebSocket volume data from OKX appears to be unreliable
          marketStore.updateTickerPrice(tickerUpdate)
        }
        break

      case 'candle':
        if (message.data && message.channel) {
          const candleData = message.data as unknown as WSCandleData
          const candle = transformCandle(candleData)
          // 通知所有订阅了该 channel 的回调
          const callbacks = candleCallbacks.get(message.channel)
          if (callbacks && callbacks.size > 0) {
            callbacks.forEach((cb) => cb(candle))
          }
        }
        break

      case 'trade':
        // TODO: 处理成交数据
        break

      case 'orderbook':
        // TODO: 处理订单簿数据
        break

      case 'order_update':
        // TODO: 处理订单更新
        break

      case 'account_update':
        // TODO: 处理账户更新
        break

      case 'exchange_switching':
        // 处理交易所切换状态
        if (message.data) {
          const switchData = message.data as { from: string; to: string; status: string }
          switchingFromExchange.value = switchData.from
          switchingToExchange.value = switchData.to
          exchangeSwitching.value = switchData.status === 'switching'
          console.info(`Exchange switching: ${switchData.from} -> ${switchData.to} (${switchData.status})`)
          // Show notification
          if (switchData.status === 'switching') {
            ElMessage.info(`WebSocket 正在切换到 ${switchData.to.toUpperCase()}...`)
          } else if (switchData.status === 'completed') {
            ElMessage.success(`WebSocket 已切换到 ${switchData.to.toUpperCase()}`)
          }
        }
        break

      default:
        console.debug('Unknown message type:', message.type)
    }
  }

  /**
   * 转换后端 Ticker 数据为前端格式
   */
  function transformTicker(data: WSTickerData): Ticker {
    const last = parseFloat(data.last) || 0
    const open24h = parseFloat(data.open_24h || '0') || last
    const change_24h = last - open24h
    const change_percent_24h = open24h > 0 ? (change_24h / open24h) * 100 : 0

    // Get current exchange from market store
    const marketStore = useMarketStore()

    return {
      exchange: marketStore.currentExchange,
      symbol: data.symbol,
      last_price: last,
      bid_price: parseFloat(data.bid || '0') || 0,
      ask_price: parseFloat(data.ask || '0') || 0,
      high_24h: parseFloat(data.high_24h || '0') || 0,
      low_24h: parseFloat(data.low_24h || '0') || 0,
      volume_24h: parseFloat(data.volume_24h || '0') || 0,
      quote_volume_24h: parseFloat(data.volume_quote_24h || '0') || 0,
      change_24h,
      change_percent_24h,
      timestamp: new Date(data.timestamp).getTime(),
    }
  }

  /**
   * 转换后端 Candle 数据为前端格式
   */
  function transformCandle(data: WSCandleData): CandleUpdate {
    return {
      symbol: data.symbol,
      timeframe: data.timeframe,
      timestamp: new Date(data.timestamp).getTime(),
      open: parseFloat(data.open) || 0,
      high: parseFloat(data.high) || 0,
      low: parseFloat(data.low) || 0,
      close: parseFloat(data.close) || 0,
      volume: parseFloat(data.volume) || 0,
      is_closed: data.is_closed,
    }
  }

  /**
   * 注册 K 线更新回调
   * @param channel K线频道 (candle:symbol:timeframe)
   * @param callback 回调函数
   */
  function onCandle(channel: string, callback: CandleCallback): void {
    if (!candleCallbacks.has(channel)) {
      candleCallbacks.set(channel, new Set())
    }
    candleCallbacks.get(channel)!.add(callback)
  }

  /**
   * 移除 K 线更新回调
   * @param channel K线频道
   * @param callback 回调函数
   */
  function offCandle(channel: string, callback: CandleCallback): void {
    const callbacks = candleCallbacks.get(channel)
    if (callbacks) {
      callbacks.delete(callback)
      if (callbacks.size === 0) {
        candleCallbacks.delete(channel)
      }
    }
  }

  /**
   * 订阅多个 ticker
   * @returns 取消订阅函数
   */
  function subscribeToTickers(symbols: string[]): () => void {
    const channels = symbols.map((symbol) => `ticker:${symbol}`)
    channels.forEach((channel) => subscribe(channel))

    return () => {
      channels.forEach((channel) => unsubscribe(channel))
    }
  }

  /**
   * 订阅 K 线数据
   * @returns 取消订阅函数
   */
  function subscribeToCandles(symbol: string, timeframe: string): () => void {
    const channel = `candle:${symbol}:${timeframe}`
    subscribe(channel)

    return () => {
      unsubscribe(channel)
    }
  }

  return {
    // State
    connected,
    reconnectAttempts,
    subscribedChannels,
    serviceUnavailable,
    serviceUnavailableMessage,
    exchangeSwitching,
    switchingFromExchange,
    switchingToExchange,
    // Getters
    isConnected,
    // Actions
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    subscribeToTickers,
    subscribeToCandles,
    onCandle,
    offCandle,
  }
})

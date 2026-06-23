import { logger } from '@/shared/lib/logger'

export type WSEventHandler = (payload: unknown) => void

const BACKOFF_MS = [1_000, 2_000, 5_000, 15_000] as const
const MAX_BACKOFF_MS = 30_000
const HEARTBEAT_MS = 20_000

export interface WSClientOptions {
  /** When false, caller must reconnect manually (e.g. refresh ws-ticket). Default true. */
  autoReconnect?: boolean
}

export class WSClient {
  private socket: WebSocket | null = null
  private handlers = new Map<string, Set<WSEventHandler>>()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private reconnectAttempt = 0
  private intentionalClose = false
  private url: string

  constructor(
    url: string,
    private readonly options: WSClientOptions = {},
  ) {
    this.url = url
  }

  /** Replace endpoint before the next connect (used after ws-ticket refresh). */
  setUrl(url: string): void {
    this.url = url
  }

  getUrl(): string {
    return this.url
  }

  isOpen(): boolean {
    return this.socket?.readyState === WebSocket.OPEN
  }

  isConnecting(): boolean {
    return this.socket?.readyState === WebSocket.CONNECTING
  }

  waitUntilOpen(timeoutMs = 15_000): Promise<void> {
    if (this.isOpen()) return Promise.resolve()

    const socket = this.socket
    if (!socket) {
      return Promise.reject(new Error('ws_not_connected'))
    }

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup()
        reject(new Error('ws_open_timeout'))
      }, timeoutMs)

      const onOpen = (): void => {
        cleanup()
        resolve()
      }

      const onClose = (): void => {
        cleanup()
        reject(new Error('ws_closed_before_open'))
      }

      const cleanup = (): void => {
        clearTimeout(timer)
        socket.removeEventListener('open', onOpen)
        socket.removeEventListener('close', onClose)
      }

      socket.addEventListener('open', onOpen)
      socket.addEventListener('close', onClose)
    })
  }

  connect(): void {
    this.intentionalClose = false
    this.openSocket()
  }

  disconnect(): void {
    this.intentionalClose = true
    this.clearReconnect()
    this.clearHeartbeat()
    this.socket?.close()
    this.socket = null
  }

  on(event: string, handler: WSEventHandler): void {
    const set = this.handlers.get(event) ?? new Set()
    set.add(handler)
    this.handlers.set(event, set)
  }

  off(event: string, handler: WSEventHandler): void {
    this.handlers.get(event)?.delete(handler)
  }

  sendJson(data: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data))
    }
  }

  /** Visible for tests */
  getReconnectAttempt(): number {
    return this.reconnectAttempt
  }

  private openSocket(): void {
    if (this.socket?.readyState === WebSocket.OPEN) return

    this.socket = new WebSocket(this.url)

    this.socket.addEventListener('open', () => {
      this.reconnectAttempt = 0
      this.clearReconnect()
      this.startHeartbeat()
      this.emit('open', null)
    })

    this.socket.addEventListener('message', (event) => {
      let payload: unknown = event.data
      try {
        payload = JSON.parse(String(event.data))
      } catch {
        /* raw string payload */
      }
      this.emit('message', payload)
    })

    this.socket.addEventListener('close', () => {
      this.clearHeartbeat()
      this.emit('close', null)
      if (!this.intentionalClose && this.options.autoReconnect !== false) {
        this.scheduleReconnect()
      }
    })

    this.socket.addEventListener('error', () => {
      this.emit('error', null)
    })
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return
    const delay = this.nextBackoffMs()
    this.reconnectAttempt += 1
    logger.debug('WS reconnect scheduled', { delay, attempt: this.reconnectAttempt })
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.openSocket()
    }, delay)
  }

  private nextBackoffMs(): number {
    if (this.reconnectAttempt < BACKOFF_MS.length) {
      return BACKOFF_MS[this.reconnectAttempt]
    }
    return MAX_BACKOFF_MS
  }

  private startHeartbeat(): void {
    this.clearHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: 'ping' }))
      }
    }, HEARTBEAT_MS)
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private emit(event: string, payload: unknown): void {
    this.handlers.get(event)?.forEach((handler) => handler(payload))
  }
}

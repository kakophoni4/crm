import { fetchWsTicket } from '@/features/auth/api'
import { AppError } from '@/shared/api/http'
import { WSClient, type WSEventHandler } from '@/shared/api/ws'
import { env } from '@/shared/config/env'
import { logger } from '@/shared/lib/logger'

export type RealtimeTopicHandler = (payload: Record<string, unknown>) => void

function wsBaseUrl(): string {
  const raw = env.VITE_WS_URL || 'ws://localhost:8000/api/v1/ws'
  return raw.split('?')[0] ?? raw
}

async function buildTicketUrl(): Promise<string> {
  const { ticket } = await fetchWsTicket()
  return `${wsBaseUrl()}?ticket=${encodeURIComponent(ticket)}`
}

function parseFrame(raw: unknown): { type: string; payload: Record<string, unknown> } | null {
  if (!raw || typeof raw !== 'object') return null
  const frame = raw as { type?: string; topic?: string; payload?: Record<string, unknown> }
  const type = frame.type ?? frame.topic
  if (!type || typeof type !== 'string') return null
  return { type, payload: frame.payload ?? {} }
}

class RealtimeWSManager {
  private client: WSClient | null = null
  private topicHandlers = new Map<string, Set<RealtimeTopicHandler>>()
  private rawHandlers = new Set<WSEventHandler>()
  private connecting: Promise<void> | null = null
  private intentionalClose = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempt = 0

  async connect(): Promise<void> {
    this.intentionalClose = false
    if (this.client?.isOpen()) return
    if (this.connecting) return this.connecting

    this.connecting = this.openFresh()
    try {
      await this.connecting
    } finally {
      this.connecting = null
    }
  }

  disconnect(): void {
    this.intentionalClose = true
    this.clearReconnect()
    this.client?.disconnect()
    this.client = null
  }

  onTopic(topic: string, handler: RealtimeTopicHandler): () => void {
    const set = this.topicHandlers.get(topic) ?? new Set()
    set.add(handler)
    this.topicHandlers.set(topic, set)
    return () => this.topicHandlers.get(topic)?.delete(handler)
  }

  onRaw(handler: WSEventHandler): () => void {
    this.rawHandlers.add(handler)
    return () => this.rawHandlers.delete(handler)
  }

  /** Visible for tests */
  getClient(): WSClient | null {
    return this.client
  }

  getReconnectAttempt(): number {
    return this.reconnectAttempt
  }

  private async openFresh(): Promise<void> {
    this.clearReconnect()
    try {
      const url = await buildTicketUrl()
      if (this.client?.isOpen()) {
        return
      }
      if (this.client) {
        this.client.disconnect()
        this.client = null
      }
      const client = new WSClient(url, { autoReconnect: false })
      this.client = client
      client.on('message', (payload) => this.handleMessage(payload))
      client.on('close', () => {
        if (!this.intentionalClose) {
          this.scheduleReconnect()
        }
      })
      client.connect()
      await client.waitUntilOpen()
      this.reconnectAttempt = 0
    } catch (err) {
      logger.warn('WS connect failed', err)
      if (err instanceof AppError && (err.status === 401 || err.status === 403)) {
        return
      }
      if (!this.intentionalClose) {
        this.scheduleReconnect()
      }
    }
  }

  private handleMessage(raw: unknown): void {
    this.rawHandlers.forEach((handler) => handler(raw))

    const frame = parseFrame(raw)
    if (!frame) return

    if (frame.type === 'ping') {
      this.client?.sendJson({ type: 'pong' })
      return
    }

    this.topicHandlers.get(frame.type)?.forEach((handler) => handler(frame.payload))
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer || this.intentionalClose) return
    const delays = [1_000, 2_000, 5_000, 15_000]
    const delay = delays[Math.min(this.reconnectAttempt, delays.length - 1)] ?? 30_000
    const capped = Math.min(delay, 30_000)
    this.reconnectAttempt += 1
    logger.debug('Realtime WS reconnect', { delay: capped, attempt: this.reconnectAttempt })
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      void this.openFresh()
    }, capped)
  }

  private clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }
}

let manager: RealtimeWSManager | null = null

export function getRealtimeWS(): RealtimeWSManager {
  if (!manager) {
    manager = new RealtimeWSManager()
  }
  return manager
}

export async function connectRealtime(): Promise<void> {
  await getRealtimeWS().connect()
}

export function disconnectRealtime(): void {
  manager?.disconnect()
  manager = null
}

/** Test helper */
export function resetRealtimeForTests(): void {
  disconnectRealtime()
}

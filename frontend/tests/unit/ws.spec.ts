import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WSClient } from '@/shared/api/ws'

type WsListener = (event?: { data?: string }) => void

class MockWebSocket {
  static OPEN = 1
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.OPEN
  private listeners: Record<string, WsListener[]> = {}

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send = vi.fn()

  addEventListener(event: string, fn: WsListener): void {
    ;(this.listeners[event] ??= []).push(fn)
  }

  close(): void {
    this.readyState = 3
    this.dispatch('close')
  }

  simulateOpen(): void {
    this.readyState = MockWebSocket.OPEN
    this.dispatch('open')
  }

  dispatch(event: 'open' | 'close' | 'message' | 'error', payload?: { data?: string }): void {
    this.listeners[event]?.forEach((fn) => fn(payload))
  }
}

describe('WSClient', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('reconnects with exponential backoff capped at 30s', () => {
    const client = new WSClient('ws://localhost:8000/ws')
    client.connect()

    const expectDelay = (ms: number) => {
      const before = MockWebSocket.instances.length
      MockWebSocket.instances.at(-1)?.close()
      vi.advanceTimersByTime(ms - 1)
      expect(MockWebSocket.instances.length).toBe(before)
      vi.advanceTimersByTime(1)
      expect(MockWebSocket.instances.length).toBe(before + 1)
    }

    expectDelay(1000)
    expect(client.getReconnectAttempt()).toBe(1)

    expectDelay(2000)
    expect(client.getReconnectAttempt()).toBe(2)

    expectDelay(5000)
    expect(client.getReconnectAttempt()).toBe(3)

    expectDelay(15_000)
    expect(client.getReconnectAttempt()).toBe(4)

    expectDelay(30_000)
    expect(client.getReconnectAttempt()).toBe(5)

    client.disconnect()
  })

  it('sends heartbeat ping every 20 seconds when connected', () => {
    const client = new WSClient('ws://localhost:8000/ws')
    client.connect()
    MockWebSocket.instances[0].simulateOpen()

    vi.advanceTimersByTime(20_000)
    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'ping' }),
    )

    client.disconnect()
  })

  it('supports on/off event handlers', () => {
    const client = new WSClient('ws://localhost:8000/ws')
    const handler = vi.fn()
    client.on('message', handler)
    client.connect()
    MockWebSocket.instances[0].dispatch('message', { data: '{"ok":true}' })
    expect(handler).toHaveBeenCalled()
    client.off('message', handler)
    MockWebSocket.instances[0].dispatch('message', { data: '{"ok":false}' })
    expect(handler).toHaveBeenCalledTimes(1)
    client.disconnect()
  })
})

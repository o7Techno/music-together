// WebSocket комнаты с переподключением (SPEC §5.7): экспоненциальная задержка с джиттером до 10 с,
// после подключения сервер присылает полный снапшот. Коды 4401/4403/4404 — окончательные.

import type { ClientMessage, ServerMessage } from './protocol/generated'

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

export const CLOSE_UNAUTHORIZED = 4401
export const CLOSE_FORBIDDEN = 4403
export const CLOSE_NOT_FOUND = 4404
const TERMINAL_CODES = new Set([CLOSE_UNAUTHORIZED, CLOSE_FORBIDDEN, CLOSE_NOT_FOUND])
/** «Переподключитесь»: сервер перезапускается (1012 — от uvicorn, 4012 — наш). */
const RESTART_CODES = new Set([1012, 4012])

const BASE_DELAY_MS = 500
const MAX_DELAY_MS = 10_000

/** Задержка перед попыткой `attempt` (0, 1, 2…): full jitter поверх экспоненты. */
export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const cap = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt)
  return Math.round(cap / 2 + (random() * cap) / 2)
}

export interface RoomSocketHandlers {
  onOpen(): void
  onMessage(msg: ServerMessage): void
  onStatus(status: SocketStatus): void
  onTerminal(code: number): void
}

export interface SocketEnv {
  createSocket(url: string): WebSocket
  setTimeout(cb: () => void, ms: number): number
  clearTimeout(handle: number): void
  random(): number
}

const browserEnv: SocketEnv = {
  createSocket: (url) => new WebSocket(url),
  setTimeout: (cb, ms) => window.setTimeout(cb, ms),
  clearTimeout: (h) => {
    window.clearTimeout(h)
  },
  random: Math.random,
}

export function roomSocketUrl(slug: string, loc: Location = window.location): string {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${loc.host}/ws/rooms/${encodeURIComponent(slug)}`
}

export class RoomSocket {
  private ws: WebSocket | null = null
  private attempt = 0
  private retryTimer: number | null = null
  private stopped = false
  status: SocketStatus = 'connecting'

  constructor(
    private readonly url: string,
    private readonly handlers: RoomSocketHandlers,
    private readonly env: SocketEnv = browserEnv,
  ) {}

  connect(): void {
    this.stopped = false
    this.open()
  }

  private setStatus(status: SocketStatus): void {
    this.status = status
    this.handlers.onStatus(status)
  }

  private open(): void {
    if (this.stopped) return
    this.setStatus(this.attempt === 0 ? 'connecting' : 'reconnecting')
    const ws = this.env.createSocket(this.url)
    this.ws = ws
    ws.onopen = () => {
      this.handlers.onOpen()
    }
    ws.onmessage = (event: MessageEvent<string>) => {
      let msg: ServerMessage
      try {
        msg = JSON.parse(event.data) as ServerMessage
      } catch {
        return
      }
      if (msg.type === 'snapshot') {
        this.attempt = 0
        this.setStatus('open')
      }
      this.handlers.onMessage(msg)
    }
    ws.onclose = (event: CloseEvent) => {
      if (this.ws !== ws) return
      this.ws = null
      if (this.stopped) {
        this.setStatus('closed')
        return
      }
      if (TERMINAL_CODES.has(event.code)) {
        this.stopped = true
        this.setStatus('closed')
        this.handlers.onTerminal(event.code)
        return
      }
      const delay = RESTART_CODES.has(event.code)
        ? 300 + this.env.random() * 700
        : backoffDelay(this.attempt, () => this.env.random())
      this.attempt += 1
      this.setStatus('reconnecting')
      this.retryTimer = this.env.setTimeout(() => {
        this.retryTimer = null
        this.open()
      }, delay)
    }
  }

  /** Сеть вернулась (событие `online`): не ждём таймер, пробуем сразу. */
  reconnectNow(): void {
    if (this.stopped || this.ws) return
    if (this.retryTimer !== null) this.env.clearTimeout(this.retryTimer)
    this.retryTimer = null
    this.open()
  }

  /** Принудительно разорвать (например, вкладка заметила, что связь мертва). */
  drop(): void {
    this.ws?.close()
  }

  send(msg: ClientMessage): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify(msg))
    return true
  }

  close(): void {
    this.stopped = true
    if (this.retryTimer !== null) this.env.clearTimeout(this.retryTimer)
    this.ws?.close(1000)
    this.ws = null
    this.setStatus('closed')
  }
}

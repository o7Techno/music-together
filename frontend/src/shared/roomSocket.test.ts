import { CLOSE_FORBIDDEN, RoomSocket, type SocketEnv, backoffDelay } from './roomSocket'

class FakeWs {
  static OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  send(data: string): void {
    this.sent.push(data)
  }
  close(): void {
    this.readyState = 3
  }
  open(): void {
    this.readyState = 1
    this.onopen?.()
    this.onmessage?.({ data: JSON.stringify({ type: 'snapshot' }) })
  }
}

function env() {
  const sockets: FakeWs[] = []
  const timers: { cb: () => void; ms: number }[] = []
  const e: SocketEnv = {
    createSocket: () => {
      const ws = new FakeWs()
      sockets.push(ws)
      return ws as unknown as WebSocket
    },
    setTimeout: (cb, ms) => timers.push({ cb, ms }),
    clearTimeout: () => undefined,
    random: () => 0.5,
  }
  return { e, sockets, timers }
}

const noop = {
  onOpen: () => undefined,
  onMessage: () => undefined,
  onStatus: () => undefined,
  onTerminal: () => undefined,
}

describe('backoffDelay', () => {
  it('grows exponentially with jitter and caps at 10 s', () => {
    expect(backoffDelay(0, () => 0)).toBe(250)
    expect(backoffDelay(0, () => 1)).toBe(500)
    expect(backoffDelay(3, () => 1)).toBe(4000)
    expect(backoffDelay(20, () => 1)).toBe(10_000)
    expect(backoffDelay(20, () => 0)).toBe(5000)
  })
})

describe('RoomSocket', () => {
  beforeAll(() => {
    vi.stubGlobal('WebSocket', FakeWs)
  })

  it('reconnects with growing delays and resets after a snapshot', () => {
    const { e, sockets, timers } = env()
    const s = new RoomSocket('ws://x', noop, e)
    s.connect()
    sockets[0]!.onclose?.({ code: 1006 })
    sockets.length = 1
    timers[0]!.cb()
    sockets[1]!.onclose?.({ code: 1006 })
    expect(timers[1]!.ms).toBeGreaterThan(timers[0]!.ms)
    timers[1]!.cb()
    sockets[2]!.open()
    expect(s.status).toBe('open')
    sockets[2]!.onclose?.({ code: 1006 })
    expect(timers[2]!.ms).toBe(timers[0]!.ms)
  })

  it('stops on terminal close codes', () => {
    const { e, sockets, timers } = env()
    const onTerminal = vi.fn()
    const s = new RoomSocket('ws://x', { ...noop, onTerminal }, e)
    s.connect()
    sockets[0]!.onclose?.({ code: CLOSE_FORBIDDEN })
    expect(onTerminal).toHaveBeenCalledWith(CLOSE_FORBIDDEN)
    expect(timers).toHaveLength(0)
    expect(s.status).toBe('closed')
  })

  it('reconnects quickly on server restart (1012)', () => {
    const { e, sockets, timers } = env()
    const s = new RoomSocket('ws://x', noop, e)
    s.connect()
    sockets[0]!.open()
    sockets[0]!.onclose?.({ code: 1012 })
    expect(timers[0]!.ms).toBeLessThan(1000)
    expect(s.status).toBe('reconnecting')
  })

  it('sends only when open', () => {
    const { e, sockets } = env()
    const s = new RoomSocket('ws://x', noop, e)
    s.connect()
    expect(s.send({ type: 'ping', t0: 1 })).toBe(false)
    sockets[0]!.open()
    expect(s.send({ type: 'ping', t0: 1 })).toBe(true)
    expect(sockets[0]!.sent).toHaveLength(1)
  })
})

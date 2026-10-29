// Детерминированные дублёры для unit-тестов движка: ручное время, планировщик, симулятор <audio>.

import type { AudioDeck, Clock, DeckEvent, Scheduler, StreamResolver, TimerHandle } from './types'

export class FakeClock implements Clock {
  t: number
  constructor(t = 1_000_000) {
    this.t = t
  }
  now(): number {
    return this.t
  }
}

interface FakeTimer {
  id: number
  at: number
  cb: () => void
  every: number | null
}

export class FakeScheduler implements Scheduler {
  private timers: FakeTimer[] = []
  private seq = 1
  private readonly clock: FakeClock

  constructor(clock: FakeClock) {
    this.clock = clock
  }

  setTimeout(cb: () => void, ms: number): TimerHandle {
    const id = this.seq++
    this.timers.push({ id, at: this.clock.t + Math.max(0, ms), cb, every: null })
    return id
  }

  clearTimeout(handle: TimerHandle): void {
    this.timers = this.timers.filter((t) => t.id !== handle)
  }

  setInterval(cb: () => void, ms: number): TimerHandle {
    const id = this.seq++
    this.timers.push({ id, at: this.clock.t + ms, cb, every: ms })
    return id
  }

  clearInterval(handle: TimerHandle): void {
    this.clearTimeout(handle)
  }

  spinUntil(localMs: number): void {
    if (localMs > this.clock.t) this.clock.t = localMs
  }

  /** Продвинуть время, выполняя таймеры по порядку; между ними даём отработать промисам. */
  async advance(ms: number): Promise<void> {
    const target = this.clock.t + ms
    for (;;) {
      await flush()
      const due = this.timers.filter((t) => t.at <= target).sort((a, b) => a.at - b.at || a.id - b.id)
      const next = due[0]
      if (!next) break
      if (next.at > this.clock.t) this.clock.t = next.at
      if (next.every !== null) next.at += next.every
      else this.timers = this.timers.filter((t) => t.id !== next.id)
      next.cb()
    }
    this.clock.t = Math.max(this.clock.t, target)
    await flush()
  }
}

export async function flush(): Promise<void> {
  for (let i = 0; i < 10; i++) await Promise.resolve()
}

export interface FakeDeckOptions {
  /** Сколько длится загрузка до canplaythrough. */
  loadMs?: number
  /** Задержка между play() и реальным началом звука. */
  startLatencyMs?: number
  /** Сколько длится seek. */
  seekMs?: number
  /** Относительный уход часов звуковой карты: 0.001 = +1 мс на секунду. */
  skew?: number
  durationMs?: number
}

/** Симулятор HTMLAudioElement поверх FakeClock. */
export class FakeDeck implements AudioDeck {
  src: string | null = null
  paused = true
  seeking = false
  readyState = 0
  volume = 1
  muted = false
  loads: string[] = []
  playCalls: number[] = []
  seekCalls: number[] = []
  failNextPlay = false

  private pos = 0
  private baseAt = 0
  private soundingFrom = 0
  private rate = 1
  private handlers = new Map<DeckEvent, Set<() => void>>()
  private loadedAt = Infinity

  readonly id: string
  opts: FakeDeckOptions
  private readonly clock: FakeClock
  private readonly scheduler: FakeScheduler

  constructor(id: string, clock: FakeClock, scheduler: FakeScheduler, opts: FakeDeckOptions = {}) {
    this.id = id
    this.clock = clock
    this.scheduler = scheduler
    this.opts = opts
  }

  private get o(): Required<FakeDeckOptions> {
    return {
      loadMs: 200,
      startLatencyMs: 20,
      seekMs: 40,
      skew: 0,
      durationMs: 180_000,
      ...this.opts,
    }
  }

  on(event: DeckEvent, cb: () => void): () => void {
    let set = this.handlers.get(event)
    if (!set) {
      set = new Set()
      this.handlers.set(event, set)
    }
    set.add(cb)
    return () => set.delete(cb)
  }

  emit(event: DeckEvent): void {
    for (const cb of [...(this.handlers.get(event) ?? [])]) cb()
  }

  load(src: string): void {
    this.commit()
    this.src = src
    this.loads.push(src)
    this.pos = 0
    this.paused = true
    this.readyState = 0
    this.loadedAt = this.clock.t + this.o.loadMs
    this.scheduler.setTimeout(() => {
      if (this.src !== src) return
      this.readyState = 4
      this.emit('canplay')
      this.emit('canplaythrough')
    }, this.o.loadMs)
  }

  unload(): void {
    this.src = null
    this.readyState = 0
  }

  /** Зафиксировать накопленную позицию (перед сменой темпа/паузой/seek). */
  private commit(): void {
    this.pos = this.currentTimeMs
    this.baseAt = this.clock.t
    this.soundingFrom = Math.max(this.soundingFrom, this.clock.t)
  }

  get currentTimeMs(): number {
    if (this.paused || this.seeking) return this.pos
    const from = Math.max(this.baseAt, this.soundingFrom)
    const elapsed = Math.max(0, this.clock.t - from)
    return Math.min(this.o.durationMs, this.pos + elapsed * this.rate * (1 + this.o.skew))
  }

  seek(ms: number): void {
    this.commit()
    this.seekCalls.push(ms)
    this.pos = ms
    this.seeking = true
    this.scheduler.setTimeout(() => {
      this.baseAt = this.clock.t
      this.seeking = false
      this.emit('seeked')
    }, this.o.seekMs)
  }

  play(): Promise<void> {
    if (this.failNextPlay) {
      this.failNextPlay = false
      return Promise.reject(new Error('NotAllowedError'))
    }
    this.playCalls.push(this.clock.t)
    if (!this.paused) return Promise.resolve()
    this.commit()
    this.paused = false
    this.soundingFrom = this.clock.t + this.o.startLatencyMs
    this.baseAt = this.clock.t
    this.scheduler.setTimeout(() => {
      this.emit('playing')
    }, this.o.startLatencyMs)
    return Promise.resolve()
  }

  pause(): void {
    if (this.paused) return
    this.commit()
    this.paused = true
  }

  get playbackRate(): number {
    return this.rate
  }

  set playbackRate(value: number) {
    this.commit()
    this.rate = value
  }

  bufferedAheadMs(fromMs: number): number {
    if (this.clock.t < this.loadedAt) return 0
    return Math.max(0, this.o.durationMs - fromMs)
  }

  unlock(): Promise<void> {
    return Promise.resolve()
  }
}

export class FakeResolver implements StreamResolver {
  calls: string[] = []
  unavailable = new Set<string>()
  mirrors: string[] = []

  resolve(trackId: string): Promise<{ url: string; mirrors: string[] }> {
    this.calls.push(trackId)
    if (this.unavailable.has(trackId)) {
      return import('./types').then(({ TrackUnavailable }) => {
        throw new TrackUnavailable()
      })
    }
    return Promise.resolve({
      url: `https://audio.test/${trackId}.mp3?n=${this.calls.length}`,
      mirrors: this.mirrors.map((m) => `${m}/${trackId}.mp3`),
    })
  }
}

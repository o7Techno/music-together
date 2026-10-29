// Браузерные реализации абстракций движка: часы, планировщик, аудиодек над <audio>,
// оценка задержки вывода звука.

import type { AudioDeck, Clock, DeckEvent, Scheduler, TimerHandle } from './types'

export const browserClock: Clock = {
  now: () => performance.timeOrigin + performance.now(),
}

const MAX_SPIN_MS = 25

export class BrowserScheduler implements Scheduler {
  constructor(private readonly clock: Clock = browserClock) {}

  setTimeout(cb: () => void, ms: number): TimerHandle {
    return window.setTimeout(cb, ms)
  }

  clearTimeout(handle: TimerHandle): void {
    window.clearTimeout(handle)
  }

  setInterval(cb: () => void, ms: number): TimerHandle {
    return window.setInterval(cb, ms)
  }

  clearInterval(handle: TimerHandle): void {
    window.clearInterval(handle)
  }

  spinUntil(localMs: number): void {
    // Короткий активный цикл: таймеры браузера дают ошибку в единицы-десятки мс,
    // последние миллисекунды до старта добираем точно.
    const limit = this.clock.now() + MAX_SPIN_MS
    while (this.clock.now() < localMs && this.clock.now() < limit) {
      /* ожидание */
    }
  }
}

/** Крошечный беззвучный WAV — для разблокировки автовоспроизведения жестом пользователя. */
function silentWavUrl(): string {
  const samples = 800
  const buffer = new ArrayBuffer(44 + samples)
  const v = new DataView(buffer)
  const ascii = (offset: number, s: string): void => {
    for (let i = 0; i < s.length; i++) v.setUint8(offset + i, s.charCodeAt(i))
  }
  ascii(0, 'RIFF')
  v.setUint32(4, 36 + samples, true)
  ascii(8, 'WAVE')
  ascii(12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true) // PCM
  v.setUint16(22, 1, true) // моно
  v.setUint32(24, 8000, true)
  v.setUint32(28, 8000, true)
  v.setUint16(32, 1, true)
  v.setUint16(34, 8, true)
  ascii(36, 'data')
  v.setUint32(40, samples, true)
  for (let i = 0; i < samples; i++) v.setUint8(44 + i, 128)
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
}

let silentUrl: string | null = null

type PitchElement = HTMLAudioElement & {
  mozPreservesPitch?: boolean
  webkitPreservesPitch?: boolean
}

export class HtmlAudioDeck implements AudioDeck {
  readonly el: HTMLAudioElement
  private currentSrc: string | null = null

  constructor(readonly id: string) {
    const el = new Audio() as PitchElement
    el.preload = 'auto'
    // Без crossOrigin: ссылки Яндекса не играют в CORS-режиме (DECISIONS D-009).
    el.preservesPitch = true
    el.mozPreservesPitch = true
    el.webkitPreservesPitch = true
    this.el = el
  }

  get src(): string | null {
    return this.currentSrc
  }

  load(src: string): void {
    this.currentSrc = src
    this.el.src = src
    this.el.load()
  }

  unload(): void {
    this.currentSrc = null
    this.el.removeAttribute('src')
    this.el.load()
  }

  get currentTimeMs(): number {
    return this.el.currentTime * 1000
  }

  seek(ms: number): void {
    this.el.currentTime = Math.max(0, ms / 1000)
  }

  get seeking(): boolean {
    return this.el.seeking
  }

  play(): Promise<void> {
    return this.el.play()
  }

  pause(): void {
    this.el.pause()
  }

  get paused(): boolean {
    return this.el.paused
  }

  get playbackRate(): number {
    return this.el.playbackRate
  }

  set playbackRate(rate: number) {
    this.el.playbackRate = rate
  }

  bufferedAheadMs(fromMs: number): number {
    const t = fromMs / 1000
    const ranges = this.el.buffered
    for (let i = 0; i < ranges.length; i++) {
      if (ranges.start(i) <= t + 0.05 && t <= ranges.end(i)) return (ranges.end(i) - t) * 1000
    }
    return 0
  }

  get readyState(): number {
    return this.el.readyState
  }

  get volume(): number {
    return this.el.volume
  }

  set volume(v: number) {
    this.el.volume = v
  }

  get muted(): boolean {
    return this.el.muted
  }

  set muted(m: boolean) {
    this.el.muted = m
  }

  on(event: DeckEvent, cb: () => void): () => void {
    this.el.addEventListener(event, cb)
    return () => {
      this.el.removeEventListener(event, cb)
    }
  }

  async unlock(): Promise<void> {
    // iOS разблокирует конкретный элемент: проигрываем тишину на нём самом, затем возвращаем трек.
    const el = this.el
    const restoreSrc = this.currentSrc
    const restoreTime = el.currentTime
    const wasMuted = el.muted
    el.muted = true
    if (!restoreSrc) {
      silentUrl ??= silentWavUrl()
      el.src = silentUrl
    }
    try {
      await el.play()
    } catch {
      // Если браузер всё равно отказал — движок узнает об этом при первом play().
    }
    el.pause()
    el.muted = wasMuted
    if (restoreSrc) el.currentTime = restoreTime
    else el.removeAttribute('src')
  }
}

/** Задержка вывода звука из AudioContext (Chrome/Firefox: outputLatency, Safari: baseLatency). */
export class LatencyProbe {
  private ctx: AudioContext | null = null

  /** Вызывать из жеста пользователя. */
  resume(): void {
    try {
      this.ctx ??= new AudioContext()
      void this.ctx.resume()
    } catch {
      this.ctx = null
    }
  }

  outputLatencyMs(): number | null {
    const ctx = this.ctx
    if (!ctx) return null
    const output = 'outputLatency' in ctx ? ctx.outputLatency : undefined
    const seconds = typeof output === 'number' && output > 0 ? output : ctx.baseLatency
    return Number.isFinite(seconds) ? Math.round(seconds * 1000 * 10) / 10 : null
  }
}

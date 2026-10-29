// Синхронизация часов с сервером (SPEC §5.3).
//
// Для каждого пинга: RTT = t1 − t0, offset = serverTime − (t0 + RTT/2). Оценка — медиана offset
// по 3 замерам с наименьшим RTT в скользящем окне. Новая оценка применяется сглаженно, чтобы
// не прыгать на выбросах; большой скачок (смена системного времени) применяется сразу.

export interface ClockSample {
  rttMs: number
  offsetMs: number
  atMs: number
}

export interface ClockSyncOptions {
  windowSize: number
  bestCount: number
  smoothing: number
  jumpThresholdMs: number
}

const DEFAULTS: ClockSyncOptions = {
  windowSize: 24,
  bestCount: 3,
  smoothing: 0.3,
  jumpThresholdMs: 250,
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) return sorted[mid] ?? 0
  return ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2
}

export class ClockSync {
  private readonly opts: ClockSyncOptions
  private samples: ClockSample[] = []
  private offset: number | null = null
  private bestRtt: number | null = null
  /** Оценка опирается хотя бы на `bestCount` замеров — с этого момента только сглаживаем. */
  private trusted = false

  constructor(opts: Partial<ClockSyncOptions> = {}) {
    this.opts = { ...DEFAULTS, ...opts }
  }

  /** Добавить замер: t0/t1 — локальное время отправки/получения, serverTime — время сервера. */
  addSample(t0: number, serverTime: number, t1: number): void {
    const rttMs = t1 - t0
    if (!Number.isFinite(rttMs) || rttMs < 0) return
    const offsetMs = serverTime - (t0 + rttMs / 2)
    this.samples.push({ rttMs, offsetMs, atMs: t1 })
    if (this.samples.length > this.opts.windowSize) this.samples.shift()
    this.update()
  }

  private update(): void {
    const best = [...this.samples].sort((a, b) => a.rttMs - b.rttMs).slice(0, this.opts.bestCount)
    if (best.length === 0) return
    const estimate = median(best.map((s) => s.offsetMs))
    this.bestRtt = best[0]?.rttMs ?? null
    const current = this.offset ?? estimate
    const jump = Math.abs(estimate - current) > this.opts.jumpThresholdMs
    this.offset =
      !this.trusted || jump ? estimate : current + this.opts.smoothing * (estimate - current)
    if (best.length >= this.opts.bestCount) this.trusted = true
  }

  /** Новая серия замеров после переподключения: старые замеры забываем, оценку оставляем как приор. */
  resetWindow(): void {
    this.samples = []
  }

  get calibrated(): boolean {
    return this.offset !== null && this.samples.length >= this.opts.bestCount
  }

  get offsetMs(): number {
    return this.offset ?? 0
  }

  get rttMs(): number | null {
    return this.bestRtt
  }

  get sampleCount(): number {
    return this.samples.length
  }

  serverNow(localNowMs: number): number {
    return localNowMs + this.offsetMs
  }

  toLocal(serverMs: number): number {
    return serverMs - this.offsetMs
  }
}

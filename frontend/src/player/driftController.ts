// Контроллер дрейфа (SPEC §5.5).
//
// drift = фактическая позиция − ожидаемая (положительный — впереди).
// - |drift| < мёртвой зоны — ничего не делаем (с гистерезисом: выходим из коррекции ниже exitZone);
// - до порога жёсткого seek — плавная подстройка playbackRate, пропорционально дрейфу, в пределах ±5 %;
// - от порога — жёсткий seek на ожидаемую позицию с упреждением на выученную задержку seek;
// - seek не чаще раза в minSeekIntervalMs; 3 неудачных seek подряд → «нестабилен».
// Решение принимается только по текущему замеру (сглаженному медианой), поэтому пропуски тиков
// в фоновой вкладке не накапливают ошибку.

export interface DriftProfile {
  name: string
  deadZoneMs: number
  exitZoneMs: number
  /** Максимальное отклонение playbackRate от 1 (0 — подстройка темпом отключена). */
  maxRateDelta: number
  /** Коэффициент: на сколько (доля в секунду) сокращать дрейф. 1 → постоянная времени 1 с. */
  gainPerSecond: number
  hardSeekMs: number
  minSeekIntervalMs: number
  maxSeekFailures: number
}

export const DESKTOP_PROFILE: DriftProfile = {
  name: 'desktop',
  deadZoneMs: 20,
  exitZoneMs: 8,
  maxRateDelta: 0.05,
  gainPerSecond: 1,
  hardSeekMs: 1000,
  minSeekIntervalMs: 2000,
  maxSeekFailures: 3,
}

export type DriftAction =
  { kind: 'none'; rate: 1 } | { kind: 'rate'; rate: number } | { kind: 'seek'; targetMs: number }

const SMOOTHING_WINDOW = 3
const UNSTABLE_SEEK_INTERVAL_MS = 30_000
const SEEK_LATENCY_MIN = 0
const SEEK_LATENCY_MAX = 600

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor(sorted.length / 2)] ?? 0
}

export class DriftController {
  private recent: number[] = []
  private correcting = false
  private lastSeekAt = -Infinity
  private pendingSeekCheck = false
  private seekFailures = 0
  /** Выученная задержка seek: на сколько отстаём сразу после перемотки. */
  seekLatencyMs = 120
  unstable = false
  profile: DriftProfile

  constructor(profile: DriftProfile = DESKTOP_PROFILE) {
    this.profile = profile
  }

  /** Сбросить состояние (новый трек, пауза, ручная перемотка). */
  reset(): void {
    this.recent = []
    this.correcting = false
    this.pendingSeekCheck = false
  }

  get smoothedDriftMs(): number | null {
    return this.recent.length > 0 ? median(this.recent) : null
  }

  get seekFailureCount(): number {
    return this.seekFailures
  }

  update(driftMs: number, expectedMs: number, nowMs: number): DriftAction {
    const p = this.profile
    this.recent.push(driftMs)
    if (this.recent.length > SMOOTHING_WINDOW) this.recent.shift()
    // После seek сглаживание по старым замерам вредно — смотрим на свежий.
    const drift = this.pendingSeekCheck ? driftMs : median(this.recent)
    const abs = Math.abs(drift)

    if (this.pendingSeekCheck) {
      this.pendingSeekCheck = false
      // Учимся: если после seek отстаём на X — в следующий раз прыгаем на X дальше.
      this.seekLatencyMs = Math.min(
        SEEK_LATENCY_MAX,
        Math.max(SEEK_LATENCY_MIN, this.seekLatencyMs - drift * 0.5),
      )
      if (abs >= p.hardSeekMs) {
        this.seekFailures += 1
        if (this.seekFailures >= p.maxSeekFailures) this.unstable = true
      } else {
        this.seekFailures = 0
        this.unstable = false
      }
    }

    if (abs >= p.hardSeekMs) {
      // Seek не помогает — повторяем редко: частая перемотка слышна как непрерывные лаги.
      const interval =
        this.seekFailures > p.maxSeekFailures + 1 ? UNSTABLE_SEEK_INTERVAL_MS : p.minSeekIntervalMs
      if (nowMs - this.lastSeekAt >= interval) {
        this.lastSeekAt = nowMs
        this.pendingSeekCheck = true
        this.recent = []
        this.correcting = false
        return { kind: 'seek', targetMs: Math.max(0, expectedMs + this.seekLatencyMs) }
      }
      // Seek недавно был — пока тянем темпом на максимуме.
      return this.rateFor(drift)
    }

    if (this.correcting ? abs < p.exitZoneMs : abs < p.deadZoneMs) {
      this.correcting = false
      return { kind: 'none', rate: 1 }
    }
    this.correcting = true
    return this.rateFor(drift)
  }

  /** Отметить внешний seek (старт/ручная перемотка), чтобы не считать его неудачной коррекцией. */
  noteSeek(nowMs: number): void {
    this.lastSeekAt = nowMs
    this.recent = []
  }

  private rateFor(driftMs: number): DriftAction {
    const p = this.profile
    if (p.maxRateDelta <= 0) return { kind: 'none', rate: 1 }
    const delta = Math.max(
      -p.maxRateDelta,
      Math.min(p.maxRateDelta, (driftMs / 1000) * p.gainPerSecond),
    )
    // Впереди → замедляемся, отстаём → ускоряемся.
    return { kind: 'rate', rate: 1 - delta }
  }
}

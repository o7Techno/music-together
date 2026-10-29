// Абстракции движка синхронизации. Реальные реализации — над браузерными API,
// тестовые — детерминированные, с ручным временем (см. *.test.ts).

/** Монотонные часы в эпохальных миллисекундах: performance.timeOrigin + performance.now(). */
export interface Clock {
  now(): number
}

export type TimerHandle = number

export interface Scheduler {
  setTimeout(cb: () => void, ms: number): TimerHandle
  clearTimeout(handle: TimerHandle): void
  setInterval(cb: () => void, ms: number): TimerHandle
  clearInterval(handle: TimerHandle): void
  /** Точная доводка до момента `localMs` (короткий цикл ожидания, не дольше ~20 мс). */
  spinUntil(localMs: number): void
}

export type DeckEvent =
  'canplay' | 'canplaythrough' | 'playing' | 'waiting' | 'stalled' | 'seeked' | 'error' | 'ended'

/** Один аудиоэлемент. Движок держит два: текущий и предзагружаемый следующий. */
export interface AudioDeck {
  readonly id: string
  readonly src: string | null
  load(src: string): void
  unload(): void
  /** Позиция воспроизведения, мс. */
  readonly currentTimeMs: number
  seek(ms: number): void
  readonly seeking: boolean
  play(): Promise<void>
  pause(): void
  readonly paused: boolean
  playbackRate: number
  /** Сколько миллисекунд загружено вперёд от `fromMs` (0, если позиция вне буфера). */
  bufferedAheadMs(fromMs: number): number
  readonly readyState: number
  volume: number
  muted: boolean
  on(event: DeckEvent, cb: () => void): () => void
  /** Разблокировка автовоспроизведения — вызывать из обработчика жеста пользователя. */
  unlock(): Promise<void>
}

export interface StreamSource {
  url: string
  mirrors: string[]
}

export interface StreamResolver {
  /** Свежая ссылка на аудио трека для текущего пользователя (его токеном). */
  resolve(trackId: string): Promise<StreamSource>
}

export class TrackUnavailable extends Error {
  constructor(message = 'track unavailable') {
    super(message)
    this.name = 'TrackUnavailable'
  }
}

export interface Logger {
  debug(msg: string, data?: Record<string, unknown>): void
  warn(msg: string, data?: Record<string, unknown>): void
}

export const silentLogger: Logger = {
  debug: () => undefined,
  warn: () => undefined,
}

// Движок синхронизации воспроизведения (SPEC §5). Чистый TypeScript без React и DOM:
// часы, планировщик, аудиоэлементы, транспорт и получение ссылок внедряются.
//
// Клиент никогда не синхронизируется по другим клиентам — только по формуле состояния сервера:
//   playing: positionMs + (serverNow − anchorServerMs);  paused/loading: positionMs.

import type {
  ClientMessage,
  PlaybackState,
  QueueState,
  ServerMessage,
  SyncState,
} from '@/shared/protocol/generated'

import { ClockSync } from './clockSync'
import { DESKTOP_PROFILE, DriftController, type DriftProfile } from './driftController'
import {
  type AudioDeck,
  type Clock,
  type Logger,
  type Scheduler,
  type StreamResolver,
  type TimerHandle,
  TrackUnavailable,
  silentLogger,
} from './types'

export const TICK_MS = 250
export const DRIFT_REPORT_MS = 2000
export const PRELOAD_BEFORE_END_MS = 20_000
export const READY_BUFFER_MS = 3000
export const CALIBRATION_PINGS = 8
export const CALIBRATION_GAP_MS = 60
export const RECALIBRATE_EVERY_MS = 30_000
export const RECALIBRATION_PINGS = 4
export const IN_SYNC_THRESHOLD_MS = 40
/** Позиция на деке считается «уже там», если ближе этого порога — лишний seek не нужен. */
const SEEK_TOLERANCE_MS = 30
const SPIN_WINDOW_MS = 20
const CALIBRATION_WAIT_MS = 1500
const MAX_RELOADS_PER_TRACK = 3

export interface SyncEngineDeps {
  clock: Clock
  scheduler: Scheduler
  decks: readonly [AudioDeck, AudioDeck]
  resolver: StreamResolver
  send: (msg: ClientMessage) => void
  profile?: DriftProfile
  /** Задержка вывода звука (AudioContext.outputLatency), мс; null — неизвестна. */
  outputLatencyMs?: () => number | null
  logger?: Logger
}

export interface DebugInfo {
  offsetMs: number
  rttMs: number | null
  clockSamples: number
  driftMs: number | null
  smoothedDriftMs: number | null
  playbackRate: number
  bufferedAheadMs: number
  version: number
  status: string
  outputLatencyMs: number | null
  latencyCompensation: boolean
  profile: string
  seekLatencyMs: number
  startLatencyMs: number
  seekFailures: number
  unstable: boolean
  sync: SyncState
}

export interface SyncProbe {
  serverNow: number
  expectedMs: number
  actualMs: number | null
  driftMs: number | null
  offsetMs: number
  rttMs: number | null
  version: number
  status: string | null
  trackId: string | null
  queueItemId: string | null
  playing: boolean
  rate: number
}

interface DeckTrack {
  trackId: string
  urls: string[]
  urlIndex: number
}

type Listener = () => void

export function expectedPosition(state: PlaybackState, serverNow: number): number {
  if (state.status !== 'playing') return state.positionMs
  const elapsed = Math.max(0, serverNow - state.anchorServerMs)
  const position = state.positionMs + elapsed
  return state.durationMs > 0 ? Math.min(position, state.durationMs) : position
}

export class SyncEngine {
  readonly clockSync = new ClockSync()
  readonly controller: DriftController

  state: PlaybackState | null = null
  queue: QueueState | null = null
  audioUnlocked = false
  trackUnavailable = false
  sync: SyncState = 'idle'
  buffering = false
  /** Компенсировать задержку вывода звука (по умолчанию выкл., см. DECISIONS D-021). */
  latencyCompensation = false

  private readonly d: Required<Omit<SyncEngineDeps, 'profile'>>
  private active: AudioDeck
  private spare: AudioDeck
  private readonly deckTracks = new Map<string, DeckTrack>()
  private readonly reloads = new Map<string, number>()
  private listeners = new Set<Listener>()
  private tickTimer: TimerHandle | null = null
  private recalibrateTimer: TimerHandle | null = null
  private startTimer: TimerHandle | null = null
  private pingTimers: TimerHandle[] = []
  private started = false
  private lastDriftMs: number | null = null
  private lastReportAt = -Infinity
  private preloading: string | null = null
  private startLatencyMs = 30
  private startLatencyPending = false
  private playStartedAt = 0
  private lastStatusSent = ''
  private calibrationWaiters: (() => void)[] = []
  private readonly deckUnsubs: (() => void)[] = []

  constructor(deps: SyncEngineDeps) {
    this.d = {
      clock: deps.clock,
      scheduler: deps.scheduler,
      decks: deps.decks,
      resolver: deps.resolver,
      send: deps.send,
      outputLatencyMs: deps.outputLatencyMs ?? (() => null),
      logger: deps.logger ?? silentLogger,
    }
    this.controller = new DriftController(deps.profile ?? DESKTOP_PROFILE)
    ;[this.active, this.spare] = deps.decks
    for (const deck of deps.decks) this.watchDeck(deck)
  }

  // ── Жизненный цикл ──────────────────────────────────────────────────────────

  start(): void {
    if (this.tickTimer !== null) return
    this.tickTimer = this.d.scheduler.setInterval(() => {
      this.tick()
    }, TICK_MS)
    this.recalibrateTimer = this.d.scheduler.setInterval(() => {
      this.pingBurst(RECALIBRATION_PINGS)
    }, RECALIBRATE_EVERY_MS)
  }

  stop(): void {
    const s = this.d.scheduler
    if (this.tickTimer !== null) s.clearInterval(this.tickTimer)
    if (this.recalibrateTimer !== null) s.clearInterval(this.recalibrateTimer)
    this.tickTimer = null
    this.recalibrateTimer = null
    this.cancelStart()
    for (const t of this.pingTimers) s.clearTimeout(t)
    for (const unsub of this.deckUnsubs) unsub()
    for (const deck of this.d.decks) deck.pause()
  }

  /** WebSocket (пере)подключён: новая серия замеров часов (SPEC §5.3). */
  onConnected(): void {
    this.clockSync.resetWindow()
    this.lastStatusSent = ''
    this.pingBurst(CALIBRATION_PINGS)
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emit(): void {
    for (const l of this.listeners) l()
  }

  // ── Сообщения сервера ───────────────────────────────────────────────────────

  handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
      case 'pong':
        this.clockSync.addSample(msg.t0, msg.serverTime, this.d.clock.now())
        if (this.clockSync.calibrated) this.flushCalibrationWaiters()
        break
      case 'snapshot':
        if (!this.clockSync.calibrated) {
          // Грубый приор до первых пингов: ошибка ≈ половина RTT.
          this.clockSync.addSample(this.d.clock.now(), msg.serverTime, this.d.clock.now())
          this.clockSync.resetWindow()
        }
        this.queue = msg.queue
        this.applyState(msg.playback, true)
        this.sendStatus(true)
        break
      case 'playback':
        this.applyState(msg.state, false)
        break
      case 'queue':
        if (!this.queue || msg.queue.version >= this.queue.version) this.queue = msg.queue
        break
      default:
        break
    }
  }

  private pingBurst(count: number): void {
    for (let i = 0; i < count; i++) {
      this.pingTimers.push(
        this.d.scheduler.setTimeout(() => {
          this.d.send({ type: 'ping', t0: this.d.clock.now() })
        }, i * CALIBRATION_GAP_MS),
      )
    }
    if (this.pingTimers.length > 64) this.pingTimers = this.pingTimers.slice(-32)
  }

  private whenCalibrated(): Promise<void> {
    if (this.clockSync.calibrated) return Promise.resolve()
    return new Promise((resolve) => {
      this.calibrationWaiters.push(resolve)
      this.d.scheduler.setTimeout(resolve, CALIBRATION_WAIT_MS)
    })
  }

  private flushCalibrationWaiters(): void {
    const waiters = this.calibrationWaiters
    this.calibrationWaiters = []
    for (const w of waiters) w()
  }

  // ── Применение состояния ────────────────────────────────────────────────────

  private isStale(version: number): boolean {
    return this.state?.version !== version
  }

  applyState(state: PlaybackState, force: boolean): void {
    const prev = this.state
    if (!force && prev && state.version <= prev.version) return
    this.state = state
    const trackChanged = prev?.queueItemId !== state.queueItemId
    if (trackChanged) {
      this.trackUnavailable = false
      this.reloads.clear()
    }
    this.cancelStart()
    this.started = false
    this.controller.reset()
    this.lastDriftMs = null
    this.active.playbackRate = 1

    switch (state.status) {
      case 'paused':
        this.active.pause()
        this.spare.pause()
        if (state.trackId) void this.cuePaused(state)
        break
      case 'loading':
        this.active.pause()
        this.spare.pause()
        if (state.trackId) void this.prepareAndReady(state)
        break
      case 'playing':
        this.spare.pause()
        if (state.trackId) void this.startPlaying(state)
        break
    }
    this.updateSync()
    this.emit()
  }

  private async cuePaused(state: PlaybackState): Promise<void> {
    const deck = await this.ensureTrack(state, state.version)
    if (!deck || this.isStale(state.version)) return
    deck.pause()
    this.seekIfFar(deck, state.positionMs)
  }

  private async prepareAndReady(state: PlaybackState): Promise<void> {
    const version = state.version
    const deck = await this.ensureTrack(state, version)
    if (!deck || this.isStale(version)) return
    deck.pause()
    this.seekIfFar(deck, state.positionMs)
    await this.waitBuffered(deck, state.positionMs, version)
    if (this.isStale(version)) return
    if (this.audioUnlocked && !this.trackUnavailable) this.d.send({ type: 'ready', version })
  }

  private async startPlaying(state: PlaybackState): Promise<void> {
    const version = state.version
    const deck = await this.ensureTrack(state, version)
    if (!deck || this.isStale(version) || !this.audioUnlocked) return
    await this.whenCalibrated()
    if (this.isStale(version)) return

    const anchorLocal = this.clockSync.toLocal(state.anchorServerMs)
    const startAt = anchorLocal - this.startLatencyMs
    const now = this.d.clock.now()

    if (startAt > now + 5) {
      // Старт назначен в будущем: заранее встаём на позицию и запускаемся точно в момент якоря.
      this.seekIfFar(deck, state.positionMs)
      const fire = (): void => {
        this.startTimer = null
        if (this.isStale(version)) return
        this.d.scheduler.spinUntil(startAt)
        this.beginPlayback(deck)
      }
      const delay = startAt - now - SPIN_WINDOW_MS
      if (delay > 0) this.startTimer = this.d.scheduler.setTimeout(fire, delay)
      else fire()
      return
    }

    // Опоздали (новый участник, долгая загрузка, вкладка в фоне): прыгаем на вычисленную позицию.
    const lead = this.controller.seekLatencyMs
    const target = expectedPosition(state, this.clockSync.serverNow(now + lead))
    deck.seek(target)
    this.controller.noteSeek(now)
    await this.waitBuffered(deck, target, version, 500)
    if (this.isStale(version)) return
    this.beginPlayback(deck)
  }

  private beginPlayback(deck: AudioDeck): void {
    deck.playbackRate = 1
    this.playStartedAt = this.d.clock.now()
    this.started = true
    this.startLatencyPending = true
    deck.play().catch((err: unknown) => {
      this.d.logger.warn('play() rejected', { err: String(err) })
      this.started = false
      // Только NotAllowedError — это политика автовоспроизведения (нужен жест пользователя).
      // AbortError (прервали новой загрузкой/паузой) и ошибки источника обрабатываются отдельно.
      if (err instanceof Error && err.name === 'NotAllowedError') {
        this.audioUnlocked = false
        this.sendStatus()
        this.emit()
      }
    })
  }

  private cancelStart(): void {
    if (this.startTimer !== null) {
      this.d.scheduler.clearTimeout(this.startTimer)
      this.startTimer = null
    }
  }

  private seekIfFar(deck: AudioDeck, positionMs: number): void {
    if (Math.abs(deck.currentTimeMs - positionMs) > SEEK_TOLERANCE_MS) deck.seek(positionMs)
  }

  /** Ждать достаточной буферизации на позиции (canplaythrough или ≥ 3 с вперёд). */
  private waitBuffered(
    deck: AudioDeck,
    positionMs: number,
    version: number,
    needMs = READY_BUFFER_MS,
  ): Promise<void> {
    return new Promise((resolve) => {
      const check = (): boolean => {
        if (this.isStale(version)) return true
        if (deck.seeking) return false
        const ahead = deck.bufferedAheadMs(positionMs)
        const remaining = (this.state?.durationMs ?? 0) - positionMs
        return ahead >= Math.min(needMs, Math.max(0, remaining - 50)) || deck.readyState >= 4
      }
      if (check()) {
        resolve()
        return
      }
      const unsubs: (() => void)[] = []
      const done = (): void => {
        if (!check()) return
        for (const u of unsubs) u()
        this.d.scheduler.clearInterval(poll)
        resolve()
      }
      unsubs.push(
        deck.on('canplaythrough', done),
        deck.on('seeked', done),
        deck.on('canplay', done),
      )
      const poll = this.d.scheduler.setInterval(done, 100)
    })
  }

  // ── Деки: загрузка, предзагрузка, ошибки ────────────────────────────────────

  private async ensureTrack(state: PlaybackState, version: number): Promise<AudioDeck | null> {
    const trackId = state.trackId
    if (!trackId) return null
    if (this.deckTracks.get(this.active.id)?.trackId === trackId) return this.active
    if (this.deckTracks.get(this.spare.id)?.trackId === trackId) {
      // Следующий трек уже предзагружен — меняем деки местами, барьер проходит почти мгновенно.
      this.active.pause()
      ;[this.active, this.spare] = [this.spare, this.active]
      return this.active
    }
    try {
      const source = await this.d.resolver.resolve(trackId)
      if (this.isStale(version)) return null
      this.active.pause()
      this.loadInto(this.active, trackId, [source.url, ...source.mirrors])
      return this.active
    } catch (err) {
      if (this.isStale(version)) return null
      this.markUnavailable(err)
      return null
    }
  }

  private loadInto(deck: AudioDeck, trackId: string, urls: string[]): void {
    const first = urls[0]
    if (!first) return
    this.deckTracks.set(deck.id, { trackId, urls, urlIndex: 0 })
    deck.load(first)
  }

  private markUnavailable(err: unknown): void {
    this.d.logger.warn('stream unavailable', { err: String(err) })
    if (err instanceof TrackUnavailable) {
      this.trackUnavailable = true
      this.sendStatus()
      this.emit()
    }
  }

  private maybePreload(): void {
    const state = this.state
    const next = this.queue?.upcoming[0]
    if (state?.status !== 'playing' || !next || next.track.id === state.trackId) return
    const remaining = state.durationMs - this.expectedPositionMs()
    if (remaining > PRELOAD_BEFORE_END_MS) return
    const trackId = next.track.id
    if (this.preloading === trackId || this.deckTracks.get(this.spare.id)?.trackId === trackId) {
      return
    }
    this.preloading = trackId
    this.d.resolver
      .resolve(trackId)
      .then((source) => {
        if (this.state?.trackId === trackId) return // уже играет — грузить на запасной поздно
        this.loadInto(this.spare, trackId, [source.url, ...source.mirrors])
      })
      .catch((err: unknown) => {
        this.d.logger.debug('preload failed', { err: String(err) })
      })
      .finally(() => {
        this.preloading = null
      })
  }

  private watchDeck(deck: AudioDeck): void {
    this.deckUnsubs.push(
      deck.on('error', () => {
        this.onDeckError(deck)
      }),
      deck.on('waiting', () => {
        if (deck === this.active) {
          this.buffering = true
          this.updateSync()
        }
      }),
      deck.on('playing', () => {
        if (deck === this.active) {
          this.buffering = false
          this.updateSync()
        }
      }),
    )
  }

  /** Ошибка воспроизведения: следующее зеркало, затем свежая ссылка (подписи протухают). */
  private onDeckError(deck: AudioDeck): void {
    const info = this.deckTracks.get(deck.id)
    if (!info) return
    if (deck !== this.active) {
      this.deckTracks.delete(deck.id)
      return
    }
    const state = this.state
    if (!state || state.trackId !== info.trackId) return
    const next = info.urls[info.urlIndex + 1]
    if (next) {
      info.urlIndex += 1
      deck.load(next)
    } else {
      const attempts = (this.reloads.get(info.trackId) ?? 0) + 1
      this.reloads.set(info.trackId, attempts)
      if (attempts > MAX_RELOADS_PER_TRACK) {
        this.markUnavailable(new TrackUnavailable('playback keeps failing'))
        return
      }
      this.deckTracks.delete(deck.id)
    }
    this.d.logger.debug('reloading after deck error', { trackId: info.trackId })
    this.applyState(this.state ?? state, true)
  }

  // ── Цикл коррекции дрейфа ───────────────────────────────────────────────────

  expectedPositionMs(): number {
    if (!this.state) return 0
    return expectedPosition(this.state, this.clockSync.serverNow(this.d.clock.now()))
  }

  private measureDrift(): { drift: number; expected: number; actual: number } | null {
    const state = this.state
    const deck = this.active
    if (state?.status !== 'playing' || !this.started || deck.paused || deck.seeking) return null
    const serverNow = this.clockSync.serverNow(this.d.clock.now())
    if (serverNow < state.anchorServerMs) return null
    const expected = expectedPosition(state, serverNow)
    const latency = this.latencyCompensation ? (this.d.outputLatencyMs() ?? 0) : 0
    const actual = deck.currentTimeMs - latency
    return { drift: actual - expected, expected, actual }
  }

  /** Один шаг коррекции. Вызывается таймером; пропуски тиков не накапливают ошибку. */
  tick(): void {
    this.maybePreload()
    const m = this.measureDrift()
    if (!m) {
      this.lastDriftMs = null
      this.updateSync()
      return
    }
    const now = this.d.clock.now()
    this.lastDriftMs = m.drift
    if (this.startLatencyPending && now - this.playStartedAt >= 300) {
      // Учимся на старте: отстали на X → в следующий раз жмём play() на X раньше.
      this.startLatencyPending = false
      this.startLatencyMs = Math.min(200, Math.max(0, this.startLatencyMs - m.drift * 0.5))
    }
    const state = this.state
    if (state && state.durationMs - m.expected > 300) {
      const action = this.controller.update(m.drift, m.expected, now)
      if (action.kind === 'seek') {
        this.active.seek(action.targetMs)
      } else if (Math.abs(this.active.playbackRate - action.rate) > 0.0005) {
        this.active.playbackRate = action.rate
      }
    }
    if (now - this.lastReportAt >= DRIFT_REPORT_MS) {
      this.lastReportAt = now
      this.d.send({
        type: 'drift_report',
        driftMs: Math.round(m.drift * 10) / 10,
        playbackRate: this.active.playbackRate,
        offsetMs: Math.round(this.clockSync.offsetMs),
        rttMs: Math.round(this.clockSync.rttMs ?? 0),
        outputLatencyMs: this.d.outputLatencyMs(),
      })
    }
    this.updateSync()
  }

  private updateSync(): void {
    let next: SyncState
    const state = this.state
    if (state?.status !== 'playing' || !this.audioUnlocked || this.trackUnavailable) next = 'idle'
    else if (this.controller.unstable) next = 'unstable'
    else if (this.buffering) next = 'buffering'
    else {
      const drift = this.controller.smoothedDriftMs ?? this.lastDriftMs
      next = drift !== null && Math.abs(drift) <= IN_SYNC_THRESHOLD_MS ? 'in_sync' : 'catching_up'
    }
    if (next !== this.sync) {
      this.sync = next
      this.sendStatus()
      this.emit()
    }
  }

  private sendStatus(force = false): void {
    const key = `${this.audioUnlocked}|${this.trackUnavailable}|${this.sync}`
    if (!force && key === this.lastStatusSent) return
    this.lastStatusSent = key
    this.d.send({
      type: 'client_status',
      audioUnlocked: this.audioUnlocked,
      trackUnavailable: this.trackUnavailable,
      sync: this.sync,
    })
  }

  // ── Разблокировка звука ─────────────────────────────────────────────────────

  /** Вызывать синхронно из обработчика клика/тапа (политики автовоспроизведения). */
  async unlock(): Promise<void> {
    await Promise.all(this.d.decks.map((deck) => deck.unlock()))
    this.audioUnlocked = true
    this.sendStatus()
    if (this.state) this.applyState(this.state, true)
    this.emit()
  }

  // ── Отладка и e2e ───────────────────────────────────────────────────────────

  setLatencyCompensation(enabled: boolean): void {
    this.latencyCompensation = enabled
    this.emit()
  }

  setProfile(profile: DriftProfile): void {
    this.controller.profile = profile
    this.emit()
  }

  debugInfo(): DebugInfo {
    const pos = this.expectedPositionMs()
    return {
      offsetMs: this.clockSync.offsetMs,
      rttMs: this.clockSync.rttMs,
      clockSamples: this.clockSync.sampleCount,
      driftMs: this.lastDriftMs,
      smoothedDriftMs: this.controller.smoothedDriftMs,
      playbackRate: this.active.playbackRate,
      bufferedAheadMs: this.active.bufferedAheadMs(pos),
      version: this.state?.version ?? 0,
      status: this.state?.status ?? 'none',
      outputLatencyMs: this.d.outputLatencyMs(),
      latencyCompensation: this.latencyCompensation,
      profile: this.controller.profile.name,
      seekLatencyMs: this.controller.seekLatencyMs,
      startLatencyMs: this.startLatencyMs,
      seekFailures: this.controller.seekFailureCount,
      unstable: this.controller.unstable,
      sync: this.sync,
    }
  }

  probe(): SyncProbe {
    const now = this.d.clock.now()
    const serverNow = this.clockSync.serverNow(now)
    const m = this.measureDrift()
    return {
      serverNow,
      expectedMs: this.state ? expectedPosition(this.state, serverNow) : 0,
      actualMs: m ? m.actual : null,
      driftMs: m ? m.drift : null,
      offsetMs: this.clockSync.offsetMs,
      rttMs: this.clockSync.rttMs,
      version: this.state?.version ?? 0,
      status: this.state?.status ?? null,
      trackId: this.state?.trackId ?? null,
      queueItemId: this.state?.queueItemId ?? null,
      playing: !this.active.paused,
      rate: this.active.playbackRate,
    }
  }
}

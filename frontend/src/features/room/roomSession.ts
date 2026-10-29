// Сессия комнаты: WebSocket + движок синхронизации + два аудиоэлемента + команды с ack/error.
// Живёт вне React (один экземпляр на открытую комнату), UI читает состояние из roomStore.

import { useAuthIssue } from '@/features/auth/authIssue'
import { BrowserScheduler, HtmlAudioDeck, LatencyProbe, browserClock } from '@/player/browser'
import { detectProfile } from '@/player/platform'
import { SyncEngine } from '@/player/syncEngine'
import { type StreamResolver, TrackUnavailable } from '@/player/types'
import { ApiError, api } from '@/shared/api'
import type { ClientMessage, ServerMessage } from '@/shared/protocol/generated'
import { RoomSocket, roomSocketUrl } from '@/shared/roomSocket'

import { applyServerMessage, resetRoomStore, useRoomStore } from './roomStore'

const COMMAND_TIMEOUT_MS = 10_000

type CommandMessage = Extract<ClientMessage, { clientMsgId: string }>
type CommandInput = CommandMessage extends infer M
  ? M extends CommandMessage
    ? Omit<M, 'clientMsgId'>
    : never
  : never

export class CommandError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'CommandError'
  }
}

interface Pending {
  resolve: () => void
  reject: (err: CommandError) => void
  timer: number
}

const streamResolver: StreamResolver = {
  async resolve(trackId) {
    try {
      const info = await api.stream(trackId)
      return { url: info.url, mirrors: info.mirrors }
    } catch (err) {
      if (err instanceof ApiError && [402, 404, 422].includes(err.status)) {
        throw new TrackUnavailable(err.message)
      }
      if (err instanceof ApiError && err.status === 401) {
        useAuthIssue.setState({ relogin: true })
        throw new TrackUnavailable(err.message)
      }
      throw err
    }
  },
}

export class RoomSession {
  readonly engine: SyncEngine
  readonly decks: readonly [HtmlAudioDeck, HtmlAudioDeck]
  private readonly socket: RoomSocket
  private readonly latency = new LatencyProbe()
  private readonly pending = new Map<string, Pending>()
  private seq = 0
  private readonly cleanups: (() => void)[] = []
  private errorListeners = new Set<(err: CommandError) => void>()

  constructor(readonly slug: string) {
    resetRoomStore()
    this.decks = [new HtmlAudioDeck('a'), new HtmlAudioDeck('b')]
    const params = new URLSearchParams(window.location.search)
    this.engine = new SyncEngine({
      clock: browserClock,
      scheduler: new BrowserScheduler(),
      decks: this.decks,
      resolver: streamResolver,
      send: (msg) => {
        this.socket.send(msg)
      },
      profile: detectProfile({
        userAgent: navigator.userAgent,
        maxTouchPoints: navigator.maxTouchPoints,
        override: params.get('syncProfile'),
      }),
      outputLatencyMs: () => this.latency.outputLatencyMs(),
      logger: {
        debug: (msg, data) => {
          if (params.has('debug')) console.debug('[sync]', msg, data ?? '')
        },
        warn: (msg, data) => {
          console.warn('[sync]', msg, data ?? '')
        },
      },
    })
    this.socket = new RoomSocket(roomSocketUrl(slug), {
      onOpen: () => {
        this.engine.onConnected()
      },
      onMessage: (msg) => {
        this.onMessage(msg)
      },
      onStatus: (status) => {
        useRoomStore.setState({ status })
        if (status !== 'open') this.failPending('Нет связи — команда не дошла.')
      },
      onTerminal: (code) => {
        useRoomStore.setState({ terminalCode: code })
        this.engine.stop()
      },
    })
    this.cleanups.push(
      this.engine.subscribe(() => {
        useRoomStore.setState({
          audioUnlocked: this.engine.audioUnlocked,
          sync: this.engine.sync,
          trackUnavailable: this.engine.trackUnavailable,
        })
      }),
    )
    const onOnline = (): void => {
      this.socket.reconnectNow()
    }
    const onVisible = (): void => {
      if (document.visibilityState === 'visible') this.engine.tick()
    }
    window.addEventListener('online', onOnline)
    document.addEventListener('visibilitychange', onVisible)
    this.cleanups.push(() => {
      window.removeEventListener('online', onOnline)
      document.removeEventListener('visibilitychange', onVisible)
    })
    window.__syncProbe = () => this.engine.probe()
    window.__roomSession = this
  }

  start(): void {
    this.engine.start()
    this.socket.connect()
  }

  dispose(): void {
    this.socket.close()
    this.engine.stop()
    for (const deck of this.decks) deck.unload()
    for (const c of this.cleanups) c()
    this.failPending('Комната закрыта.')
    if (window.__roomSession === this) {
      delete window.__roomSession
      delete window.__syncProbe
    }
  }

  private onMessage(msg: ServerMessage): void {
    this.engine.handleMessage(msg)
    applyServerMessage(msg)
    if (msg.type === 'ack') {
      const p = this.pending.get(msg.clientMsgId)
      if (p) {
        window.clearTimeout(p.timer)
        this.pending.delete(msg.clientMsgId)
        p.resolve()
      }
    } else if (msg.type === 'error') {
      const err = new CommandError(msg.code, msg.message)
      const p = msg.clientMsgId ? this.pending.get(msg.clientMsgId) : undefined
      if (p && msg.clientMsgId) {
        window.clearTimeout(p.timer)
        this.pending.delete(msg.clientMsgId)
        p.reject(err)
      } else {
        for (const l of this.errorListeners) l(err)
      }
    }
  }

  private failPending(message: string): void {
    for (const [id, p] of this.pending) {
      window.clearTimeout(p.timer)
      p.reject(new CommandError('offline', message))
      this.pending.delete(id)
    }
  }

  onError(listener: (err: CommandError) => void): () => void {
    this.errorListeners.add(listener)
    return () => this.errorListeners.delete(listener)
  }

  /** Отправить команду; промис завершается по `ack` или отклоняется по `error`/таймауту. */
  command(input: CommandInput): Promise<void> {
    const clientMsgId = `c${String(++this.seq)}-${Date.now().toString(36)}`
    const msg: CommandMessage = { ...input, clientMsgId }
    return new Promise<void>((resolve, reject) => {
      if (!this.socket.send(msg)) {
        reject(new CommandError('offline', 'Нет связи с комнатой — переподключаемся…'))
        return
      }
      const timer = window.setTimeout(() => {
        this.pending.delete(clientMsgId)
        reject(new CommandError('timeout', 'Сервер не ответил. Попробуйте ещё раз.'))
      }, COMMAND_TIMEOUT_MS)
      this.pending.set(clientMsgId, { resolve, reject, timer })
    })
  }

  /** Разорвать соединение (отладка, e2e): клиент переподключится сам. */
  dropConnection(): void {
    this.socket.drop()
  }

  /** Разблокировать звук — вызывать синхронно из обработчика клика. */
  unlockAudio(): void {
    this.latency.resume()
    void this.engine.unlock()
  }

  setVolume(volume: number, muted: boolean): void {
    for (const deck of this.decks) {
      deck.volume = volume
      deck.muted = muted
    }
  }
}

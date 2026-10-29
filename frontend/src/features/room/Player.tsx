import { useEffect, useRef, useState } from 'react'

import { artistNames, formatTime } from '@/shared/format'
import type { RepeatMode } from '@/shared/protocol/generated'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import {
  MuteIcon,
  NextIcon,
  PauseIcon,
  PlayIcon,
  PrevIcon,
  RepeatIcon,
  VolumeIcon,
} from '@/shared/ui/icons'

import { useRoomSession } from './RoomContext'
import { useRoomStore } from './roomStore'
import { usePlaybackActions } from './usePlaybackActions'
import { ReactionBurst } from './ReactionBurst'
import { useCommand } from './useCommand'

const NEXT_REPEAT: Record<RepeatMode, RepeatMode> = { off: 'queue', queue: 'track', track: 'off' }
const REPEAT_LABEL: Record<RepeatMode, string> = {
  off: 'Повтор выключен',
  queue: 'Повтор очереди',
  track: 'Повтор трека',
}

/** Позиция для прогресс-бара: каждый кадр из движка (по формуле серверного состояния). */
function usePosition(): number {
  const session = useRoomSession()
  const [pos, setPos] = useState(0)
  useEffect(() => {
    let frame = 0
    let last = -1
    const loop = (): void => {
      const p = Math.floor(session.engine.expectedPositionMs() / 250)
      if (p !== last) {
        last = p
        setPos(p * 250)
      }
      frame = requestAnimationFrame(loop)
    }
    frame = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(frame)
    }
  }, [session])
  return pos
}

export function Player() {
  const playback = useRoomStore((s) => s.playback)
  const current = useRoomStore((s) => s.queue?.current ?? null)
  const repeat = useRoomStore((s) => s.queue?.repeat ?? 'off')
  const trackUnavailable = useRoomStore((s) => s.trackUnavailable)
  const send = useCommand()
  const actions = usePlaybackActions()
  const position = usePosition()
  const [scrub, setScrub] = useState<number | null>(null)
  const track = current?.track
  const duration = playback?.durationMs ?? 0
  const status = playback?.status ?? 'paused'
  const shown = scrub ?? Math.min(position, duration)

  return (
    <section aria-label="Плеер" className="flex flex-col gap-4">
      <div className="relative flex items-center gap-4 lg:flex-col lg:items-stretch">
        <ReactionBurst />
        <Cover
          url={track?.coverUrl}
          size="lg"
          alt={track ? `Обложка: ${track.title}` : 'Нет трека'}
          className="size-20 shadow-xl sm:size-28 lg:aspect-square lg:size-auto lg:w-full"
          rounded="rounded-xl"
        />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold lg:text-xl" data-testid="track-title">
            {track?.title ?? 'Ничего не играет'}
          </h2>
          <p className="text-fg-muted truncate">
            {track ? artistNames(track.artists) : 'Добавьте трек в очередь'}
          </p>
          {status === 'loading' && <p className="text-fg-subtle text-xs">Загружаем у всех…</p>}
          {trackUnavailable && (
            <p role="status" className="text-warn mt-1 text-sm">
              У вас этот трек недоступен — остальные слушают дальше.
            </p>
          )}
        </div>
      </div>

      <div className="space-y-1">
        <input
          type="range"
          aria-label="Позиция трека"
          min={0}
          max={Math.max(1, duration)}
          step={1000}
          value={shown}
          disabled={!track}
          onChange={(e) => {
            setScrub(Number(e.target.value))
          }}
          onPointerUp={() => {
            if (scrub !== null) actions.seek(scrub)
            setScrub(null)
          }}
          onKeyUp={(e) => {
            if (scrub !== null && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
              actions.seek(scrub)
              setScrub(null)
            }
          }}
          className="w-full accent-[var(--c-accent)]"
        />
        <div className="text-fg-subtle flex justify-between text-xs tabular-nums">
          <span data-testid="position">{formatTime(shown)}</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <IconButton
          label={REPEAT_LABEL[repeat]}
          active={repeat !== 'off'}
          onClick={() => {
            void send({ type: 'cmd.set_repeat', mode: NEXT_REPEAT[repeat] })
          }}
        >
          <span className="relative">
            <RepeatIcon />
            {repeat === 'track' && (
              <span className="absolute -top-1 -right-2 text-[10px] font-bold">1</span>
            )}
          </span>
        </IconButton>
        <div className="flex items-center gap-2">
          <IconButton label="Предыдущий" onClick={actions.prev} disabled={!track}>
            <PrevIcon />
          </IconButton>
          <button
            type="button"
            aria-label={status === 'paused' ? 'Играть' : 'Пауза'}
            onClick={actions.playPause}
            className="focus-ring bg-fg text-surface-0 flex size-14 items-center justify-center rounded-full transition-transform hover:scale-105 active:scale-95"
          >
            {status === 'paused' ? <PlayIcon size={26} /> : <PauseIcon size={26} />}
          </button>
          <IconButton label="Следующий" onClick={actions.next} disabled={!track}>
            <NextIcon />
          </IconButton>
        </div>
        <VolumeControl />
      </div>
    </section>
  )
}

const VOLUME_KEY = 'mt.volume'

function readVolume(): { volume: number; muted: boolean } {
  try {
    const raw = localStorage.getItem(VOLUME_KEY)
    if (raw) {
      const v = JSON.parse(raw) as { volume?: unknown; muted?: unknown }
      return {
        volume: typeof v.volume === 'number' ? Math.min(1, Math.max(0, v.volume)) : 1,
        muted: v.muted === true,
      }
    }
  } catch {
    /* localStorage недоступен — громкость по умолчанию */
  }
  return { volume: 1, muted: false }
}

/** Громкость и mute — локальные для участника, не синхронизируются (SPEC §4.5). */
function VolumeControl() {
  const session = useRoomSession()
  const [state, setState] = useState(readVolume)
  const first = useRef(true)
  useEffect(() => {
    session.setVolume(state.volume, state.muted)
    if (first.current) {
      first.current = false
      return
    }
    try {
      localStorage.setItem(VOLUME_KEY, JSON.stringify(state))
    } catch {
      /* без сохранения */
    }
  }, [session, state])
  return (
    <div className="group flex items-center gap-1">
      <IconButton
        label={state.muted ? 'Включить звук' : 'Выключить звук'}
        onClick={() => {
          setState((s) => ({ ...s, muted: !s.muted }))
        }}
      >
        {state.muted || state.volume === 0 ? <MuteIcon /> : <VolumeIcon />}
      </IconButton>
      <input
        type="range"
        aria-label="Громкость"
        min={0}
        max={1}
        step={0.01}
        value={state.muted ? 0 : state.volume}
        onChange={(e) => {
          setState({ volume: Number(e.target.value), muted: false })
        }}
        className="hidden w-20 accent-[var(--c-accent)] sm:block"
      />
    </div>
  )
}

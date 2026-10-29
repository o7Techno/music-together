// Компактный плеер снизу на мобильных (SPEC §8): обложка, название, тонкий прогресс, кнопки.
// Тап по названию разворачивает полный плеер.

import { useEffect, useState } from 'react'

import { artistNames } from '@/shared/format'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { NextIcon, PauseIcon, PlayIcon } from '@/shared/ui/icons'

import { useRoomSession } from './RoomContext'
import { useRoomStore } from './roomStore'
import { usePlaybackActions } from './usePlaybackActions'

function useProgress(): number {
  const session = useRoomSession()
  const duration = useRoomStore((s) => s.playback?.durationMs ?? 0)
  const [ratio, setRatio] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => {
      setRatio(duration > 0 ? Math.min(1, session.engine.expectedPositionMs() / duration) : 0)
    }, 500)
    return () => {
      window.clearInterval(t)
    }
  }, [session, duration])
  return ratio
}

export function MiniPlayer({ onExpand }: { onExpand: () => void }) {
  const track = useRoomStore((s) => s.queue?.current?.track ?? null)
  const status = useRoomStore((s) => s.playback?.status ?? 'paused')
  const actions = usePlaybackActions()
  const progress = useProgress()
  return (
    <div
      className="bg-surface-2/95 border-border relative border-t backdrop-blur"
      data-testid="mini-player"
    >
      <div
        className="bg-accent absolute top-0 left-0 h-0.5 transition-[width] duration-500"
        style={{ width: `${String(progress * 100)}%` }}
        aria-hidden="true"
      />
      <div className="flex items-center gap-3 px-3 py-2">
        <button
          type="button"
          onClick={onExpand}
          className="focus-ring flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left"
          aria-label="Открыть плеер"
        >
          <Cover url={track?.coverUrl} size="sm" className="size-11" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">
              {track?.title ?? 'Ничего не играет'}
            </span>
            <span className="text-fg-muted block truncate text-xs">
              {track ? artistNames(track.artists) : 'Добавьте трек'}
            </span>
          </span>
        </button>
        <IconButton
          label={status === 'paused' ? 'Играть' : 'Пауза'}
          size="lg"
          onClick={actions.playPause}
          className="text-fg"
        >
          {status === 'paused' ? <PlayIcon size={26} /> : <PauseIcon size={26} />}
        </IconButton>
        <IconButton label="Следующий" size="lg" onClick={actions.next} disabled={!track}>
          <NextIcon size={24} />
        </IconButton>
      </div>
    </div>
  )
}

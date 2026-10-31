// Media Session API (SPEC §4.5): экран блокировки, медиаклавиши, уведомления. Команды идут в
// комнату как обычные — пауза с телефона ставит паузу у всех.

import { useEffect } from 'react'

import { isIOS } from '@/player/platform'
import { coverSrc } from '@/shared/ui/Cover'

import { useRoomSession } from './RoomContext'
import { useRoomStore } from './roomStore'
import { usePlaybackActions } from './usePlaybackActions'

/** iOS показывает на экране блокировки либо перемотку на 10 с, либо «следующий / предыдущий». */
export function usesTrackButtonsOnly(info: { userAgent: string; maxTouchPoints: number }): boolean {
  return isIOS(info)
}

export function useMediaSession(): void {
  const session = useRoomSession()
  const actions = usePlaybackActions()
  const track = useRoomStore((s) => s.queue?.current?.track ?? null)
  const playback = useRoomStore((s) => s.playback)

  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    const ms = navigator.mediaSession
    const seekSteps: [MediaSessionAction, MediaSessionActionHandler][] = usesTrackButtonsOnly(
      navigator,
    )
      ? []
      : [
          [
            'seekforward',
            (d) => {
              actions.seek(session.engine.expectedPositionMs() + (d.seekOffset ?? 10) * 1000)
            },
          ],
          [
            'seekbackward',
            (d) => {
              actions.seek(session.engine.expectedPositionMs() - (d.seekOffset ?? 10) * 1000)
            },
          ],
        ]
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ['play', actions.play],
      ['pause', actions.pause],
      ['nexttrack', actions.next],
      ['previoustrack', actions.prev],
      [
        'seekto',
        (d) => {
          if (d.seekTime !== undefined) actions.seek(d.seekTime * 1000)
        },
      ],
      ...seekSteps,
    ]
    for (const [action, handler] of handlers) {
      try {
        ms.setActionHandler(action, handler)
      } catch {
        /* действие не поддерживается браузером */
      }
    }
    return () => {
      for (const [action] of handlers) {
        try {
          ms.setActionHandler(action, null)
        } catch {
          /* ignore */
        }
      }
    }
  }, [session, actions])

  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    const ms = navigator.mediaSession
    if (!track) {
      ms.metadata = null
      return
    }
    const artwork = (['md', 'lg', 'xl'] as const)
      .map((size) => coverSrc(track.coverUrl, size))
      .filter((src): src is string => src !== null)
      .map((src, i) => ({ src, sizes: ['200x200', '400x400', '1000x1000'][i] ?? '400x400' }))
    ms.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artists.map((a) => a.name).join(', '),
      album: track.albumTitle ?? '',
      artwork,
    })
  }, [track])

  useEffect(() => {
    if (!('mediaSession' in navigator) || !playback) return
    const ms = navigator.mediaSession
    ms.playbackState = playback.status === 'paused' ? 'paused' : 'playing'
    if (playback.durationMs > 0 && 'setPositionState' in ms) {
      try {
        ms.setPositionState({
          duration: playback.durationMs / 1000,
          position: Math.min(playback.durationMs, session.engine.expectedPositionMs()) / 1000,
          playbackRate: 1,
        })
      } catch {
        /* некорректные значения в переходных состояниях — пропускаем */
      }
    }
  }, [playback, session])
}

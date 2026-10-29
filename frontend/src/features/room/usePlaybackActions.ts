import { useMemo } from 'react'

import { useRoomStore } from './roomStore'
import { useCommand } from './useCommand'

/** Команды воспроизведения с актуальным expectedQueueItemId (антидребезг на сервере, SPEC §4.5). */
export function usePlaybackActions() {
  const send = useCommand()
  return useMemo(() => {
    const current = (): string | null => useRoomStore.getState().playback?.queueItemId ?? null
    return {
      playPause: () => {
        const s = useRoomStore.getState().playback
        void send({ type: s?.status === 'paused' ? 'cmd.play' : 'cmd.pause' })
      },
      play: () => void send({ type: 'cmd.play' }),
      pause: () => void send({ type: 'cmd.pause' }),
      next: () => void send({ type: 'cmd.next', expectedQueueItemId: current() }),
      prev: () => void send({ type: 'cmd.prev', expectedQueueItemId: current() }),
      seek: (positionMs: number) =>
        void send({
          type: 'cmd.seek',
          positionMs: Math.max(0, Math.round(positionMs)),
          expectedQueueItemId: current(),
        }),
    }
  }, [send])
}

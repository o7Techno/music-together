// Запуск и команды волны. Сервер сам решает, что играет следующим: клиент только отображает.

import { useCallback } from 'react'

import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import type { WaveMode, WaveSeed } from '@/shared/protocol/generated'
import { toast } from '@/shared/ui/Toaster'

const EXPLAINED_KEY = 'mt.waveExplained'
const DISLIKE_HINT_KEY = 'mt.waveDislikeHint'

/** Показать пояснение один раз. Без localStorage покажем снова: это не страшно. */
function once(key: string, message: string): void {
  try {
    if (localStorage.getItem(key)) return
    localStorage.setItem(key, '1')
  } catch {
    /* показываем без запоминания */
  }
  toast.info(message)
}

export function useWaveStart() {
  const send = useCommand()
  return useCallback(
    async (
      mode: WaveMode,
      options: { seed?: WaveSeed; settings?: string[] } = {},
    ): Promise<boolean> => {
      const { wave, selfUserId } = useRoomStore.getState()
      const active = wave !== null && wave.status !== 'off'
      if (active && wave.ownerId !== selfUserId) {
        const name = wave.ownerName ?? 'другого участника'
        if (!window.confirm(`Заменить волну ${name} на свою?`)) return false
      }
      once(
        EXPLAINED_KEY,
        'Волна учится на том, что слушает вся комната. Отключить можно в панели «Волна».',
      )
      return send({
        type: 'wave.start',
        mode,
        seed: options.seed ?? null,
        settings: options.settings ?? [],
        expectedWaveId: active ? wave.waveId : null,
      })
    },
    [send],
  )
}

/** «Не нравится»: пропуск трека волны, у её владельца — ещё и дизлайк в аккаунте. */
export function useDislike() {
  const send = useCommand()
  return useCallback(() => {
    const { playback, queue, selfUserId } = useRoomStore.getState()
    if (queue?.current?.origin.ownerId === selfUserId) {
      once(DISLIKE_HINT_KEY, 'Дизлайк сохранится в вашем аккаунте и повлияет на рекомендации.')
    }
    void send({ type: 'track.dislike', expectedQueueItemId: playback?.queueItemId ?? null })
  }, [send])
}

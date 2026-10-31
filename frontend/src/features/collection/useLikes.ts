// Лайки: все id загружаются разом и лежат в кеше как Set. Яндекс всё равно отдаёт только полный
// список, а запросы по видимым строкам дали бы поток запросов при прокрутке (SPEC-wave §6.1).

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { useRoomStore } from '@/features/room/roomStore'
import { ApiError, api } from '@/shared/api'
import { toast } from '@/shared/ui/Toaster'

const LIKED_KEY = ['liked-ids']
const STALE_MS = 2 * 60_000
const EMPTY: ReadonlySet<string> = new Set()

export function useLikedIds(): ReadonlySet<string> {
  const query = useQuery({
    queryKey: LIKED_KEY,
    queryFn: async () => new Set((await api.likedIds()).trackIds),
    staleTime: STALE_MS,
  })
  return query.data ?? EMPTY
}

/** Лайк с оптимистичным обновлением: при ошибке — откат и тост. */
export function useToggleLike(): (trackId: string) => void {
  const qc = useQueryClient()
  return useCallback(
    (trackId: string) => {
      const before = qc.getQueryData<Set<string>>(LIKED_KEY) ?? new Set<string>()
      const liked = !before.has(trackId)
      const next = new Set(before)
      if (liked) next.add(trackId)
      else next.delete(trackId)
      qc.setQueryData(LIKED_KEY, next)
      const room = useRoomStore.getState().room?.slug
      const request = liked ? api.like(trackId, room) : api.unlike(trackId, room)
      request.catch((err: unknown) => {
        qc.setQueryData<Set<string>>(LIKED_KEY, (current) => {
          const restored = new Set(current)
          if (liked) restored.delete(trackId)
          else restored.add(trackId)
          return restored
        })
        toast.error(err instanceof ApiError ? err.message : 'Не получилось. Попробуйте ещё раз.')
      })
    },
    [qc],
  )
}

// Добавление треков в очередь: лимит за раз, предупреждение о дубликатах (спросить, не блокировать).

import { useCallback } from 'react'

import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import { plural } from '@/shared/format'
import { toast } from '@/shared/ui/Toaster'

export const MAX_BATCH = 500

export type SourceKind = 'album' | 'playlist' | 'artist' | 'liked' | 'link' | 'search' | 'history'
export type AddPosition = 'end' | 'next' | 'now'

export interface AddOptions {
  position?: AddPosition
  source: { kind: SourceKind; title?: string | null }
  /** Не спрашивать про дубликаты (повторное подтверждение). */
  force?: boolean
}

export function queuedTrackIds(): Set<string> {
  const q = useRoomStore.getState().queue
  const ids = new Set<string>()
  if (q?.current) ids.add(q.current.track.id)
  for (const item of q?.upcoming ?? []) ids.add(item.track.id)
  return ids
}

export function shuffled<T>(items: readonly T[], random: () => number = Math.random): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j] as T, copy[i] as T]
  }
  return copy
}

export function useAddTracks() {
  const send = useCommand()
  const sendAdd = useCallback(
    async (trackIds: string[], opts: AddOptions, dupes: number): Promise<boolean> => {
      if (trackIds.length > MAX_BATCH) {
        toast.info(
          `За раз можно добавить до ${String(MAX_BATCH)} треков — добавляем первые ${String(MAX_BATCH)}.`,
        )
      }
      const ids = trackIds.slice(0, MAX_BATCH)
      const ok = await send({
        type: 'queue.add',
        trackIds: ids,
        position: opts.position ?? 'end',
        source: { kind: opts.source.kind, title: opts.source.title ?? null },
      })
      if (ok && dupes > 0 && dupes < trackIds.length) {
        toast.info(
          `${String(dupes)} ${plural(dupes, 'трек уже был', 'трека уже были', 'треков уже были')} в очереди`,
        )
      }
      return ok
    },
    [send],
  )
  return useCallback(
    async (trackIds: string[], opts: AddOptions): Promise<boolean> => {
      if (trackIds.length === 0) return false
      const queued = queuedTrackIds()
      const dupes = trackIds.filter((id) => queued.has(id)).length
      if (!opts.force && dupes > 0 && dupes === trackIds.length) {
        // Все треки уже в очереди — спрашиваем, а не блокируем (SPEC §4.3).
        const what = trackIds.length === 1 ? 'Этот трек уже в очереди' : 'Эти треки уже в очереди'
        toast.withAction(`${what}. Добавить ещё раз?`, 'Добавить', () => {
          void sendAdd(trackIds, opts, dupes)
        })
        return false
      }
      return sendAdd(trackIds, opts, dupes)
    },
    [sendAdd],
  )
}

// Карточка набора треков (альбом, плейлист, артист, трек по ссылке): добавить всё одним действием.

import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import { plural } from '@/shared/format'
import type { TrackList } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { toast } from '@/shared/ui/Toaster'

export const MAX_BATCH = 500

const KIND_LABEL: Record<string, string> = {
  track: 'Трек',
  album: 'Альбом',
  playlist: 'Плейлист',
  artist: 'Исполнитель',
  liked: 'Мне нравится',
}

export type SourceKind = 'album' | 'playlist' | 'artist' | 'liked' | 'link' | 'search'

export function useAddTracks() {
  const send = useCommand()
  return async (
    trackIds: string[],
    opts: {
      position?: 'end' | 'next' | 'now'
      source: { kind: SourceKind; title?: string | null }
    },
  ): Promise<boolean> => {
    if (trackIds.length === 0) return false
    if (trackIds.length > MAX_BATCH) {
      toast.info(
        `За раз можно добавить до ${String(MAX_BATCH)} треков — добавим первые ${String(MAX_BATCH)}.`,
      )
    }
    return send({
      type: 'queue.add',
      trackIds: trackIds.slice(0, MAX_BATCH),
      position: opts.position ?? 'end',
      source: { kind: opts.source.kind, title: opts.source.title ?? null },
    })
  }
}

export function TrackListCard({
  list,
  sourceKind = 'link',
}: {
  list: TrackList
  sourceKind?: SourceKind
}) {
  const add = useAddTracks()
  const queue = useRoomStore((s) => s.queue)
  const available = list.tracks.filter((t) => t.available)
  const ids = available.map((t) => t.id)
  const inQueue = new Set([
    queue?.current?.track.id,
    ...(queue?.upcoming.map((i) => i.track.id) ?? []),
  ])
  const duplicates = ids.filter((id) => inQueue.has(id)).length
  const source = { kind: list.kind === 'track' ? 'link' : sourceKind, title: list.title } as const
  return (
    <div
      className="border-border bg-surface-2 flex gap-3 rounded-xl border p-3"
      data-testid="link-card"
    >
      <Cover url={list.coverUrl} size="md" className="size-16" />
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <p className="text-fg-subtle text-xs">{KIND_LABEL[list.kind] ?? list.kind}</p>
          <p className="truncate font-medium">{list.title}</p>
          {list.subtitle && <p className="text-fg-muted truncate text-sm">{list.subtitle}</p>}
          {list.kind !== 'track' && (
            <p className="text-fg-subtle text-xs">
              {available.length} {plural(available.length, 'трек', 'трека', 'треков')}
              {available.length < list.tracks.length &&
                ` · ${String(list.tracks.length - available.length)} недоступно`}
            </p>
          )}
          {duplicates > 0 && (
            <p className="text-warn text-xs">
              {duplicates === ids.length ? 'Уже в очереди' : `${String(duplicates)} уже в очереди`}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={ids.length === 0}
            onClick={() => void add(ids, { source })}
          >
            {list.kind === 'track' ? 'В очередь' : 'Добавить все'}
          </Button>
          <Button
            size="sm"
            disabled={ids.length === 0}
            onClick={() => void add(ids, { position: 'next', source })}
          >
            Играть следующим
          </Button>
        </div>
      </div>
    </div>
  )
}

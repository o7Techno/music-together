// Карточка набора треков по ссылке (трек, альбом, плейлист, артист): добавить одним действием.

import { useAddNav } from '@/features/add/addNav'
import { type SourceKind, queuedTrackIds, useAddTracks } from '@/features/add/useAddTracks'
import { useRoomStore } from '@/features/room/roomStore'
import { plural } from '@/shared/format'
import type { TrackList } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'

const KIND_LABEL: Record<string, string> = {
  track: 'Трек',
  album: 'Альбом',
  playlist: 'Плейлист',
  artist: 'Исполнитель',
  liked: 'Мне нравится',
}

export function TrackListCard({ list, onAdded }: { list: TrackList; onAdded?: () => void }) {
  const add = useAddTracks()
  const open = useAddNav((s) => s.open)
  // Подписка на очередь — чтобы метка «уже в очереди» обновлялась.
  useRoomStore((s) => s.queue?.version)
  const available = list.tracks.filter((t) => t.available)
  const ids = available.map((t) => t.id)
  const queued = queuedTrackIds()
  const duplicates = ids.filter((id) => queued.has(id)).length
  const kind: SourceKind =
    list.kind === 'track' ? 'link' : list.kind === 'liked' ? 'liked' : list.kind
  const source = { kind, title: list.title }
  const run = async (position: 'end' | 'next'): Promise<void> => {
    if (await add(ids, { position, source })) onAdded?.()
  }
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
          {list.kind === 'track' && available.length === 0 && (
            <p className="text-warn text-xs">Трек недоступен для вашего аккаунта</p>
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
            onClick={() => void run('end')}
          >
            {list.kind === 'track' ? 'В очередь' : 'Добавить все'}
          </Button>
          <Button size="sm" disabled={ids.length === 0} onClick={() => void run('next')}>
            Играть следующим
          </Button>
          {list.kind !== 'track' && list.kind !== 'liked' && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                open({
                  type: list.kind as 'album' | 'playlist' | 'artist',
                  id: list.id,
                  title: list.title,
                })
                onAdded?.()
              }}
            >
              Выбрать треки
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

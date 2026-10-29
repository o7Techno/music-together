// Альбом / плейлист / исполнитель / «Мне нравится»: треки с выбором, у исполнителя — ещё альбомы.

import { useQuery } from '@tanstack/react-query'

import { ApiError, api } from '@/shared/api'
import type { TrackList } from '@/shared/protocol/generated'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'

import { type EntityRef, useAddNav } from './addNav'
import { SelectableTrackList } from './SelectableTrackList'

function load(entity: EntityRef): Promise<TrackList> {
  switch (entity.type) {
    case 'album':
      return api.album(entity.id)
    case 'playlist':
      return api.playlist(entity.id)
    case 'artist':
      return api.artist(entity.id)
    case 'liked':
      return api.myLiked()
  }
}

const LABEL: Record<EntityRef['type'], string> = {
  album: 'Альбом',
  playlist: 'Плейлист',
  artist: 'Исполнитель',
  liked: 'Коллекция',
}

export function EntityView({ entity }: { entity: EntityRef }) {
  const back = useAddNav((s) => s.back)
  const open = useAddNav((s) => s.open)
  const data = useQuery({
    queryKey: ['entity', entity.type, entity.id],
    queryFn: () => load(entity),
    staleTime: 5 * 60_000,
  })
  const list = data.data
  return (
    <div className="flex min-h-0 flex-col gap-3" data-testid="entity-view">
      <div className="flex items-center gap-3">
        <IconButton label="Назад" onClick={back}>
          <span aria-hidden="true" className="text-lg">
            ←
          </span>
        </IconButton>
        <Cover url={list?.coverUrl} size="md" className="size-14" alt={entity.title} />
        <div className="min-w-0">
          <p className="text-fg-subtle text-xs">{LABEL[entity.type]}</p>
          <h3 className="truncate font-semibold">{list?.title ?? entity.title}</h3>
          {list?.subtitle && <p className="text-fg-muted truncate text-sm">{list.subtitle}</p>}
        </div>
      </div>
      {data.isPending && <SkeletonRows />}
      {data.error && (
        <p role="alert" className="text-bad text-sm">
          {data.error instanceof ApiError ? data.error.message : 'Не удалось загрузить.'}
        </p>
      )}
      {list && list.albums.length > 0 && (
        <section className="space-y-2">
          <h4 className="text-fg-muted text-sm font-semibold">Альбомы</h4>
          <ul className="flex scrollbar-thin gap-3 overflow-x-auto pb-1">
            {list.albums.map((a) => (
              <li key={a.id} className="w-24 shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    open({ type: 'album', id: a.id, title: a.title })
                  }}
                  className="focus-ring group w-full rounded-lg text-left"
                >
                  <Cover
                    url={a.coverUrl}
                    size="md"
                    className="aspect-square w-full"
                    alt={a.title}
                  />
                  <span className="mt-1 line-clamp-2 text-xs group-hover:underline">{a.title}</span>
                  {a.year && <span className="text-fg-subtle text-xs">{a.year}</span>}
                </button>
              </li>
            ))}
          </ul>
          <h4 className="text-fg-muted text-sm font-semibold">Популярные треки</h4>
        </section>
      )}
      {list && (
        <SelectableTrackList
          tracks={list.tracks}
          source={{ kind: entity.type === 'liked' ? 'liked' : entity.type, title: list.title }}
        />
      )}
    </div>
  )
}

export function SkeletonRows({ count = 6 }: { count?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-2">
          <div className="bg-surface-3 size-9 animate-pulse rounded" />
          <div className="flex-1 space-y-1.5">
            <div className="bg-surface-3 h-3 w-2/3 animate-pulse rounded" />
            <div className="bg-surface-3 h-2.5 w-1/3 animate-pulse rounded" />
          </div>
        </div>
      ))}
    </div>
  )
}

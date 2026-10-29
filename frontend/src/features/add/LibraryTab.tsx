// «Мои плейлисты»: «Мне нравится», плейлисты пользователя, альбомы в коллекции (SPEC §4.4).

import { useQuery } from '@tanstack/react-query'

import { ApiError, api } from '@/shared/api'
import { plural } from '@/shared/format'
import { Cover } from '@/shared/ui/Cover'

import { useAddNav } from './addNav'
import { SkeletonRows } from './EntityView'

export function LibraryTab() {
  const open = useAddNav((s) => s.open)
  const playlists = useQuery({ queryKey: ['my-playlists'], queryFn: api.myPlaylists })
  const albums = useQuery({ queryKey: ['my-albums'], queryFn: api.myAlbums })
  const error = playlists.error ?? albums.error

  return (
    <div className="space-y-5" data-testid="library">
      <button
        type="button"
        onClick={() => {
          open({ type: 'liked', id: 'liked', title: 'Мне нравится' })
        }}
        className="focus-ring hover:bg-surface-2 flex w-full items-center gap-3 rounded-xl p-2 text-left"
      >
        <span
          aria-hidden="true"
          className="flex size-12 items-center justify-center rounded-lg bg-gradient-to-br from-rose-500 to-amber-400 text-xl text-white"
        >
          ♥
        </span>
        <span className="font-medium">Мне нравится</span>
        <span aria-hidden="true" className="text-fg-subtle ml-auto">
          ›
        </span>
      </button>

      {error && (
        <p role="alert" className="text-bad text-sm">
          {error instanceof ApiError ? error.message : 'Не удалось загрузить коллекцию.'}
        </p>
      )}

      <section className="space-y-1">
        <h4 className="text-fg-muted px-2 text-sm font-semibold">Плейлисты</h4>
        {playlists.isPending && <SkeletonRows count={3} />}
        {playlists.data?.length === 0 && (
          <p className="text-fg-subtle px-2 text-sm">Своих плейлистов пока нет.</p>
        )}
        <ul>
          {playlists.data?.map((p) => (
            <li key={p.ref}>
              <Row
                title={p.title}
                subtitle={
                  p.trackCount === null
                    ? (p.ownerName ?? '')
                    : `${String(p.trackCount)} ${plural(p.trackCount, 'трек', 'трека', 'треков')}`
                }
                cover={p.coverUrl}
                onClick={() => {
                  open({ type: 'playlist', id: p.ref, title: p.title })
                }}
              />
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-1">
        <h4 className="text-fg-muted px-2 text-sm font-semibold">Альбомы в коллекции</h4>
        {albums.isPending && <SkeletonRows count={3} />}
        {albums.data?.length === 0 && (
          <p className="text-fg-subtle px-2 text-sm">Сохранённых альбомов нет.</p>
        )}
        <ul>
          {albums.data?.map((a) => (
            <li key={a.id}>
              <Row
                title={a.title}
                subtitle={a.artists.map((x) => x.name).join(', ')}
                cover={a.coverUrl}
                onClick={() => {
                  open({ type: 'album', id: a.id, title: a.title })
                }}
              />
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function Row({
  title,
  subtitle,
  cover,
  onClick,
}: {
  title: string
  subtitle: string
  cover: string | null
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="focus-ring hover:bg-surface-2 flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left"
    >
      <Cover url={cover} size="sm" className="size-10" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{title}</span>
        <span className="text-fg-muted block truncate text-xs">{subtitle}</span>
      </span>
      <span aria-hidden="true" className="text-fg-subtle">
        ›
      </span>
    </button>
  )
}

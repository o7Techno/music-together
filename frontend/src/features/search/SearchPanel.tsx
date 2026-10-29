import { type UseQueryResult, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { useCommand } from '@/features/room/useCommand'
import { ApiError, api } from '@/shared/api'
import { artistNames, formatTime } from '@/shared/format'
import { looksLikeYandexLink } from '@/shared/links'
import type { ResolveResponse, Track } from '@/shared/protocol/generated'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { PlayNextIcon, PlusIcon, SearchIcon } from '@/shared/ui/icons'

import { TrackListCard } from './TrackListCard'

const DEBOUNCE_MS = 250

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => {
      setV(value)
    }, ms)
    return () => {
      window.clearTimeout(t)
    }
  }, [value, ms])
  return v
}

export function SearchPanel() {
  const [query, setQuery] = useState('')
  const q = useDebounced(query.trim(), DEBOUNCE_MS)
  const isLink = looksLikeYandexLink(q)
  const results = useQuery({
    queryKey: ['search', q],
    // TanStack Query отменяет устаревший запрос через signal.
    queryFn: ({ signal }) => api.search(q, signal),
    enabled: q.length > 0 && !isLink,
    staleTime: 5 * 60_000,
  })
  const links = useQuery({
    queryKey: ['resolve', q],
    queryFn: ({ signal }) => api.resolveLinks(q, signal),
    enabled: isLink,
    staleTime: 5 * 60_000,
    retry: false,
  })
  return (
    <section aria-label="Поиск" className="flex min-h-0 flex-col gap-3">
      <label className="relative block">
        <span className="sr-only">Поиск треков</span>
        <SearchIcon
          className="text-fg-subtle pointer-events-none absolute top-1/2 left-3 -translate-y-1/2"
          size={18}
        />
        <input
          type="search"
          data-search-input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
          }}
          placeholder="Трек, исполнитель или ссылка Яндекс Музыки"
          className="focus-ring border-border bg-surface-2 h-11 w-full rounded-full border pr-4 pl-10"
        />
      </label>
      {isLink && <LinkResults state={links} />}
      {results.isFetching && <p className="text-fg-subtle text-sm">Ищем…</p>}
      {results.error && (
        <p role="alert" className="text-bad text-sm">
          {results.error instanceof ApiError ? results.error.message : 'Поиск не удался.'}
        </p>
      )}
      {results.data && results.data.tracks.length === 0 && !results.isFetching && (
        <p className="text-fg-muted text-sm">Ничего не нашли.</p>
      )}
      <ul className="space-y-1" data-testid="search-results">
        {results.data?.tracks.map((t) => (
          <TrackRow key={t.id} track={t} />
        ))}
      </ul>
    </section>
  )
}

function LinkResults({ state }: { state: UseQueryResult<ResolveResponse> }) {
  if (state.isFetching) return <p className="text-fg-subtle text-sm">Смотрим ссылку…</p>
  if (state.error) {
    return (
      <p role="alert" className="text-bad text-sm">
        {state.error instanceof ApiError ? state.error.message : 'Не удалось открыть ссылку.'}
      </p>
    )
  }
  if (!state.data) return null
  return (
    <div className="space-y-2">
      {state.data.items.map((list) => (
        <TrackListCard key={`${list.kind}:${list.id}`} list={list} />
      ))}
      {state.data.failures.map((f) => (
        <p key={`${f.kind}:${f.id}`} className="text-warn text-sm">
          {f.message}
        </p>
      ))}
    </div>
  )
}

export function TrackRow({ track }: { track: Track }) {
  const send = useCommand()
  return (
    <li className="group hover:bg-surface-2 flex items-center gap-3 rounded-lg px-2 py-1.5">
      <Cover url={track.coverUrl} size="sm" className="size-10" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{track.title}</p>
        <p className="text-fg-muted truncate text-xs">{artistNames(track.artists)}</p>
      </div>
      <span className="text-fg-subtle text-xs tabular-nums">{formatTime(track.durationMs)}</span>
      <IconButton
        size="sm"
        label={`Играть «${track.title}» следующим`}
        onClick={() => {
          void send({
            type: 'queue.add',
            trackIds: [track.id],
            position: 'next',
            source: { kind: 'search' },
          })
        }}
      >
        <PlayNextIcon size={16} />
      </IconButton>
      <IconButton
        size="sm"
        label={`Добавить «${track.title}» в очередь`}
        onClick={() => {
          void send({ type: 'queue.add', trackIds: [track.id], source: { kind: 'search' } })
        }}
      >
        <PlusIcon size={16} />
      </IconButton>
    </li>
  )
}

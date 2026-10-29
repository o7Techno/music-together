// Поиск (SPEC §4.4): по мере ввода (debounce 250 мс, отмена устаревших), секции результатов,
// клавиатура: ↑/↓ — выбор, Enter — в очередь (или открыть), Shift+Enter — играть следующим.

import { type UseQueryResult, useQuery } from '@tanstack/react-query'
import { type KeyboardEvent, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react'

import { useAddNav } from '@/features/add/addNav'
import { SkeletonRows } from '@/features/add/EntityView'
import { SECTION_TITLES, type SearchRow, moveActive, searchRows } from '@/features/add/searchRows'
import { useAddTracks } from '@/features/add/useAddTracks'
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
  const [nav, setNav] = useState({ q: '', active: -1, expanded: false })
  const q = useDebounced(query.trim(), DEBOUNCE_MS)
  // Новый запрос сбрасывает выбор и раскрытие без эффекта: состояние привязано к q.
  const { active, expanded } = nav.q === q ? nav : { active: -1, expanded: false }
  const setActive = (fn: (i: number) => number): void => {
    setNav({ q, active: fn(active), expanded })
  }
  const isLink = looksLikeYandexLink(q)
  const add = useAddTracks()
  const open = useAddNav((s) => s.open)

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
  const rows = useMemo(
    () => (results.data && !isLink ? searchRows(results.data, expanded) : []),
    [results.data, isLink, expanded],
  )

  const act = (row: SearchRow, next: boolean): void => {
    switch (row.kind) {
      case 'track':
        void add([row.track.id], { position: next ? 'next' : 'end', source: { kind: 'search' } })
        break
      case 'album':
        open({ type: 'album', id: row.album.id, title: row.album.title })
        break
      case 'artist':
        open({ type: 'artist', id: row.artist.id, title: row.artist.name })
        break
      case 'playlist':
        open({ type: 'playlist', id: row.playlist.ref, title: row.playlist.title })
        break
    }
  }

  // Enter до того, как пришли результаты именно этого запроса, не должен сработать по старым:
  // запоминаем и выполняем, когда результаты для набранного текста готовы.
  const pendingEnter = useRef<{ q: string; next: boolean } | null>(null)
  const settled = query.trim() === q && !results.isFetching
  const actOnFirst = useEffectEvent((next: boolean) => {
    const row = rows[0]
    if (row) act(row, next)
  })
  useEffect(() => {
    const pending = pendingEnter.current
    if (!pending || !settled || pending.q !== q) return
    pendingEnter.current = null
    actOnFirst(pending.next)
  }, [settled, q, rows])

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => moveActive(i, e.key === 'ArrowDown' ? 1 : -1, rows.length))
    } else if (e.key === 'Enter') {
      if (isLink) return
      e.preventDefault()
      if (!settled) {
        pendingEnter.current = { q: query.trim(), next: e.shiftKey }
        return
      }
      const row = rows[active] ?? rows[0]
      if (row) act(row, e.shiftKey)
    } else if (e.key === 'Escape') {
      setQuery('')
    }
  }

  const activeRow = rows[active]
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
          role="combobox"
          aria-expanded={rows.length > 0}
          aria-controls="search-results"
          aria-activedescendant={activeRow ? `sr-${activeRow.key}` : undefined}
          aria-autocomplete="list"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
          }}
          onKeyDown={onKeyDown}
          placeholder="Трек, исполнитель или ссылка"
          className="focus-ring border-border bg-surface-2 h-11 w-full rounded-full border pr-12 pl-10"
        />
        <kbd className="border-border text-fg-subtle pointer-events-none absolute top-1/2 right-4 hidden -translate-y-1/2 rounded border px-1.5 text-xs sm:block">
          /
        </kbd>
      </label>

      {isLink && <LinkResults state={links} />}
      {!isLink && results.isPending && q.length > 0 && <SkeletonRows />}
      {results.error && (
        <p role="alert" className="text-bad text-sm">
          {results.error instanceof ApiError ? results.error.message : 'Поиск не удался.'}
        </p>
      )}
      {results.data && rows.length === 0 && !results.isFetching && !isLink && (
        <p className="text-fg-muted text-sm">Ничего не нашли.</p>
      )}
      {!q && (
        <p className="text-fg-subtle text-sm">
          Ищите по названию и исполнителю или вставьте ссылку Яндекс Музыки — можно Ctrl+V в любом
          месте страницы. ↑/↓ — выбор, Enter — в очередь, Shift+Enter — играть следующим.
        </p>
      )}

      <ul
        id="search-results"
        role="listbox"
        aria-label="Результаты поиска"
        data-testid="search-results"
        className="space-y-0.5"
      >
        {rows.map((row, i) => {
          const first = i === 0 || rows[i - 1]?.section !== row.section
          return (
            <li key={row.key} role="presentation">
              {first && (
                <p className="text-fg-subtle px-2 pt-3 pb-1 text-xs font-semibold tracking-wide uppercase">
                  {SECTION_TITLES[row.section]}
                </p>
              )}
              <ResultRow
                row={row}
                active={i === active}
                onAct={(next) => {
                  act(row, next)
                }}
                onHover={() => {
                  setActive(() => i)
                }}
              />
              {row.section === 'tracks' &&
                rows[i + 1]?.section !== 'tracks' &&
                !expanded &&
                (results.data?.tracks.length ?? 0) > 10 && (
                  <button
                    type="button"
                    className="text-accent focus-ring rounded px-2 py-1 text-sm hover:underline"
                    onClick={() => {
                      setNav({ q, active, expanded: true })
                    }}
                  >
                    Показать все треки
                  </button>
                )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function ResultRow({
  row,
  active,
  onAct,
  onHover,
}: {
  row: SearchRow
  active: boolean
  onAct: (next: boolean) => void
  onHover: () => void
}) {
  const base = `flex items-center gap-3 rounded-lg px-2 py-1.5 ${active ? 'bg-surface-3' : 'hover:bg-surface-2'}`
  if (row.kind === 'track') {
    return (
      <div
        id={`sr-${row.key}`}
        role="option"
        aria-selected={active}
        className={base}
        onMouseEnter={onHover}
      >
        <TrackInfo track={row.track} />
        <IconButton
          size="sm"
          label={`Играть «${row.track.title}» следующим`}
          onClick={() => {
            onAct(true)
          }}
        >
          <PlayNextIcon size={16} />
        </IconButton>
        <IconButton
          size="sm"
          label={`Добавить «${row.track.title}» в очередь`}
          onClick={() => {
            onAct(false)
          }}
        >
          <PlusIcon size={16} />
        </IconButton>
      </div>
    )
  }
  const { title, subtitle, cover, round } =
    row.kind === 'album'
      ? {
          title: row.album.title,
          subtitle: `Альбом · ${artistNames(row.album.artists)}${row.album.year ? ` · ${String(row.album.year)}` : ''}`,
          cover: row.album.coverUrl,
          round: false,
        }
      : row.kind === 'artist'
        ? {
            title: row.artist.name,
            subtitle: 'Исполнитель',
            cover: row.artist.coverUrl,
            round: true,
          }
        : {
            title: row.playlist.title,
            subtitle: `Плейлист${row.playlist.ownerName ? ` · ${row.playlist.ownerName}` : ''}`,
            cover: row.playlist.coverUrl,
            round: false,
          }
  return (
    <button
      type="button"
      id={`sr-${row.key}`}
      role="option"
      aria-selected={active}
      onClick={() => {
        onAct(false)
      }}
      onMouseEnter={onHover}
      className={`${base} focus-ring w-full text-left`}
    >
      <Cover
        url={cover}
        size="sm"
        className="size-10"
        rounded={round ? 'rounded-full' : 'rounded-md'}
      />
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

export function TrackInfo({ track }: { track: Track }) {
  return (
    <>
      <Cover url={track.coverUrl} size="sm" className="size-10" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{track.title}</p>
        <p className="text-fg-muted truncate text-xs">{artistNames(track.artists)}</p>
      </div>
      <span className="text-fg-subtle text-xs tabular-nums">{formatTime(track.durationMs)}</span>
    </>
  )
}

export function LinkResults({ state }: { state: UseQueryResult<ResolveResponse> }) {
  if (state.isFetching) return <SkeletonRows count={2} />
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

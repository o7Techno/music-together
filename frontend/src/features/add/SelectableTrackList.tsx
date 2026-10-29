// Список треков с выбором (SPEC §4.4): чекбоксы, «выбрать все», «добавить выбранные»,
// «добавить все перемешав». Недоступные треки показаны, но не выбираются.

import { useMemo, useState } from 'react'

import { useRoomStore } from '@/features/room/roomStore'
import { artistNames, formatTime, plural } from '@/shared/format'
import type { Track } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'

import { MAX_BATCH, type SourceKind, shuffled, useAddTracks } from './useAddTracks'

interface Props {
  tracks: Track[]
  source: { kind: SourceKind; title: string }
}

export function SelectableTrackList({ tracks, source }: Props) {
  const add = useAddTracks()
  const queue = useRoomStore((s) => s.queue)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const available = useMemo(() => tracks.filter((t) => t.available), [tracks])
  const queued = useMemo(() => {
    const ids = new Set<string>()
    if (queue?.current) ids.add(queue.current.track.id)
    for (const i of queue?.upcoming ?? []) ids.add(i.track.id)
    return ids
  }, [queue])

  const allSelected = available.length > 0 && available.every((t) => selected.has(t.id))
  const chosen = available.filter((t) => selected.has(t.id)).map((t) => t.id)
  const allIds = available.map((t) => t.id)

  const toggle = (id: string): void => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const toggleAll = (): void => {
    setSelected(allSelected ? new Set() : new Set(allIds))
  }
  const addAndReset = async (ids: string[], position: 'end' | 'next' = 'end'): Promise<void> => {
    if (await add(ids, { position, source })) setSelected(new Set())
  }

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="bg-surface-1 sticky top-0 z-10 flex flex-wrap items-center gap-2 py-1">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            disabled={available.length === 0}
            className="accent-[var(--c-accent)]"
          />
          Выбрать все
        </label>
        <div className="ml-auto flex flex-wrap gap-2">
          {chosen.length > 0 ? (
            <>
              <Button size="sm" variant="primary" onClick={() => void addAndReset(chosen)}>
                Добавить {chosen.length}
              </Button>
              <Button size="sm" onClick={() => void addAndReset(chosen, 'next')}>
                Следующими
              </Button>
            </>
          ) : (
            <>
              <Button
                size="sm"
                variant="primary"
                disabled={allIds.length === 0}
                onClick={() => void addAndReset(allIds)}
              >
                Добавить все
              </Button>
              <Button
                size="sm"
                disabled={allIds.length === 0}
                onClick={() => void addAndReset(shuffled(allIds))}
              >
                Все вперемешку
              </Button>
            </>
          )}
        </div>
      </div>
      {allIds.length > MAX_BATCH && (
        <p className="text-fg-subtle text-xs">
          За раз добавляется до {MAX_BATCH} треков — остальные можно добавить следующим действием.
        </p>
      )}
      <p className="text-fg-subtle text-xs">
        {available.length} {plural(available.length, 'трек', 'трека', 'треков')}
        {available.length < tracks.length &&
          ` · ${String(tracks.length - available.length)} недоступно`}
      </p>
      <ul className="space-y-0.5" data-testid="entity-tracks">
        {tracks.map((t, i) => (
          <li key={`${t.id}-${String(i)}`}>
            <label
              className={`hover:bg-surface-2 flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 ${
                t.available ? '' : 'cursor-not-allowed opacity-40'
              }`}
            >
              <input
                type="checkbox"
                checked={selected.has(t.id)}
                disabled={!t.available}
                onChange={() => {
                  toggle(t.id)
                }}
                aria-label={`Выбрать «${t.title}»`}
                className="accent-[var(--c-accent)]"
              />
              <Cover url={t.coverUrl} size="sm" className="size-9" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{t.title}</span>
                <span className="text-fg-muted block truncate text-xs">
                  {artistNames(t.artists)}
                  {!t.available && ' · недоступен'}
                </span>
              </span>
              {queued.has(t.id) && (
                <span className="text-warn shrink-0 text-xs" title="Уже в очереди">
                  в очереди
                </span>
              )}
              <span className="text-fg-subtle shrink-0 text-xs tabular-nums">
                {formatTime(t.durationMs)}
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}

import { TrackListCard } from '@/features/search/TrackListCard'
import type { ResolveResponse } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'

import { useAddTracks } from './useAddTracks'

/** Результаты разбора ссылок; для нескольких — ещё «Добавить всё» одним действием. */
export function LinkResultsView({
  data,
  onAdded,
}: {
  data: ResolveResponse
  onAdded?: () => void
}) {
  const add = useAddTracks()
  const allIds = data.items.flatMap((l) => l.tracks.filter((t) => t.available).map((t) => t.id))
  return (
    <div className="space-y-2">
      {data.items.length > 1 && allIds.length > 0 && (
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            void add(allIds, { source: { kind: 'link' } }).then((ok) => {
              if (ok) onAdded?.()
            })
          }}
        >
          Добавить всё ({allIds.length})
        </Button>
      )}
      {data.items.map((list) => (
        <TrackListCard key={`${list.kind}:${list.id}`} list={list} onAdded={onAdded} />
      ))}
      {data.failures.map((f) => (
        <p key={`${f.kind}:${f.id}`} className="text-warn text-sm">
          {f.message}
        </p>
      ))}
    </div>
  )
}

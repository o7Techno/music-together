// История сыгранного (последние 50) с возвратом трека в очередь (SPEC §4.3).

import { useAddTracks } from '@/features/add/useAddTracks'
import { useRoomStore } from '@/features/room/roomStore'
import { artistNames } from '@/shared/format'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { PlayNextIcon, PlusIcon } from '@/shared/ui/icons'

export function HistoryList() {
  const history = useRoomStore((s) => s.queue?.history ?? [])
  const add = useAddTracks()
  if (history.length === 0) {
    return <p className="text-fg-muted p-4 text-center text-sm">Пока ничего не сыграли.</p>
  }
  return (
    <ol className="max-h-[60vh] scrollbar-thin space-y-0.5 overflow-y-auto" data-testid="history">
      {history.map((item) => (
        <li
          key={item.id}
          className="hover:bg-surface-2 flex items-center gap-3 rounded-lg px-2 py-1.5"
        >
          <Cover url={item.track.coverUrl} size="sm" className="size-10 opacity-80" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm">{item.track.title}</p>
            <p className="text-fg-muted truncate text-xs">{artistNames(item.track.artists)}</p>
          </div>
          <IconButton
            size="sm"
            label={`«${item.track.title}» — следующим`}
            onClick={() => {
              void add([item.track.id], {
                position: 'next',
                source: { kind: 'history' },
                force: true,
              })
            }}
          >
            <PlayNextIcon size={16} />
          </IconButton>
          <IconButton
            size="sm"
            label={`Вернуть «${item.track.title}» в очередь`}
            onClick={() => {
              void add([item.track.id], { source: { kind: 'history' }, force: true })
            }}
          >
            <PlusIcon size={16} />
          </IconButton>
        </li>
      ))}
    </ol>
  )
}

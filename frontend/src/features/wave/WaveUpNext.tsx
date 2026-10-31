// «Дальше в волне» под ручной очередью: ближайшие треки, закрепить или убрать. Перетаскивания нет:
// буфер принадлежит серверу, а чтобы поставить трек в нужное место, его закрепляют.

import { Avatar } from '@/features/room/Members'
import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import { TrackActions } from '@/features/collection/TrackActions'
import { artistNames, formatTime } from '@/shared/format'
import type { QueueItem } from '@/shared/protocol/generated'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { CloseIcon, PinIcon } from '@/shared/ui/icons'

export function WaveUpNext() {
  const wave = useRoomStore((s) => s.wave)
  if (!wave || wave.status === 'off') return null
  return (
    <section aria-label="Дальше в волне" className="space-y-2">
      <h2 className="text-fg-muted text-sm font-semibold">Дальше в волне</h2>
      {wave.status === 'unavailable' && (
        <p role="status" className="text-warn text-sm">
          Волна временно недоступна — пробуем снова.
        </p>
      )}
      {wave.next.length === 0 && wave.status !== 'unavailable' && (
        <p className="text-fg-subtle text-sm">Подбираем треки…</p>
      )}
      <ol className="space-y-0.5" data-testid="wave-next">
        {wave.next.map((item) => (
          <WaveRow key={item.id} item={item} />
        ))}
      </ol>
    </section>
  )
}

function WaveRow({ item }: { item: QueueItem }) {
  const send = useCommand()
  const owner = useRoomStore((s) => s.members.find((m) => m.userId === item.origin.ownerId))
  const { track } = item
  return (
    <li className="group hover:bg-surface-2 flex items-center gap-3 rounded-lg px-2 py-1.5">
      <Cover url={track.coverUrl} size="sm" className="size-10 opacity-90" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{track.title}</p>
        <p className="text-fg-muted truncate text-xs">{artistNames(track.artists)}</p>
      </div>
      {owner && (
        <span title={`Из волны: ${owner.name}`}>
          <Avatar name={owner.name} url={owner.avatarUrl} className="size-5 text-[10px]" />
        </span>
      )}
      <span className="text-fg-subtle hidden shrink-0 text-xs tabular-nums sm:inline">
        {formatTime(track.durationMs)}
      </span>
      <div className="flex shrink-0 items-center opacity-100 transition-opacity lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100">
        <TrackActions track={track} />
        <IconButton
          size="sm"
          label={`Закрепить «${track.title}» в очереди`}
          onClick={() => void send({ type: 'wave.pin', itemId: item.id })}
        >
          <PinIcon size={16} />
        </IconButton>
        <IconButton
          size="sm"
          label={`Убрать «${track.title}» из волны`}
          onClick={() => void send({ type: 'wave.remove', itemId: item.id })}
        >
          <CloseIcon size={16} />
        </IconButton>
      </div>
    </li>
  )
}

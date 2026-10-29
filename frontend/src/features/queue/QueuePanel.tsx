import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import { artistNames, formatTime } from '@/shared/format'
import type { QueueItem } from '@/shared/protocol/generated'
import { IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { PlayIcon, TrashIcon } from '@/shared/ui/icons'

export function QueuePanel() {
  const queue = useRoomStore((s) => s.queue)
  const upcoming = queue?.upcoming ?? []
  return (
    <section aria-label="Очередь" className="flex min-h-0 flex-col gap-3">
      <h3 className="text-fg-muted text-sm font-semibold">Далее · {upcoming.length}</h3>
      {upcoming.length === 0 ? (
        <p className="border-border text-fg-muted rounded-xl border border-dashed p-6 text-center">
          Найдите трек или вставьте ссылку
        </p>
      ) : (
        <ol className="space-y-1" data-testid="queue">
          {upcoming.map((item, i) => (
            <QueueRow key={item.id} item={item} index={i} />
          ))}
        </ol>
      )}
    </section>
  )
}

function QueueRow({ item, index }: { item: QueueItem; index: number }) {
  const send = useCommand()
  const members = useRoomStore((s) => s.members)
  const addedBy = members.find((m) => m.userId === item.addedBy)?.name
  return (
    <li className="group hover:bg-surface-2 flex items-center gap-3 rounded-lg px-2 py-1.5">
      <span className="text-fg-subtle w-5 text-right text-xs tabular-nums">{index + 1}</span>
      <Cover url={item.track.coverUrl} size="sm" className="size-10" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{item.track.title}</p>
        <p className="text-fg-muted truncate text-xs">
          {artistNames(item.track.artists)}
          {addedBy && <span className="text-fg-subtle"> · {addedBy}</span>}
        </p>
      </div>
      <span className="text-fg-subtle text-xs tabular-nums">
        {formatTime(item.track.durationMs)}
      </span>
      <IconButton
        size="sm"
        label={`Играть «${item.track.title}» сейчас`}
        onClick={() => {
          void send({ type: 'cmd.play_item', queueItemId: item.id })
        }}
      >
        <PlayIcon size={16} />
      </IconButton>
      <IconButton
        size="sm"
        label={`Убрать «${item.track.title}» из очереди`}
        onClick={() => {
          void send({ type: 'queue.remove', itemId: item.id })
        }}
      >
        <TrashIcon size={16} />
      </IconButton>
    </li>
  )
}

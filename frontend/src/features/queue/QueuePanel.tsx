// Очередь (SPEC §4.3): drag-and-drop, виртуализация для сотен треков, «играть сейчас/следующим»,
// перемешать, очистить (с подтверждением), удалить (с «Отменить» 5 с), история.

import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useRef, useState } from 'react'

import { TrackActions } from '@/features/collection/TrackActions'
import { usePlaylistPicker } from '@/features/collection/playlistPicker'
import { useRoomSession } from '@/features/room/RoomContext'
import { Avatar } from '@/features/room/Members'
import { CommandError } from '@/features/room/roomSession'
import { optimisticQueue, useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import { WaveUpNext } from '@/features/wave/WaveUpNext'
import { artistNames, formatTime, plural } from '@/shared/format'
import type { QueueItem } from '@/shared/protocol/generated'
import { Button, IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import {
  GripIcon,
  HistoryIcon,
  PlayIcon,
  PlayNextIcon,
  ListPlusIcon,
  ShuffleIcon,
  TrashIcon,
} from '@/shared/ui/icons'
import { toast } from '@/shared/ui/Toaster'

import { HistoryList } from './HistoryList'

const ROW_HEIGHT = 56
const UNDO_MS = 5000

function useQueueActions() {
  const session = useRoomSession()
  const send = useCommand()

  const remove = (item: QueueItem, index: number): void => {
    const rollback = optimisticQueue((q) => ({
      ...q,
      upcoming: q.upcoming.filter((i) => i.id !== item.id),
    }))
    session
      .command({ type: 'queue.remove', itemId: item.id })
      .then(() => {
        toast.withAction(
          `Убрали «${item.track.title}»`,
          'Отменить',
          () => {
            void send({
              type: 'queue.add',
              trackIds: [item.track.id],
              index,
              source: { kind: 'undo', title: null },
            })
          },
          UNDO_MS,
        )
      })
      .catch((err: unknown) => {
        rollback()
        if (err instanceof CommandError) toast.error(err.message)
      })
  }

  const move = (itemId: string, from: number, to: number): void => {
    if (from === to) return
    const rollback = optimisticQueue((q) => ({ ...q, upcoming: arrayMove(q.upcoming, from, to) }))
    session.command({ type: 'queue.move', itemId, toIndex: to }).catch((err: unknown) => {
      rollback()
      if (err instanceof CommandError) toast.error(err.message)
    })
  }

  return {
    remove,
    move,
    playNow: (item: QueueItem) => void send({ type: 'cmd.play_item', queueItemId: item.id }),
  }
}

export function QueuePanel() {
  const upcoming = useRoomStore((s) => s.queue?.upcoming ?? [])
  const historyCount = useRoomStore((s) => s.queue?.history.length ?? 0)
  const send = useCommand()
  const waveOn = useRoomStore((s) => s.wave !== null && s.wave.status !== 'off')
  const openPicker = usePlaylistPicker((s) => s.open)
  const [showHistory, setShowHistory] = useState(false)
  const confirm = useRef<HTMLDialogElement>(null)
  const totalMs = upcoming.reduce((sum, i) => sum + i.track.durationMs, 0)

  return (
    <section aria-label="Очередь" className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center gap-2">
        <h2 className="text-fg-muted text-sm font-semibold">
          {showHistory ? 'История' : 'Далее'}
          {!showHistory && upcoming.length > 0 && (
            <span className="text-fg-subtle font-normal">
              {' '}
              · {upcoming.length} {plural(upcoming.length, 'трек', 'трека', 'треков')} ·{' '}
              {formatTime(totalMs)}
            </span>
          )}
        </h2>
        <div className="ml-auto flex items-center">
          {!showHistory && upcoming.length > 0 && (
            <IconButton
              size="sm"
              label="Сохранить очередь в плейлист"
              onClick={() => {
                openPicker({ trackIds: upcoming.map((i) => i.track.id), title: 'Вся очередь' })
              }}
            >
              <ListPlusIcon size={16} />
            </IconButton>
          )}
          {showHistory && historyCount > 0 && (
            <IconButton
              size="sm"
              label="Сохранить историю в плейлист"
              onClick={() => {
                const history = useRoomStore.getState().queue?.history ?? []
                openPicker({
                  trackIds: history.map((i) => i.track.id),
                  title: 'История комнаты: последние треки',
                })
              }}
            >
              <ListPlusIcon size={16} />
            </IconButton>
          )}
          {!showHistory && upcoming.length > 1 && (
            <IconButton
              size="sm"
              label="Перемешать оставшиеся"
              onClick={() => void send({ type: 'queue.shuffle' })}
            >
              <ShuffleIcon size={16} />
            </IconButton>
          )}
          {!showHistory && upcoming.length > 0 && (
            <IconButton
              size="sm"
              label="Очистить очередь"
              onClick={() => confirm.current?.showModal()}
            >
              <TrashIcon size={16} />
            </IconButton>
          )}
          <IconButton
            size="sm"
            label={showHistory ? 'Показать очередь' : `История (${String(historyCount)})`}
            active={showHistory}
            onClick={() => {
              setShowHistory((v) => !v)
            }}
          >
            <HistoryIcon size={16} />
          </IconButton>
        </div>
      </div>

      {showHistory ? (
        <HistoryList />
      ) : upcoming.length === 0 ? (
        !waveOn && (
          <p className="border-border text-fg-muted rounded-xl border border-dashed p-6 text-center">
            Найдите трек или вставьте ссылку
          </p>
        )
      ) : (
        <SortableQueue items={upcoming} />
      )}

      {!showHistory && <WaveUpNext />}

      <dialog
        ref={confirm}
        aria-label="Очистить очередь"
        className="bg-surface-1 text-fg m-auto w-[min(24rem,calc(100vw-2rem))] rounded-2xl p-5 shadow-2xl backdrop:bg-black/60"
      >
        <p className="font-semibold">Очистить очередь?</p>
        <p className="text-fg-muted mt-1 text-sm">
          Уберём {upcoming.length} {plural(upcoming.length, 'трек', 'трека', 'треков')}. Текущий
          трек доиграет.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => confirm.current?.close()}>
            Отмена
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              confirm.current?.close()
              void send({ type: 'queue.clear' })
            }}
          >
            Очистить
          </Button>
        </div>
      </dialog>
    </section>
  )
}

function SortableQueue({ items }: { items: QueueItem[] }) {
  const actions = useQueueActions()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState<QueueItem | null>(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  // eslint-disable-next-line react-hooks/incompatible-library -- useVirtualizer возвращает функции, это ожидаемо
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
    getItemKey: (i) => items[i]?.id ?? i,
  })

  const onDragStart = (e: DragStartEvent): void => {
    setDragging(items.find((i) => i.id === e.active.id) ?? null)
  }
  const onDragEnd = (e: DragEndEvent): void => {
    setDragging(null)
    if (!e.over || e.active.id === e.over.id) return
    const from = items.findIndex((i) => i.id === e.active.id)
    const to = items.findIndex((i) => i.id === e.over?.id)
    if (from >= 0 && to >= 0) actions.move(String(e.active.id), from, to)
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => {
        setDragging(null)
      }}
    >
      <SortableContext items={items.map((i) => i.id)} strategy={verticalListSortingStrategy}>
        <div
          ref={scrollRef}
          className="max-h-[60vh] scrollbar-thin overflow-y-auto lg:max-h-[calc(100dvh-22rem)]"
        >
          <ol
            data-testid="queue"
            className="relative"
            style={{ height: `${String(virtualizer.getTotalSize())}px` }}
          >
            {virtualizer.getVirtualItems().map((v) => {
              const item = items[v.index]
              if (!item) return null
              return (
                <SortableRow
                  key={item.id}
                  item={item}
                  index={v.index}
                  top={v.start}
                  actions={actions}
                />
              )
            })}
          </ol>
        </div>
      </SortableContext>
      <DragOverlay>
        {dragging && (
          <div className="bg-surface-3 rounded-lg shadow-2xl">
            <RowContent item={dragging} index={items.indexOf(dragging)} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  )
}

function SortableRow({
  item,
  index,
  top,
  actions,
}: {
  item: QueueItem
  index: number
  top: number
  actions: ReturnType<typeof useQueueActions>
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id })
  return (
    <li
      ref={setNodeRef}
      className={`group hover:bg-surface-2 absolute inset-x-0 flex items-center rounded-lg ${
        isDragging ? 'opacity-30' : ''
      }`}
      style={{
        top: `${String(top)}px`,
        height: `${String(ROW_HEIGHT)}px`,
        transform: CSS.Transform.toString(transform),
        transition,
      }}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        aria-label={`Перетащить «${item.track.title}»`}
        className="focus-ring text-fg-subtle hover:text-fg cursor-grab touch-none rounded px-1 active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripIcon size={16} />
      </button>
      <RowContent item={item} index={index} />
      <div className="flex shrink-0 items-center opacity-100 transition-opacity lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100">
        <TrackActions track={item.track} />
        <IconButton
          size="sm"
          label={`Играть «${item.track.title}» сейчас`}
          onClick={() => {
            actions.playNow(item)
          }}
        >
          <PlayIcon size={16} />
        </IconButton>
        {/* У первой строки кнопка скрыта, но место занимает: иначе колонки строк разъедутся. */}
        <IconButton
          size="sm"
          className={index === 0 ? 'invisible' : ''}
          label={`«${item.track.title}» — следующим`}
          onClick={() => {
            actions.move(item.id, index, 0)
          }}
        >
          <PlayNextIcon size={16} />
        </IconButton>
        <IconButton
          size="sm"
          label={`Убрать «${item.track.title}» из очереди`}
          onClick={() => {
            actions.remove(item, index)
          }}
        >
          <TrashIcon size={16} />
        </IconButton>
      </div>
    </li>
  )
}

function RowContent({ item, index }: { item: QueueItem; index: number }) {
  const addedBy = useRoomStore((s) => s.members.find((m) => m.userId === item.addedBy))
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3 px-2 py-1.5">
      <span className="text-fg-subtle w-5 shrink-0 text-right text-xs tabular-nums">
        {index + 1}
      </span>
      <Cover url={item.track.coverUrl} size="sm" className="size-10" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{item.track.title}</p>
        <p className="text-fg-muted truncate text-xs">{artistNames(item.track.artists)}</p>
      </div>
      {addedBy && (
        <span title={`Добавил(а): ${addedBy.name}`}>
          <Avatar name={addedBy.name} url={addedBy.avatarUrl} className="size-5 text-[10px]" />
        </span>
      )}
      <span className="text-fg-subtle shrink-0 text-xs tabular-nums">
        {formatTime(item.track.durationMs)}
      </span>
    </div>
  )
}

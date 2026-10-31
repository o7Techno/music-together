// Откуда текущий трек: «Моя волна · Аня», «Волна по: Radiohead», «Добавил Петя».

import { useRoomStore } from '@/features/room/roomStore'
import type { QueueItem } from '@/shared/protocol/generated'

function sourceLabel(item: QueueItem, addedByName: string | undefined): string | null {
  const { origin } = item
  if (origin.kind === 'wave') {
    if (origin.shared) return `Общая волна · ${origin.ownerName ?? ''}`
    if (origin.seedLabel) return `Волна по: ${origin.seedLabel}`
    return origin.ownerName ? `Моя волна · ${origin.ownerName}` : 'Моя волна'
  }
  return addedByName ? `Добавил(а) ${addedByName}` : null
}

export function WaveBadge({ className = '' }: { className?: string }) {
  const current = useRoomStore((s) => s.queue?.current ?? null)
  const addedBy = useRoomStore((s) => s.members.find((m) => m.userId === current?.addedBy)?.name)
  if (!current) return null
  const label = sourceLabel(current, addedBy)
  if (!label) return null
  return (
    <p
      data-testid="track-source"
      className={`truncate text-xs ${
        current.origin.kind === 'wave' ? 'text-accent font-medium' : 'text-fg-subtle'
      } ${className}`}
    >
      {label}
    </p>
  )
}

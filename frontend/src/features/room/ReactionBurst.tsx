// Реакции на трек всплывают над обложкой на пару секунд.

import { useEffect, useState } from 'react'

import { useRoomStore } from './roomStore'

const SHOW_MS = 2500

interface Burst {
  id: string
  emoji: string
  left: number
}

export function ReactionBurst() {
  const [bursts, setBursts] = useState<Burst[]>([])
  useEffect(
    () =>
      useRoomStore.subscribe((state, prev) => {
        if (state.chat === prev.chat) return
        const known = new Set(prev.chat.map((m) => m.id))
        const fresh = state.chat.filter(
          (m) => m.emoji && !known.has(m.id) && Date.now() - m.atMs < SHOW_MS,
        )
        if (fresh.length === 0) return
        const added = fresh.map((m) => ({
          id: m.id,
          emoji: m.emoji ?? '',
          left: 10 + ((m.id.charCodeAt(0) * 37) % 70),
        }))
        setBursts((b) => [...b, ...added].slice(-12))
        window.setTimeout(() => {
          setBursts((b) => b.filter((x) => !added.some((a) => a.id === x.id)))
        }, SHOW_MS)
      }),
    [],
  )
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-10 overflow-hidden">
      {bursts.map((b) => (
        <span
          key={b.id}
          className="animate-float-up absolute bottom-2 text-3xl"
          style={{ left: `${String(b.left)}%` }}
        >
          {b.emoji}
        </span>
      ))}
    </div>
  )
}

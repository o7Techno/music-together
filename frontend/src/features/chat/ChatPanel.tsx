// Чат комнаты и реакции на текущий трек (SPEC §4.6). История на сервере — не дольше суток.

import { type SyntheticEvent, useEffect, useRef, useState } from 'react'

import { Avatar } from '@/features/room/Members'
import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import type { ChatMessage } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'

export const REACTIONS = ['👍', '❤️', '🔥', '😂', '😮', '👏'] as const

function time(ms: number): string {
  return new Date(ms).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export function ReactionBar() {
  const send = useCommand()
  const hasTrack = useRoomStore((s) => Boolean(s.playback?.trackId))
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Реакции на трек">
      {REACTIONS.map((emoji) => (
        <button
          key={emoji}
          type="button"
          disabled={!hasTrack}
          onClick={() => void send({ type: 'chat.react', emoji })}
          aria-label={`Реакция ${emoji}`}
          className="focus-ring hover:bg-surface-3 rounded-full px-2 py-1 text-lg transition-transform active:scale-125 disabled:opacity-40"
        >
          {emoji}
        </button>
      ))}
    </div>
  )
}

export function ChatPanel() {
  const chat = useRoomStore((s) => s.chat)
  const selfId = useRoomStore((s) => s.selfUserId)
  const members = useRoomStore((s) => s.members)
  const send = useCommand()
  const [text, setText] = useState('')
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    const el = list.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chat.length])

  const submit = async (e: SyntheticEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault()
    const value = text.trim()
    if (!value) return
    setText('')
    if (!(await send({ type: 'chat.send', text: value }))) setText(value)
  }

  return (
    <section aria-label="Чат" className="flex min-h-0 flex-col gap-2">
      <ReactionBar />
      <ol
        ref={list}
        className="max-h-72 min-h-24 scrollbar-thin space-y-2 overflow-y-auto pr-1"
        data-testid="chat"
        aria-live="polite"
      >
        {chat.length === 0 && (
          <li className="text-fg-subtle text-sm">Напишите что-нибудь — история хранится сутки.</li>
        )}
        {chat.map((m) => (
          <ChatLine
            key={m.id}
            message={m}
            mine={m.userId === selfId}
            avatar={members.find((x) => x.userId === m.userId)?.avatarUrl ?? null}
          />
        ))}
      </ol>
      <form onSubmit={(e) => void submit(e)} className="flex gap-2">
        <input
          value={text}
          onChange={(e) => {
            setText(e.target.value)
          }}
          maxLength={500}
          placeholder="Сообщение"
          aria-label="Сообщение в чат"
          className="focus-ring border-border bg-surface-2 h-10 min-w-0 flex-1 rounded-full border px-4"
        />
        <Button type="submit" size="md" disabled={!text.trim()}>
          Отправить
        </Button>
      </form>
    </section>
  )
}

function ChatLine({
  message: m,
  mine,
  avatar,
}: {
  message: ChatMessage
  mine: boolean
  avatar: string | null
}) {
  if (m.emoji) {
    return (
      <li className="text-fg-muted flex items-center gap-2 text-sm">
        <span className="text-xl" aria-hidden="true">
          {m.emoji}
        </span>
        <span>
          {m.userName} реагирует на трек <span className="sr-only">{m.emoji}</span>
        </span>
        <time className="text-fg-subtle ml-auto text-xs">{time(m.atMs)}</time>
      </li>
    )
  }
  return (
    <li className={`flex items-start gap-2 ${mine ? 'flex-row-reverse' : ''}`}>
      <Avatar name={m.userName} url={avatar} className="size-7" />
      <div
        className={`max-w-[80%] rounded-2xl px-3 py-1.5 text-sm ${
          mine ? 'bg-accent text-black' : 'bg-surface-3'
        }`}
      >
        {!mine && <p className="text-fg-muted text-xs font-medium">{m.userName}</p>}
        <p className="break-words whitespace-pre-wrap">{m.text}</p>
      </div>
      <time className="text-fg-subtle self-end text-[10px]">{time(m.atMs)}</time>
    </li>
  )
}

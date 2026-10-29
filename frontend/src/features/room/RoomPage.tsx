import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useMe } from '@/features/auth/useAuth'
import { LoginCard } from '@/features/auth/LoginCard'
import { QueuePanel } from '@/features/queue/QueuePanel'
import { SearchPanel } from '@/features/search/SearchPanel'
import { eventText, isToastWorthy } from '@/shared/format'
import { CLOSE_FORBIDDEN, CLOSE_NOT_FOUND, CLOSE_UNAUTHORIZED } from '@/shared/roomSocket'
import { Button } from '@/shared/ui/Button'
import { FullScreenSpinner } from '@/shared/ui/Spinner'
import { toast } from '@/shared/ui/Toaster'

import { DebugPanel } from './DebugPanel'
import { EventFeed } from './EventFeed'
import { Members } from './Members'
import { Player } from './Player'
import { RoomContext, useRoomSession } from './RoomContext'
import type { RoomSession } from './roomSession'
import { useRoomStore } from './roomStore'
import { closeRoom, openRoom, useSessionStore } from './sessionStore'

export default function RoomPage() {
  const { slug = '' } = useParams()
  const me = useMe()
  if (me.isPending) return <FullScreenSpinner />
  if (!me.data) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-6 p-4">
        <h1 className="text-2xl font-semibold">Вас пригласили послушать музыку вместе</h1>
        <LoginCard />
      </main>
    )
  }
  return <Room slug={slug} key={slug} />
}

function useSession(slug: string): RoomSession | null {
  useEffect(() => {
    openRoom(slug)
    return () => {
      closeRoom()
    }
  }, [slug])
  return useSessionStore((s) => s.session)
}

function Room({ slug }: { slug: string }) {
  const session = useSession(slug)
  const [debug, setDebug] = useState(() => new URLSearchParams(window.location.search).has('debug'))

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key === 'd' || e.key === 'D' || e.key === 'в' || e.key === 'В') setDebug((v) => !v)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  useToastsForOthers()

  if (!session) return <FullScreenSpinner />
  return (
    <RoomContext.Provider value={session}>
      <RoomLayout />
      {debug && (
        <DebugPanel
          onClose={() => {
            setDebug(false)
          }}
        />
      )}
    </RoomContext.Provider>
  )
}

/** Критичные действия других участников — коротким тостом. */
function useToastsForOthers(): void {
  useEffect(() => {
    let lastId: string | null = null
    return useRoomStore.subscribe((state, prev) => {
      if (state.events === prev.events || prev.events.length === 0) return
      const e = state.events.at(-1)
      if (!e || e.id === lastId) return
      lastId = e.id
      if (e.userId !== state.selfUserId && isToastWorthy(e)) toast.info(eventText(e))
    })
  }, [])
}

function RoomLayout() {
  const room = useRoomStore((s) => s.room)
  const status = useRoomStore((s) => s.status)
  const terminal = useRoomStore((s) => s.terminalCode)
  const audioUnlocked = useRoomStore((s) => s.audioUnlocked)

  if (terminal !== null) return <Terminal code={terminal} />
  if (!room) return <FullScreenSpinner />

  return (
    <div className="mx-auto flex min-h-dvh max-w-7xl flex-col gap-4 p-3 sm:p-4">
      <header className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/"
            className="focus-ring text-fg-muted hover:text-fg rounded"
            aria-label="На главную"
          >
            ←
          </Link>
          <h1 className="truncate text-lg font-semibold">{room.name}</h1>
          <ConnectionDot status={status} />
        </div>
        <InviteButton slug={room.slug} />
      </header>

      {!audioUnlocked && <UnlockBanner />}

      <div className="grid flex-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)_360px]">
        <div className="bg-surface-1 space-y-6 rounded-2xl p-4">
          <Player />
          <Members />
        </div>
        <div className="bg-surface-1 min-h-0 space-y-6 rounded-2xl p-4">
          <QueuePanel />
          <EventFeed />
        </div>
        <div className="bg-surface-1 min-h-0 rounded-2xl p-4">
          <SearchPanel />
        </div>
      </div>
    </div>
  )
}

function ConnectionDot({ status }: { status: string }) {
  const sync = useRoomStore((s) => s.sync)
  const offline = status !== 'open'
  const tone = offline
    ? 'bg-bad'
    : sync === 'catching_up' || sync === 'buffering'
      ? 'bg-warn'
      : sync === 'unstable'
        ? 'bg-bad'
        : 'bg-ok'
  const label = offline
    ? 'Нет связи — переподключаемся'
    : sync === 'in_sync'
      ? 'В синхроне'
      : sync === 'catching_up'
        ? 'Догоняем'
        : sync === 'buffering'
          ? 'Буферизация'
          : sync === 'unstable'
            ? 'Синхрон нестабилен'
            : 'На связи'
  return (
    <span
      className="text-fg-subtle flex items-center gap-1.5 text-xs"
      role="status"
      data-testid="connection"
    >
      <span className={`size-2 rounded-full ${tone}`} />
      <span className="hidden sm:inline">{label}</span>
    </span>
  )
}

function UnlockBanner() {
  const session = useRoomSession()
  return (
    <div className="border-accent/40 bg-accent/10 flex flex-col items-center gap-3 rounded-2xl border p-4 text-center sm:flex-row sm:text-left">
      <p className="flex-1">Браузер не даёт сайтам включать звук без вашего разрешения.</p>
      <Button
        variant="primary"
        size="lg"
        onClick={() => {
          session.unlockAudio()
        }}
        data-testid="unlock"
      >
        Включить звук
      </Button>
    </div>
  )
}

function InviteButton({ slug }: { slug: string }) {
  const share = async (): Promise<void> => {
    const url = `${window.location.origin}/r/${slug}`
    if (typeof navigator.share === 'function' && window.matchMedia('(pointer: coarse)').matches) {
      try {
        await navigator.share({ title: 'Слушаем вместе', url })
        return
      } catch {
        /* отменили — скопируем */
      }
    }
    try {
      await navigator.clipboard.writeText(url)
      toast.success('Ссылка скопирована')
    } catch {
      toast.info(url)
    }
  }
  return (
    <Button variant="secondary" size="sm" onClick={() => void share()}>
      Пригласить
    </Button>
  )
}

function Terminal({ code }: { code: number }) {
  const text =
    code === CLOSE_NOT_FOUND
      ? 'Комната не найдена — возможно, её удалили или перевыпустили ссылку.'
      : code === CLOSE_FORBIDDEN
        ? 'Создатель комнаты закрыл вам доступ.'
        : code === CLOSE_UNAUTHORIZED
          ? 'Нужно войти заново.'
          : 'Соединение закрыто.'
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-lg">{text}</p>
      <Link to="/" className="text-accent hover:underline">
        На главную
      </Link>
    </main>
  )
}

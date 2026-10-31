import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { AccountNotice } from '@/features/auth/AccountNotice'
import { useMe } from '@/features/auth/useAuth'
import { LoginCard } from '@/features/auth/LoginCard'
import { PlaylistDialog } from '@/features/collection/PlaylistDialog'
import { QueuePanel } from '@/features/queue/QueuePanel'
import { AddPanel } from '@/features/add/AddPanel'
import { useAddNav } from '@/features/add/addNav'
import { PasteDrop } from '@/features/add/PasteDrop'
import { eventText, isToastWorthy } from '@/shared/format'
import { CLOSE_FORBIDDEN, CLOSE_NOT_FOUND, CLOSE_UNAUTHORIZED } from '@/shared/roomSocket'
import { Button } from '@/shared/ui/Button'
import { FullScreenSpinner } from '@/shared/ui/Spinner'
import { toast } from '@/shared/ui/Toaster'

import { ChatPanel } from '@/features/chat/ChatPanel'
import { useIsDesktop } from '@/shared/useMediaQuery'
import { ThemeToggle } from '@/shared/ui/ThemeToggle'

import { DebugPanel } from './DebugPanel'
import { EventFeed } from './EventFeed'
import { Members } from './Members'
import { MiniPlayer } from './MiniPlayer'
import { Player } from './Player'
import { RoomContext, useRoomSession } from './RoomContext'
import { RoomSettingsButton } from './RoomSettings'
import type { RoomSession } from './roomSession'
import { useRoomStore } from './roomStore'
import { closeRoom, openRoom, useSessionStore } from './sessionStore'
import { useMediaSession } from './useMediaSession'
import { usePlayerHotkeys } from './usePlayerHotkeys'

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
      if (
        (e.ctrlKey || e.metaKey) &&
        (e.key === 'k' || e.key === 'K' || e.key === 'л' || e.key === 'Л')
      ) {
        e.preventDefault()
        focusSearch()
        return
      }
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      if (e.key === '/' || e.key === '.') {
        // «/» на русской раскладке — это «.» на той же клавише.
        e.preventDefault()
        focusSearch()
        return
      }
      if (e.key === 'd' || e.key === 'D' || e.key === 'в' || e.key === 'В') setDebug((v) => !v)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  useToastsForOthers()
  useEffect(() => {
    useAddNav.getState().reset()
  }, [slug])

  if (!session) return <FullScreenSpinner />
  return (
    <RoomContext.Provider value={session}>
      <RoomLayout />
      <PasteDrop />
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

function focusSearch(): void {
  useAddNav.getState().setTab('search')
  // Поле поиска всегда смонтировано (скрыто при других вкладках) — фокус после перерисовки.
  requestAnimationFrame(() => {
    document.querySelector<HTMLInputElement>('[data-search-input]')?.focus()
  })
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

type MobileTab = 'queue' | 'add' | 'people' | 'chat'

const MOBILE_TABS: { id: MobileTab; label: string; icon: string }[] = [
  { id: 'queue', label: 'Очередь', icon: '☰' },
  { id: 'add', label: 'Добавить', icon: '+' },
  { id: 'people', label: 'Люди', icon: '👥' },
  { id: 'chat', label: 'Чат', icon: '💬' },
]

function RoomLayout() {
  const room = useRoomStore((s) => s.room)
  const status = useRoomStore((s) => s.status)
  const terminal = useRoomStore((s) => s.terminalCode)
  const audioUnlocked = useRoomStore((s) => s.audioUnlocked)
  const desktop = useIsDesktop()
  const [tab, setTab] = useState<MobileTab>('queue')
  const [playerOpen, setPlayerOpen] = useState(false)
  usePlayerHotkeys()
  useMediaSession()

  if (terminal !== null) return <Terminal code={terminal} />
  if (!room) return <FullScreenSpinner />
  const visible = (t: MobileTab): string => (tab === t ? 'block' : 'hidden')

  return (
    <div className="mx-auto flex min-h-dvh max-w-7xl flex-col gap-3 p-3 pb-40 sm:p-4 lg:pb-4">
      <header className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            to="/"
            className="focus-ring text-fg-muted hover:text-fg flex size-9 shrink-0 items-center justify-center rounded-full"
            aria-label="На главную"
          >
            ←
          </Link>
          <h1 className="truncate text-lg font-semibold">{room.name}</h1>
          <ConnectionDot status={status} />
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <ThemeToggle />
          <RoomSettingsButton />
          <InviteButton slug={room.slug} />
        </div>
      </header>

      <MeNotice />
      <PlaylistDialog />
      {!audioUnlocked && <UnlockBanner />}

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)_380px]">
        <aside
          className={`bg-surface-1 space-y-6 rounded-2xl p-4 lg:block ${visible('people')}`}
          aria-label="Плеер и участники"
        >
          {desktop && <Player />}
          <Members />
        </aside>
        <main
          className={`bg-surface-1 min-h-0 space-y-6 rounded-2xl p-4 lg:block ${visible('queue')}`}
        >
          <QueuePanel />
          {desktop ? <FeedAndChat /> : <EventFeed />}
        </main>
        <section
          aria-label="Добавить треки"
          className={`bg-surface-1 min-h-0 rounded-2xl p-4 lg:block ${visible('add')}`}
        >
          <AddPanel />
        </section>
        {!desktop && (
          <section aria-label="Чат" className={`bg-surface-1 rounded-2xl p-4 ${visible('chat')}`}>
            <ChatPanel />
          </section>
        )}
      </div>

      {!desktop && (
        <div className="fixed inset-x-0 bottom-0 z-30 pb-[env(safe-area-inset-bottom)]">
          <MiniPlayer
            onExpand={() => {
              setPlayerOpen(true)
            }}
          />
          <nav
            aria-label="Разделы комнаты"
            className="bg-surface-1 border-border grid grid-cols-4 border-t"
          >
            {MOBILE_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-current={tab === t.id ? 'page' : undefined}
                onClick={() => {
                  setTab(t.id)
                }}
                className={`focus-ring flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs ${
                  tab === t.id ? 'text-accent' : 'text-fg-muted'
                }`}
              >
                <span aria-hidden="true" className="text-lg leading-none">
                  {t.icon}
                </span>
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      )}
      {!desktop && playerOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Плеер"
          className="bg-surface-0 animate-sheet-in fixed inset-0 z-40 overflow-y-auto p-5 pt-[max(1.25rem,env(safe-area-inset-top))]"
        >
          <button
            type="button"
            onClick={() => {
              setPlayerOpen(false)
            }}
            className="focus-ring text-fg-muted mx-auto mb-4 block rounded-full px-4 py-1"
            aria-label="Свернуть плеер"
          >
            ⌄
          </button>
          <div className="mx-auto max-w-md">
            <Player />
          </div>
        </div>
      )}
    </div>
  )
}

function FeedAndChat() {
  const [view, setView] = useState<'feed' | 'chat'>('feed')
  const unread = useRoomStore((s) => s.chat.length)
  return (
    <div className="space-y-3">
      <div role="tablist" aria-label="Лента и чат" className="flex gap-4 text-sm">
        {(
          [
            ['feed', 'Лента'],
            ['chat', `Чат${unread ? ` · ${String(unread)}` : ''}`],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            onClick={() => {
              setView(id)
            }}
            className={`focus-ring rounded pb-1 font-semibold ${
              view === id ? 'text-fg border-accent border-b-2' : 'text-fg-muted'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {view === 'feed' ? <EventFeed /> : <ChatPanel />}
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

function MeNotice() {
  const me = useMe()
  return me.data ? <AccountNotice me={me.data} /> : null
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

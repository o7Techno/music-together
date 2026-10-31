// Добавление в плейлист (SPEC-wave §6.2): поиск, недавние сверху, создание нового, вопрос про
// дубликат, а для одного трека — ещё и лайк: на телефоне это единственное действие в строке.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type SyntheticEvent, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, api } from '@/shared/api'
import { plural } from '@/shared/format'
import type { PlaylistSummary } from '@/shared/protocol/generated'
import { Button, IconButton } from '@/shared/ui/Button'
import { Cover } from '@/shared/ui/Cover'
import { CloseIcon, HeartIcon } from '@/shared/ui/icons'
import { toast } from '@/shared/ui/Toaster'

import { type PlaylistTarget, usePlaylistPicker } from './playlistPicker'
import { useLikedIds, useToggleLike } from './useLikes'

const RECENT_KEY = 'mt.recentPlaylists'
const RECENT_LIMIT = 5
const LINK_TOAST_MS = 6000
const PLAYLISTS_KEY = ['my-playlists-editable']

function readRecent(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
  } catch {
    return []
  }
}

function rememberRecent(ref: string): void {
  try {
    const next = [ref, ...readRecent().filter((r) => r !== ref)].slice(0, RECENT_LIMIT)
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    /* без запоминания */
  }
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Не получилось. Попробуйте ещё раз.'
}

function done(playlist: PlaylistSummary): void {
  const message = `Добавлено в «${playlist.title}»`
  const url = playlist.externalUrl
  if (url) {
    toast.withAction(
      message,
      'Открыть в Яндекс Музыке',
      () => {
        window.open(url, '_blank', 'noopener,noreferrer')
      },
      LINK_TOAST_MS,
    )
  } else {
    toast.success(message)
  }
}

export function PlaylistDialog() {
  const target = usePlaylistPicker((s) => s.target)
  const close = usePlaylistPicker((s) => s.close)
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = dialog.current
    if (!el) return
    if (target && !el.open) el.showModal()
    if (!target && el.open) el.close()
  }, [target])

  return (
    <dialog
      ref={dialog}
      aria-label="Добавить в плейлист"
      onClose={close}
      className="bg-surface-1 text-fg m-auto w-[min(26rem,calc(100vw-2rem))] rounded-2xl p-0 shadow-2xl backdrop:bg-black/60"
    >
      {target && <PickerBody key={target.trackIds.join()} target={target} onClose={close} />}
    </dialog>
  )
}

function PickerBody({ target, onClose }: { target: PlaylistTarget; onClose: () => void }) {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [duplicate, setDuplicate] = useState<PlaylistSummary | null>(null)
  const [recent] = useState(readRecent)
  const playlists = useQuery({
    queryKey: PLAYLISTS_KEY,
    queryFn: async () => (await api.myPlaylists()).filter((p) => p.editable),
    staleTime: 60_000,
  })

  const invalidate = (): void => {
    void qc.invalidateQueries({ queryKey: PLAYLISTS_KEY })
    void qc.invalidateQueries({ queryKey: ['my-playlists'] })
    void qc.invalidateQueries({ queryKey: ['entity', 'playlist'] })
  }

  const add = useMutation({
    mutationFn: (v: { playlist: PlaylistSummary; allowDuplicate: boolean }) =>
      api.addToPlaylist(v.playlist.ref, target.trackIds, v.allowDuplicate),
    onSuccess: (playlist) => {
      rememberRecent(playlist.ref)
      invalidate()
      done(playlist)
      onClose()
    },
    onError: (err, v) => {
      if (err instanceof ApiError && err.code === 'duplicate') setDuplicate(v.playlist)
      else toast.error(errorText(err))
    },
  })

  const remove = useMutation({
    mutationFn: (playlist: PlaylistSummary) => {
      const trackId = target.trackIds[0]
      if (trackId === undefined) throw new Error('no track')
      return api.removeFromPlaylist(playlist.ref, trackId)
    },
    onSuccess: (playlist) => {
      invalidate()
      toast.success(`Убрано из «${playlist.title}»`)
      onClose()
    },
    onError: (err) => toast.error(errorText(err)),
  })

  const create = useMutation({
    mutationFn: (title: string) => api.createPlaylist(title),
    onSuccess: (playlist) => {
      add.mutate({ playlist, allowDuplicate: false })
    },
    onError: (err) => toast.error(errorText(err)),
  })

  const shown = useMemo(() => {
    const query = search.trim().toLowerCase()
    const rank = (p: PlaylistSummary): number => {
      const index = recent.indexOf(p.ref)
      return index === -1 ? RECENT_LIMIT : index
    }
    return (playlists.data ?? [])
      .filter((p) => p.title.toLowerCase().includes(query))
      .sort((a, b) => rank(a) - rank(b))
  }, [playlists.data, search, recent])

  const submitNew = (e: SyntheticEvent<HTMLFormElement>): void => {
    e.preventDefault()
    const title = newTitle.trim()
    if (title) create.mutate(title)
  }

  const busy = add.isPending || create.isPending || remove.isPending
  const single = target.trackIds.length === 1 ? target.trackIds[0] : undefined

  return (
    <div className="space-y-4 p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-semibold">Добавить в плейлист</h2>
          <p className="text-fg-muted truncate text-sm">{target.title}</p>
        </div>
        <IconButton size="sm" label="Закрыть" onClick={onClose}>
          <CloseIcon size={16} />
        </IconButton>
      </div>

      {single !== undefined && <LikeRow trackId={single} />}

      {duplicate ? (
        <div className="space-y-3" role="alert">
          <p className="text-sm">Этот трек уже есть в «{duplicate.title}».</p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={busy}
              onClick={() => {
                add.mutate({ playlist: duplicate, allowDuplicate: true })
              }}
            >
              Добавить ещё раз
            </Button>
            {single !== undefined && (
              <Button
                size="sm"
                disabled={busy}
                onClick={() => {
                  remove.mutate(duplicate)
                }}
              >
                Убрать из плейлиста
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setDuplicate(null)
              }}
            >
              Отмена
            </Button>
          </div>
        </div>
      ) : (
        <>
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
            }}
            placeholder="Найти плейлист"
            aria-label="Найти плейлист"
            className="focus-ring border-border bg-surface-2 h-10 w-full rounded-lg border px-3"
          />
          <ul
            className="max-h-64 scrollbar-thin space-y-0.5 overflow-y-auto"
            data-testid="playlist-options"
          >
            {playlists.isPending && <li className="text-fg-muted p-2 text-sm">Загружаем…</li>}
            {playlists.data && shown.length === 0 && (
              <li className="text-fg-muted p-2 text-sm">
                {search.trim()
                  ? 'Ничего не нашли.'
                  : 'Своих плейлистов пока нет — создайте первый.'}
              </li>
            )}
            {shown.map((p) => (
              <li key={p.ref}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    add.mutate({ playlist: p, allowDuplicate: false })
                  }}
                  className="focus-ring hover:bg-surface-2 flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-left disabled:opacity-50"
                >
                  <Cover url={p.coverUrl} size="sm" className="size-9" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{p.title}</span>
                    <span className="text-fg-muted block text-xs">
                      {p.trackCount ?? 0} {plural(p.trackCount ?? 0, 'трек', 'трека', 'треков')}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <form onSubmit={submitNew} className="flex gap-2">
            <input
              value={newTitle}
              onChange={(e) => {
                setNewTitle(e.target.value)
              }}
              maxLength={100}
              placeholder="Новый плейлист"
              aria-label="Название нового плейлиста"
              className="focus-ring border-border bg-surface-2 h-10 w-full min-w-0 flex-1 rounded-lg border px-3"
            />
            <Button type="submit" disabled={!newTitle.trim() || busy}>
              Создать
            </Button>
          </form>
        </>
      )}
    </div>
  )
}

function LikeRow({ trackId }: { trackId: string }) {
  const liked = useLikedIds().has(trackId)
  const toggle = useToggleLike()
  return (
    <button
      type="button"
      aria-pressed={liked}
      onClick={() => {
        toggle(trackId)
      }}
      className="focus-ring hover:bg-surface-2 flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left"
    >
      <HeartIcon size={18} filled={liked} className={liked ? 'text-accent' : ''} />
      <span className="text-sm">{liked ? 'В «Мне нравится»' : 'Добавить в «Мне нравится»'}</span>
    </button>
  )
}

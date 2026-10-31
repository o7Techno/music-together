// Права создателя комнаты (SPEC §4.2): переименовать, перевыпустить ссылку, удалить.

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type SyntheticEvent, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, api } from '@/shared/api'
import type { WaveMix } from '@/shared/protocol/generated'
import { Button, IconButton } from '@/shared/ui/Button'
import { CloseIcon } from '@/shared/ui/icons'
import { toast } from '@/shared/ui/Toaster'

import { useRoomStore } from './roomStore'

function message(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Не получилось. Попробуйте ещё раз.'
}

export function RoomSettingsButton() {
  const room = useRoomStore((s) => s.room)
  const selfId = useRoomStore((s) => s.selfUserId)
  const dialog = useRef<HTMLDialogElement>(null)
  if (!room || room.ownerId !== selfId) return null
  return (
    <>
      <IconButton size="sm" label="Настройки комнаты" onClick={() => dialog.current?.showModal()}>
        <span aria-hidden="true" className="text-lg leading-none">
          ⋯
        </span>
      </IconButton>
      <dialog
        ref={dialog}
        aria-label="Настройки комнаты"
        className="bg-surface-1 text-fg m-auto w-[min(26rem,calc(100vw-2rem))] rounded-2xl p-0 shadow-2xl backdrop:bg-black/60"
      >
        <RoomSettingsForm onClose={() => dialog.current?.close()} />
      </dialog>
    </>
  )
}

function RoomSettingsForm({ onClose }: { onClose: () => void }) {
  const room = useRoomStore((s) => s.room)
  const [name, setName] = useState(room?.name ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const slug = room?.slug ?? ''

  const rename = useMutation({
    mutationFn: (n: string) => api.renameRoom(slug, n),
    onSuccess: () => {
      toast.success('Комната переименована')
      void qc.invalidateQueries({ queryKey: ['rooms'] })
    },
    onError: (e) => toast.error(message(e)),
  })
  const settings = useMutation({
    mutationFn: (changes: { waveMix?: WaveMix; announceLikes?: boolean }) =>
      api.updateRoom(slug, changes),
    onError: (e) => toast.error(message(e)),
  })
  const reissue = useMutation({
    mutationFn: () => api.reissueLink(slug),
    onSuccess: (r) => {
      void navigate(`/r/${r.slug}`, { replace: true })
      toast.success('Новая ссылка готова — старая больше не работает')
      onClose()
    },
    onError: (e) => toast.error(message(e)),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteRoom(slug),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['rooms'] })
      void navigate('/')
    },
    onError: (e) => toast.error(message(e)),
  })

  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    const value = name.trim()
    if (value && value !== room?.name) rename.mutate(value)
  }

  return (
    <div className="space-y-5 p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Настройки комнаты</h2>
        <IconButton size="sm" label="Закрыть" onClick={onClose}>
          <CloseIcon size={16} />
        </IconButton>
      </div>
      <form onSubmit={submit} className="space-y-2">
        <label className="block space-y-1">
          <span className="text-fg-muted text-sm">Название</span>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value)
            }}
            maxLength={80}
            className="focus-ring border-border bg-surface-2 h-10 w-full rounded-lg border px-3"
          />
        </label>
        <Button type="submit" size="sm" disabled={!name.trim() || rename.isPending}>
          Сохранить
        </Button>
      </form>
      <div className="space-y-3">
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>Ручные треки и волна</span>
          <select
            value={room?.settings.waveMix ?? 'manual_first'}
            disabled={settings.isPending}
            onChange={(e) => {
              settings.mutate({
                waveMix: e.target.value === 'alternate' ? 'alternate' : 'manual_first',
              })
            }}
            className="focus-ring border-border bg-surface-2 h-9 rounded-lg border px-2"
          >
            <option value="manual_first">Сначала ручные</option>
            <option value="alternate">Через один</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={room?.settings.announceLikes ?? true}
            disabled={settings.isPending}
            onChange={(e) => {
              settings.mutate({ announceLikes: e.target.checked })
            }}
            className="accent-[var(--c-accent)]"
          />
          Показывать лайки в ленте
        </label>
      </div>
      <div className="space-y-2">
        <p className="text-fg-muted text-sm">
          Перевыпуск ссылки: старая перестанет работать, уже подключённые останутся в комнате.
        </p>
        <Button
          size="sm"
          onClick={() => {
            reissue.mutate()
          }}
          disabled={reissue.isPending}
        >
          Перевыпустить ссылку
        </Button>
      </div>
      <div className="border-border space-y-2 border-t pt-4">
        {confirmDelete ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm">Удалить комнату для всех?</span>
            <Button
              size="sm"
              variant="danger"
              onClick={() => {
                remove.mutate()
              }}
              disabled={remove.isPending}
            >
              Да, удалить
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setConfirmDelete(false)
              }}
            >
              Отмена
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            className="text-bad"
            onClick={() => {
              setConfirmDelete(true)
            }}
          >
            Удалить комнату
          </Button>
        )}
      </div>
    </div>
  )
}

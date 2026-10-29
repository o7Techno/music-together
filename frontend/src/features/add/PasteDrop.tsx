// Ctrl+V в любом месте комнаты и перетаскивание ссылки в окно (SPEC §4.4): если в тексте есть
// ссылки Яндекс Музыки — показываем диалог «Добавить?» с карточками.

import { useMutation } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { ApiError, api } from '@/shared/api'
import { findYandexLinks } from '@/shared/links'
import { IconButton } from '@/shared/ui/Button'
import { CloseIcon, LinkIcon } from '@/shared/ui/icons'
import { SkeletonRows } from './EntityView'
import { LinkResultsView } from './LinkResultsView'

function isEditable(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return Boolean(el?.closest('input, textarea, select, [contenteditable="true"]'))
}

function droppedText(dt: DataTransfer | null): string {
  if (!dt) return ''
  return dt.getData('text/uri-list') || dt.getData('text/plain') || ''
}

export function PasteDrop() {
  const [dragging, setDragging] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const resolve = useMutation({ mutationFn: (text: string) => api.resolveLinks(text) })

  useEffect(() => {
    const openWith = (text: string): boolean => {
      const links = findYandexLinks(text)
      if (links.length === 0) return false
      resolve.mutate(links.join('\n'))
      dialog.current?.showModal()
      return true
    }
    const onPaste = (e: ClipboardEvent): void => {
      // В полях ввода вставка работает как обычно (поиск сам распознаёт ссылки).
      if (isEditable(e.target)) return
      if (openWith(e.clipboardData?.getData('text/plain') ?? '')) e.preventDefault()
    }
    let depth = 0
    const hasText = (e: DragEvent): boolean =>
      Boolean(e.dataTransfer?.types.some((t) => t === 'text/uri-list' || t === 'text/plain'))
    const onDragEnter = (e: DragEvent): void => {
      if (!hasText(e)) return
      depth += 1
      setDragging(true)
    }
    const onDragLeave = (): void => {
      depth = Math.max(0, depth - 1)
      if (depth === 0) setDragging(false)
    }
    const onDragOver = (e: DragEvent): void => {
      if (hasText(e)) e.preventDefault()
    }
    const onDrop = (e: DragEvent): void => {
      depth = 0
      setDragging(false)
      if (isEditable(e.target)) return
      if (openWith(droppedText(e.dataTransfer))) e.preventDefault()
    }
    document.addEventListener('paste', onPaste)
    window.addEventListener('dragenter', onDragEnter)
    window.addEventListener('dragleave', onDragLeave)
    window.addEventListener('dragover', onDragOver)
    window.addEventListener('drop', onDrop)
    return () => {
      document.removeEventListener('paste', onPaste)
      window.removeEventListener('dragenter', onDragEnter)
      window.removeEventListener('dragleave', onDragLeave)
      window.removeEventListener('dragover', onDragOver)
      window.removeEventListener('drop', onDrop)
    }
    // resolve.mutate стабилен; подписываемся один раз.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const close = (): void => {
    dialog.current?.close()
  }

  return (
    <>
      {dragging && (
        <div className="border-accent bg-surface-0/80 pointer-events-none fixed inset-3 z-50 flex items-center justify-center rounded-3xl border-4 border-dashed backdrop-blur-sm">
          <p className="flex items-center gap-2 text-xl font-semibold">
            <LinkIcon /> Отпустите, чтобы добавить
          </p>
        </div>
      )}
      <dialog
        ref={dialog}
        aria-label="Добавить по ссылке"
        className="bg-surface-1 text-fg m-auto w-[min(32rem,calc(100vw-2rem))] rounded-2xl p-0 shadow-2xl backdrop:bg-black/60"
        data-testid="paste-dialog"
        onClick={(e) => {
          if (e.target === e.currentTarget) close()
        }}
      >
        <div className="space-y-3 p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Добавить?</h2>
            <IconButton size="sm" label="Закрыть" onClick={close}>
              <CloseIcon size={16} />
            </IconButton>
          </div>
          {resolve.isPending && <SkeletonRows count={2} />}
          {resolve.error && (
            <p role="alert" className="text-bad text-sm">
              {resolve.error instanceof ApiError
                ? resolve.error.message
                : 'Не удалось открыть ссылку.'}
            </p>
          )}
          {resolve.data && <LinkResultsView data={resolve.data} onAdded={close} />}
        </div>
      </dialog>
    </>
  )
}

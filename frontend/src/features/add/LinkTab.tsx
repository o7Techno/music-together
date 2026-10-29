// «По ссылке»: одна или несколько ссылок (по одной на строку) → карточки «Добавить?».

import { useMutation } from '@tanstack/react-query'
import { type SyntheticEvent, useState } from 'react'

import { LinkResultsView } from '@/features/add/LinkResultsView'
import { ApiError, api } from '@/shared/api'
import { findYandexLinks } from '@/shared/links'
import { Button } from '@/shared/ui/Button'

export function LinkTab() {
  const [text, setText] = useState('')
  const resolve = useMutation({ mutationFn: (t: string) => api.resolveLinks(t) })
  const count = findYandexLinks(text).length
  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (count > 0) resolve.mutate(text)
  }
  return (
    <div className="space-y-3" data-testid="link-tab">
      <form onSubmit={submit} className="space-y-2">
        <label className="block space-y-1">
          <span className="text-fg-muted text-sm">
            Ссылки на трек, альбом, плейлист или исполнителя — по одной на строку
          </span>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value)
            }}
            rows={4}
            placeholder="https://music.yandex.ru/album/…/track/…"
            className="focus-ring border-border bg-surface-2 w-full rounded-lg border p-3 font-mono text-sm"
            data-testid="link-input"
          />
        </label>
        <Button type="submit" variant="primary" disabled={count === 0 || resolve.isPending}>
          {count > 1 ? `Найти ${String(count)} ссылки` : 'Найти'}
        </Button>
      </form>
      {resolve.error && (
        <p role="alert" className="text-bad text-sm">
          {resolve.error instanceof ApiError ? resolve.error.message : 'Не удалось открыть ссылки.'}
        </p>
      )}
      {resolve.data && <LinkResultsView data={resolve.data} />}
    </div>
  )
}

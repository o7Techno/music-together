import { useMutation, useQuery } from '@tanstack/react-query'
import { type SyntheticEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, api } from '@/shared/api'
import { plural } from '@/shared/format'
import type { Me } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'
import { FullScreenSpinner } from '@/shared/ui/Spinner'

import { LoginCard } from './LoginCard'
import { useLogout, useMe } from './useAuth'

export function HomePage() {
  const me = useMe()
  if (me.isPending) return <FullScreenSpinner />
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-10 px-4 py-10 sm:px-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Слушаем вместе</h1>
          <p className="text-fg-muted">Яндекс Музыка с друзьями — синхронно, секунда в секунду</p>
        </div>
        {me.data && <UserBadge me={me.data} />}
      </header>
      {me.data ? <Rooms me={me.data} /> : <LoginCard />}
    </main>
  )
}

function UserBadge({ me }: { me: Me }) {
  const logout = useLogout()
  return (
    <div className="flex items-center gap-3">
      <span className="text-fg-muted hidden text-sm sm:inline">{me.displayName}</span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          logout.mutate()
        }}
      >
        Выйти
      </Button>
    </div>
  )
}

function Rooms({ me }: { me: Me }) {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: api.myRooms })
  const create = useMutation({
    mutationFn: (n: string) => api.createRoom(n || undefined),
    onSuccess: (room) => {
      void navigate(`/r/${room.slug}`)
    },
  })
  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    create.mutate(name.trim())
  }
  return (
    <div className="space-y-8">
      <form
        onSubmit={submit}
        className="border-border bg-surface-1 flex flex-col gap-3 rounded-2xl border p-5 sm:flex-row"
      >
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          maxLength={80}
          placeholder={`Комната ${me.displayName}`}
          aria-label="Название комнаты"
          className="focus-ring border-border bg-surface-2 h-11 flex-1 rounded-lg border px-3"
        />
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Создать комнату
        </Button>
      </form>
      {create.error && (
        <p role="alert" className="text-bad text-sm">
          {create.error instanceof ApiError ? create.error.message : 'Не удалось создать комнату.'}
        </p>
      )}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Мои комнаты</h2>
        {rooms.isPending && <div className="bg-surface-1 h-16 animate-pulse rounded-xl" />}
        {rooms.data?.length === 0 && (
          <p className="text-fg-muted">Пока пусто — создайте комнату и позовите друзей.</p>
        )}
        <ul className="space-y-2">
          {rooms.data?.map((r) => (
            <li key={r.slug}>
              <Link
                to={`/r/${r.slug}`}
                className="focus-ring border-border bg-surface-1 hover:bg-surface-2 flex items-center justify-between gap-4 rounded-xl border px-4 py-3 transition-colors"
              >
                <span className="truncate font-medium">{r.name}</span>
                <span className="text-fg-muted shrink-0 text-sm">
                  {r.online > 0
                    ? `${String(r.online)} ${plural(r.online, 'слушает', 'слушают', 'слушают')}`
                    : r.isOwner
                      ? 'создатель'
                      : ''}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type SyntheticEvent, useState } from 'react'

import { ApiError, api } from '@/shared/api'
import { Button } from '@/shared/ui/Button'

import { useAuthConfig } from './useAuth'
import { YandexLogin } from './YandexLogin'

export function LoginCard() {
  const config = useAuthConfig()
  return (
    <div className="border-border bg-surface-1 w-full max-w-md space-y-6 rounded-2xl border p-6 shadow-2xl">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Вход</h2>
        <p className="text-fg-muted text-sm">
          Каждый слушает со своего аккаунта Яндекс Музыки с подпиской Плюс — сервис синхронизирует
          только положение трека, а не звук.
        </p>
      </div>
      {config.data?.yandexLogin && <YandexLogin />}
      {config.data?.devLogin && <DevLogin primary={!config.data.yandexLogin} />}
    </div>
  )
}

function DevLogin({ primary }: { primary: boolean }) {
  const [name, setName] = useState('')
  const qc = useQueryClient()
  const login = useMutation({
    mutationFn: (n: string) => api.devLogin(n),
    onSuccess: (me) => {
      qc.setQueryData(['me'], me)
    },
  })
  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (name.trim()) login.mutate(name.trim())
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      {!primary && <p className="text-fg-subtle text-xs">Режим разработки: вход без Яндекса</p>}
      <label className="block space-y-1">
        <span className="text-fg-muted text-sm">Ваше имя</span>
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          maxLength={40}
          autoFocus={primary}
          placeholder="Например, Аня"
          className="focus-ring border-border bg-surface-2 h-11 w-full rounded-lg border px-3"
        />
      </label>
      {login.error && (
        <p role="alert" className="text-bad text-sm">
          {login.error instanceof ApiError ? login.error.message : 'Не получилось войти.'}
        </p>
      )}
      <Button
        type="submit"
        variant={primary ? 'primary' : 'secondary'}
        className="w-full"
        disabled={!name.trim() || login.isPending}
      >
        {primary ? 'Войти' : 'Войти без Яндекса'}
      </Button>
    </form>
  )
}

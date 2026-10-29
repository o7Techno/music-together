// Плашки о проблемах с аккаунтом: нет Плюса, вход в Яндекс устарел (SPEC §4.1).

import { useQueryClient } from '@tanstack/react-query'

import type { Me } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'

import { useAuthIssue } from './authIssue'
import { useLogout } from './useAuth'

export function AccountNotice({ me }: { me: Me }) {
  const relogin = useAuthIssue((s) => s.relogin) || !me.providerConnected
  const logout = useLogout()
  const qc = useQueryClient()
  const reloginNow = (): void => {
    logout.mutate(undefined, {
      onSuccess: () => {
        useAuthIssue.setState({ relogin: false })
        void qc.invalidateQueries({ queryKey: ['me'] })
      },
    })
  }
  if (me.provider !== 'yandex') return null
  if (relogin) {
    return (
      <Notice tone="bad">
        <span>Вход в Яндекс Музыку устарел или был отозван — войдите заново.</span>
        <Button size="sm" variant="primary" onClick={reloginNow}>
          Войти заново
        </Button>
      </Notice>
    )
  }
  if (!me.hasPlus) {
    return (
      <Notice tone="warn">
        <span>
          У аккаунта <b>{me.login}</b> нет подписки Плюс — слушать полные треки не получится.
        </span>
        <Button size="sm" onClick={reloginNow}>
          Войти другим аккаунтом
        </Button>
      </Notice>
    )
  }
  return null
}

function Notice({ tone, children }: { tone: 'warn' | 'bad'; children: React.ReactNode }) {
  const color = tone === 'bad' ? 'border-bad/50 bg-bad/10' : 'border-warn/50 bg-warn/10'
  return (
    <div
      role="alert"
      className={`flex flex-col items-start gap-3 rounded-xl border p-4 text-sm sm:flex-row sm:items-center sm:justify-between ${color}`}
    >
      {children}
    </div>
  )
}

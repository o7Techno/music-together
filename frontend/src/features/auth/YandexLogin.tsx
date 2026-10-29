// Вход через Яндекс: OAuth Device Flow (основной) и ручная вставка токена (запасной), SPEC §4.1.

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type SyntheticEvent, useEffect, useRef, useState } from 'react'

import { ApiError, api } from '@/shared/api'
import type { Me } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'
import { Spinner } from '@/shared/ui/Spinner'
import { toast } from '@/shared/ui/Toaster'

/** Ссылка для получения токена вручную (OAuth implicit flow приложения Яндекс Музыки). */
const TOKEN_HELP_URL =
  'https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d'

interface Flow {
  flowId: string
  userCode: string
  verificationUrl: string
  expiresAt: number
  intervalMs: number
}

export function YandexLogin() {
  const qc = useQueryClient()
  const [flow, setFlow] = useState<Flow | null>(null)
  const [expired, setExpired] = useState(false)
  const onLoggedIn = (me: Me): void => {
    qc.setQueryData(['me'], me)
    void qc.invalidateQueries({ queryKey: ['rooms'] })
  }
  const start = useMutation({
    mutationFn: api.deviceStart,
    onSuccess: (r) => {
      setExpired(false)
      setFlow({
        flowId: r.flowId,
        userCode: r.userCode,
        verificationUrl: r.verificationUrl,
        expiresAt: Date.now() + r.expiresIn * 1000,
        intervalMs: Math.max(1, r.interval) * 1000,
      })
    },
  })

  return (
    <div className="space-y-4">
      {!flow || expired ? (
        <>
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            disabled={start.isPending}
            onClick={() => {
              start.mutate()
            }}
          >
            {start.isPending ? <Spinner className="size-5" /> : null}
            Войти через Яндекс
          </Button>
          {expired && (
            <p className="text-warn text-sm">Код устарел — получите новый, это быстро.</p>
          )}
          {start.error && (
            <p role="alert" className="text-bad text-sm">
              {start.error instanceof ApiError ? start.error.message : 'Не удалось начать вход.'}
            </p>
          )}
        </>
      ) : (
        <DeviceCode
          flow={flow}
          onDone={onLoggedIn}
          onExpired={() => {
            setExpired(true)
          }}
        />
      )}
      <TokenLogin onDone={onLoggedIn} />
    </div>
  )
}

function DeviceCode({
  flow,
  onDone,
  onExpired,
}: {
  flow: Flow
  onDone: (me: Me) => void
  onExpired: () => void
}) {
  const [left, setLeft] = useState(() => Math.round((flow.expiresAt - Date.now()) / 1000))
  const done = useRef(false)

  useEffect(() => {
    let timer = 0
    const life = { cancelled: false }
    // Функция, а не поле: проверка после await не должна «сужаться» анализатором до false.
    const cancelled = (): boolean => life.cancelled
    const poll = async (): Promise<void> => {
      if (cancelled() || done.current) return
      if (Date.now() > flow.expiresAt) {
        onExpired()
        return
      }
      try {
        const r = await api.devicePoll(flow.flowId)
        if (cancelled()) return
        if (r.status === 'ok' && r.me) {
          done.current = true
          onDone(r.me)
          return
        }
        if (r.status === 'expired') {
          onExpired()
          return
        }
      } catch (err) {
        if (err instanceof ApiError && err.status !== 0) toast.error(err.message)
      }
      timer = window.setTimeout(() => void poll(), flow.intervalMs)
    }
    timer = window.setTimeout(() => void poll(), flow.intervalMs)
    const tick = window.setInterval(() => {
      setLeft(Math.max(0, Math.round((flow.expiresAt - Date.now()) / 1000)))
    }, 1000)
    return () => {
      life.cancelled = true
      window.clearTimeout(timer)
      window.clearInterval(tick)
    }
  }, [flow, onDone, onExpired])

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(flow.userCode)
      toast.success('Код скопирован')
    } catch {
      /* не критично */
    }
  }

  return (
    <div className="border-border bg-surface-2 space-y-4 rounded-xl border p-4">
      <ol className="text-fg-muted list-decimal space-y-1 pl-5 text-sm">
        <li>
          Откройте{' '}
          <a
            href={flow.verificationUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent font-medium hover:underline"
          >
            {flow.verificationUrl.replace(/^https?:\/\//, '')}
          </a>
        </li>
        <li>
          Проверьте, что вошли в <b className="text-fg">аккаунт с Плюсом</b> — с него вы будете
          слушать
        </li>
        <li>Введите код:</li>
      </ol>
      <button
        type="button"
        onClick={() => void copy()}
        className="focus-ring bg-surface-0 w-full rounded-lg py-3 font-mono text-3xl font-bold tracking-[0.3em]"
        aria-label={`Код ${flow.userCode}, нажмите, чтобы скопировать`}
        data-testid="device-code"
      >
        {flow.userCode}
      </button>
      <p className="text-fg-subtle flex items-center gap-2 text-xs" role="status">
        <Spinner className="size-3" /> Ждём подтверждения… код действует ещё {Math.floor(left / 60)}
        :{String(left % 60).padStart(2, '0')}
      </p>
    </div>
  )
}

function TokenLogin({ onDone }: { onDone: (me: Me) => void }) {
  const [token, setToken] = useState('')
  const login = useMutation({ mutationFn: api.tokenLogin, onSuccess: onDone })
  const submit = (e: SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (token.trim()) login.mutate(token.trim())
  }
  return (
    <details className="group text-sm">
      <summary className="text-fg-subtle hover:text-fg-muted cursor-pointer select-none">
        Другие способы входа
      </summary>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <p className="text-fg-muted">
          Вставьте OAuth-токен Яндекс Музыки. Как получить: откройте{' '}
          <a
            href={TOKEN_HELP_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent hover:underline"
          >
            эту ссылку
          </a>
          , войдите в аккаунт с Плюсом и скопируйте из адресной строки значение после{' '}
          <code className="bg-surface-3 rounded px-1">access_token=</code> (до символа &amp;). Токен
          хранится на сервере в зашифрованном виде и никому не показывается.
        </p>
        <input
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => {
            setToken(e.target.value)
          }}
          placeholder="y0_…"
          aria-label="OAuth-токен"
          className="focus-ring border-border bg-surface-2 h-11 w-full rounded-lg border px-3 font-mono"
        />
        {login.error && (
          <p role="alert" className="text-bad">
            {login.error instanceof ApiError ? login.error.message : 'Не получилось войти.'}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={!token.trim() || login.isPending}>
          Войти по токену
        </Button>
      </form>
    </details>
  )
}

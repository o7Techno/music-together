// Открытая страница не обновляется сама, а в приложении на экране «Домой» нет и кнопки обновления:
// без этой плашки телефон часами выполняет старый код после деплоя.

import { useEffect, useState } from 'react'

import { Button } from './Button'

const CHECK_EVERY_MS = 5 * 60_000

async function serverBuildId(): Promise<string | null> {
  try {
    const response = await fetch('/build.json', { cache: 'no-store' })
    if (!response.ok) return null
    const data = (await response.json()) as { id?: unknown }
    return typeof data.id === 'string' ? data.id : null
  } catch {
    // Нет сети или dev-сервер отдал страницу вместо файла: проверим в следующий раз.
    return null
  }
}

export function UpdateBanner() {
  const [outdated, setOutdated] = useState(false)

  useEffect(() => {
    const check = (): void => {
      if (document.visibilityState !== 'visible') return
      void serverBuildId().then((id) => {
        if (id !== null && id !== __BUILD_ID__) setOutdated(true)
      })
    }
    check()
    const timer = window.setInterval(check, CHECK_EVERY_MS)
    document.addEventListener('visibilitychange', check)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
    }
  }, [])

  if (!outdated) return null
  return (
    <div
      role="status"
      data-testid="update-banner"
      className="bg-surface-3 fixed inset-x-3 top-[max(0.75rem,env(safe-area-inset-top))] z-50 mx-auto flex max-w-md items-center justify-between gap-3 rounded-full px-4 py-2 text-sm shadow-xl"
    >
      <span>Вышла новая версия</span>
      <Button
        size="sm"
        variant="primary"
        onClick={() => {
          window.location.reload()
        }}
      >
        Обновить
      </Button>
    </div>
  )
}

// Необязательный Sentry для фронта (SPEC §7.7): DSN приходит с сервера (/api/auth/config),
// SDK загружается отдельным чанком только если он включён — основной бандл не растёт.

import { api } from './api'

export async function initSentry(): Promise<void> {
  try {
    const config = await api.authConfig()
    if (!config.sentryDsn) return
    const Sentry = await import('@sentry/react')
    Sentry.init({
      dsn: config.sentryDsn,
      environment: config.environment,
      tracesSampleRate: 0,
    })
  } catch {
    // Мониторинг не должен ломать приложение.
  }
}

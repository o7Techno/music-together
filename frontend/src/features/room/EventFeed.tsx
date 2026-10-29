import { eventText } from '@/shared/format'

import { useRoomStore } from './roomStore'

export function EventFeed() {
  const events = useRoomStore((s) => s.events)
  const recent = events.slice(-30).reverse()
  return (
    <section aria-label="Лента событий" className="space-y-2">
      <h3 className="text-fg-muted text-sm font-semibold">Лента</h3>
      {recent.length === 0 && <p className="text-fg-subtle text-sm">Пока тихо.</p>}
      <ol className="space-y-1 text-sm" data-testid="events">
        {recent.map((e) => (
          <li key={e.id} className="text-fg-muted flex gap-2">
            <time className="text-fg-subtle shrink-0 tabular-nums">
              {new Date(e.atMs).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
            </time>
            <span className="min-w-0">{eventText(e)}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

import type { MemberView } from '@/shared/protocol/generated'

import { useRoomStore } from './roomStore'

function statusOf(m: MemberView): { label: string; tone: string } {
  if (!m.audioUnlocked) return { label: 'звук не включён', tone: 'bg-fg-subtle' }
  if (m.trackUnavailable) return { label: 'трек недоступен', tone: 'bg-bad' }
  switch (m.sync) {
    case 'in_sync':
      return { label: 'в синхроне', tone: 'bg-ok' }
    case 'catching_up':
      return { label: 'догоняет', tone: 'bg-warn' }
    case 'buffering':
      return { label: 'буферизация', tone: 'bg-warn' }
    case 'unstable':
      return { label: 'нестабильно', tone: 'bg-bad' }
    case 'idle':
      return { label: 'готов', tone: 'bg-ok/60' }
  }
}

export function Avatar({
  name,
  url,
  className = 'size-8',
}: {
  name: string
  url?: string | null
  className?: string
}) {
  if (url)
    return <img src={url} alt="" className={`${className} shrink-0 rounded-full object-cover`} />
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360
  return (
    <span
      aria-hidden="true"
      className={`${className} flex shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white`}
      style={{ background: `hsl(${String(h)} 55% 40%)` }}
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  )
}

export function Members() {
  const members = useRoomStore((s) => s.members)
  return (
    <section aria-label="Участники" className="space-y-2">
      <h3 className="text-fg-muted text-sm font-semibold">Слушают · {members.length}</h3>
      <ul className="space-y-1.5" data-testid="members">
        {members.map((m) => {
          const st = statusOf(m)
          return (
            <li key={m.userId} className="flex items-center gap-2.5 text-sm">
              <span className="relative">
                <Avatar name={m.name} url={m.avatarUrl} />
                <span
                  className={`ring-surface-1 absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full ring-2 ${st.tone}`}
                />
              </span>
              <span className="min-w-0 flex-1 truncate">
                {m.name}
                {m.isOwner && <span className="text-fg-subtle ml-1 text-xs">создатель</span>}
              </span>
              <span className="text-fg-subtle shrink-0 text-xs" title={st.label}>
                {st.label}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

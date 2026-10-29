// Отладочная панель синхрона (SPEC §5.8): ?debug=1 или клавиша D.

import { useEffect, useState } from 'react'

import type { DebugInfo } from '@/player/syncEngine'
import { DESKTOP_PROFILE } from '@/player/driftController'
import { ANDROID_PROFILE, IOS_PROFILE } from '@/player/platform'
import { IconButton } from '@/shared/ui/Button'
import { CloseIcon } from '@/shared/ui/icons'

import { useRoomSession } from './RoomContext'
import { useRoomStore } from './roomStore'

const PROFILES = [DESKTOP_PROFILE, IOS_PROFILE, ANDROID_PROFILE]

function fmt(v: number | null | undefined, digits = 1, unit = ' мс'): string {
  return v === null || v === undefined ? '—' : `${v.toFixed(digits)}${unit}`
}

export function DebugPanel({ onClose }: { onClose: () => void }) {
  const session = useRoomSession()
  const [info, setInfo] = useState<DebugInfo>(() => session.engine.debugInfo())
  const stats = useRoomStore((s) => s.stats)
  const members = useRoomStore((s) => s.members)
  useEffect(() => {
    const t = window.setInterval(() => {
      setInfo(session.engine.debugInfo())
    }, 250)
    return () => {
      window.clearInterval(t)
    }
  }, [session])

  const rows: [string, string][] = [
    ['Offset часов', fmt(info.offsetMs)],
    ['RTT (лучший)', fmt(info.rttMs)],
    ['Замеров часов', String(info.clockSamples)],
    ['Drift', fmt(info.driftMs)],
    ['Drift (сглаж.)', fmt(info.smoothedDriftMs)],
    ['playbackRate', info.playbackRate.toFixed(4)],
    ['Буфер вперёд', fmt(info.bufferedAheadMs / 1000, 1, ' с')],
    ['Версия / статус', `${String(info.version)} / ${info.status}`],
    ['Задержка вывода', fmt(info.outputLatencyMs)],
    ['Задержка старта', fmt(info.startLatencyMs)],
    ['Задержка seek', fmt(info.seekLatencyMs)],
    ['Неудачных seek', `${String(info.seekFailures)}${info.unstable ? ' (нестабилен)' : ''}`],
    ['Синхрон', info.sync],
    ['Комната: медиана', fmt(stats.medianMs)],
    ['Комната: p95', fmt(stats.p95Ms)],
    ['Комната: замеров', String(stats.samples)],
  ]

  return (
    <aside
      aria-label="Отладка синхронизации"
      data-testid="debug-panel"
      className="border-border bg-surface-1/95 fixed top-3 right-3 z-40 w-80 max-w-[calc(100vw-1.5rem)] rounded-xl border p-3 font-mono text-xs shadow-2xl backdrop-blur"
    >
      <div className="mb-2 flex items-center justify-between">
        <strong className="font-sans text-sm">Синхрон</strong>
        <IconButton size="sm" label="Закрыть отладку" onClick={onClose}>
          <CloseIcon size={14} />
        </IconButton>
      </div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-fg-subtle">{k}</dt>
            <dd className="text-right tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="border-border mt-2 space-y-0.5 border-t pt-2">
        {members.map((m) => (
          <div key={m.userId} className="flex justify-between">
            <span className="truncate">{m.name}</span>
            <span className="tabular-nums">
              {fmt(m.driftMedianMs, 0, '')} / {fmt(m.driftP95Ms, 0, ' мс')}
            </span>
          </div>
        ))}
      </div>
      <div className="border-border mt-2 flex flex-wrap items-center gap-2 border-t pt-2 font-sans">
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={info.latencyCompensation}
            onChange={(e) => {
              session.engine.setLatencyCompensation(e.target.checked)
            }}
          />
          компенсировать задержку вывода
        </label>
        <select
          aria-label="Профиль коррекции"
          value={info.profile}
          onChange={(e) => {
            const p = PROFILES.find((x) => x.name === e.target.value)
            if (p) session.engine.setProfile(p)
          }}
          className="bg-surface-3 rounded px-1"
        >
          {PROFILES.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
    </aside>
  )
}

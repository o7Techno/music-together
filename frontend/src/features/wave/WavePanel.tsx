// Панель «Волна» (SPEC-wave §9): запуск своей волны и волны по зерну, настройки, «не учить».

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { useMe } from '@/features/auth/useAuth'
import { useRoomStore } from '@/features/room/roomStore'
import { useCommand } from '@/features/room/useCommand'
import { ApiError, api } from '@/shared/api'
import type { WaveOptionGroup, WaveSeed, WaveStation } from '@/shared/protocol/generated'
import { Button } from '@/shared/ui/Button'
import { toast } from '@/shared/ui/Toaster'

import { useWaveStart } from './useWave'

const GROUP_TITLE: Record<string, string> = {
  diversity: 'Характер',
  language: 'Язык',
  mood_energy: 'Настроение',
}
// Настроение выбирается в настройках волны: второй такой же список только путает (D-045).
const KIND_TITLE: Record<string, string> = {
  activity: 'Занятие',
  genre: 'Жанр',
}

function stationSeed(station: WaveStation): WaveSeed | null {
  const { kind } = station
  if (kind !== 'mood' && kind !== 'activity' && kind !== 'genre') return null
  return { kind, id: station.id, label: station.title }
}

export function WavePanel() {
  const wave = useRoomStore((s) => s.wave)
  const selfId = useRoomStore((s) => s.selfUserId)
  const send = useCommand()
  const start = useWaveStart()
  const options = useQuery({
    queryKey: ['wave-options'],
    queryFn: api.waveOptions,
    staleTime: 15 * 60_000,
  })
  const [draft, setDraft] = useState<string[]>([])
  const active = wave !== null && wave.status !== 'off'
  const shared = active && wave.mode === 'shared'
  const mine = active && (shared || wave.ownerId === selfId)
  const settings = active ? wave.settings : draft

  const changeSetting = (group: WaveOptionGroup, seed: string): void => {
    const seeds = new Set(group.options.map((o) => o.seed))
    const isDefault = group.options.find((o) => o.seed === seed)?.default ?? false
    const next = [...settings.filter((s) => !seeds.has(s)), ...(isDefault ? [] : [seed])]
    if (mine) void send({ type: 'wave.update_settings', settings: next })
    else setDraft(next)
  }

  const settingsLocked = active && !mine

  return (
    <div className="space-y-5" data-testid="wave-panel">
      <WaveStatus />
      <div className="wave-hero space-y-3 rounded-2xl p-4">
        <Button
          size="lg"
          variant="primary"
          className="w-full"
          onClick={() => void start('personal', { settings })}
        >
          {active && !mine ? 'Включить мою волну вместо этой' : 'Включить мою волну'}
        </Button>
        <Button
          className="w-full"
          disabled={shared}
          onClick={() => void start('shared', { settings })}
        >
          Общая волна
        </Button>
        <p className="text-fg-muted text-sm">
          Бесконечный поток рекомендаций для всей комнаты. Ручные треки играют первыми.
        </p>
        {active && (
          <Button size="sm" className="w-full" onClick={() => void send({ type: 'wave.stop' })}>
            Остановить волну
          </Button>
        )}
      </div>

      <Participation />

      <SeedFromCurrent />

      {options.data && (
        <Stations
          stations={options.data.stations}
          onPick={(seed) => void start('seed', { seed, settings })}
        />
      )}

      {options.data && options.data.settings.length > 0 && (
        <section className="space-y-2" aria-label="Настройки волны">
          <h3 className="text-fg-muted text-sm font-semibold">Настройки</h3>
          {settingsLocked && (
            <p className="text-fg-subtle text-xs">Настройки меняет владелец волны.</p>
          )}
          {options.data.settings.map((group) => {
            const chosen = group.options.find((o) => settings.includes(o.seed))
            const fallback = group.options.find((o) => o.default)
            return (
              <label key={group.key} className="flex items-center justify-between gap-3 text-sm">
                <span>{GROUP_TITLE[group.key] ?? group.key}</span>
                <select
                  value={(chosen ?? fallback)?.seed ?? ''}
                  disabled={settingsLocked}
                  onChange={(e) => {
                    changeSetting(group, e.target.value)
                  }}
                  className="focus-ring border-border bg-surface-2 h-9 max-w-[60%] rounded-lg border px-2 disabled:opacity-50"
                >
                  {group.options.map((o) => (
                    <option key={o.seed} value={o.seed}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            )
          })}
        </section>
      )}

      {options.error && (
        <p role="alert" className="text-bad text-sm">
          {options.error instanceof ApiError
            ? options.error.message
            : 'Не удалось загрузить настройки волны.'}
        </p>
      )}

      <LearningToggle />
    </div>
  )
}

function WaveStatus() {
  const wave = useRoomStore((s) => s.wave)
  if (!wave || wave.status === 'off') return null
  const who =
    wave.mode === 'shared'
      ? 'Общая волна'
      : wave.seedLabel
        ? `Волна по: ${wave.seedLabel}`
        : `Моя волна · ${wave.ownerName ?? ''}`
  const state =
    wave.status === 'starting'
      ? 'Запускаем…'
      : wave.status === 'unavailable'
        ? 'Временно недоступна, пробуем снова'
        : wave.status === 'waiting'
          ? wave.mode === 'shared' && !wave.sources.some((source) => source.active)
            ? 'В общей волне никого нет: ждём участников'
            : 'Подбираем треки…'
          : wave.ownerAway
            ? 'Владелец вышел: через 15 минут волна остановится'
            : 'Играет'
  return (
    <div role="status" data-testid="wave-status">
      <p className="font-semibold">{who}</p>
      <p className="text-fg-muted text-sm">{state}</p>
    </div>
  )
}

/** Кто даёт треки в общую волну и переключатель «Моя волна участвует». */
function Participation() {
  const wave = useRoomStore((s) => s.wave)
  const selfId = useRoomStore((s) => s.selfUserId)
  const send = useCommand()
  if (wave?.mode !== 'shared' || wave.status === 'off') return null
  const me = wave.sources.find((source) => source.userId === selfId)
  const active = wave.sources.filter((source) => source.active)
  return (
    <section className="space-y-2" aria-label="Участники общей волны">
      <p className="text-fg-muted text-sm" data-testid="wave-sources">
        Участвуют: {active.map((source) => source.name).join(', ') || 'пока никто'}
      </p>
      {me && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={me.enabled}
            onChange={(e) => {
              void send({ type: 'wave.set_participation', enabled: e.target.checked })
            }}
            className="accent-[var(--c-accent)]"
          />
          Моя волна участвует
        </label>
      )}
    </section>
  )
}

function SeedFromCurrent() {
  const track = useRoomStore((s) => s.queue?.current?.track ?? null)
  const start = useWaveStart()
  if (!track) return null
  const artist = track.artists[0]
  return (
    <section className="space-y-2" aria-label="Волна от текущего трека">
      <h3 className="text-fg-muted text-sm font-semibold">От того, что играет</h3>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() =>
            void start('seed', {
              seed: { kind: 'track', id: track.id.split(':')[0] ?? track.id, label: track.title },
            })
          }
        >
          Похожее на трек
        </Button>
        {artist && (
          <Button
            size="sm"
            onClick={() =>
              void start('seed', { seed: { kind: 'artist', id: artist.id, label: artist.name } })
            }
          >
            По исполнителю
          </Button>
        )}
        {track.albumId && (
          <Button
            size="sm"
            onClick={() =>
              void start('seed', {
                seed: {
                  kind: 'album',
                  id: track.albumId ?? '',
                  label: track.albumTitle ?? 'альбом',
                },
              })
            }
          >
            По альбому
          </Button>
        )}
      </div>
    </section>
  )
}

function Stations({
  stations,
  onPick,
}: {
  stations: WaveStation[]
  onPick: (seed: WaveSeed) => void
}) {
  const kinds = ['activity', 'genre'].filter((k) => stations.some((s) => s.kind === k))
  return (
    <>
      {kinds.map((kind) => (
        <label key={kind} className="flex items-center justify-between gap-3 text-sm">
          <span className="text-fg-muted font-semibold">{KIND_TITLE[kind]}</span>
          <select
            value=""
            aria-label={`Волна: ${KIND_TITLE[kind] ?? kind}`}
            onChange={(e) => {
              const station = stations.find((s) => s.kind === kind && s.id === e.target.value)
              const seed = station ? stationSeed(station) : null
              if (seed) onPick(seed)
            }}
            className="focus-ring border-border bg-surface-2 h-9 max-w-[60%] rounded-lg border px-2"
          >
            <option value="">Выбрать…</option>
            {stations
              .filter((s) => s.kind === kind)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
          </select>
        </label>
      ))}
    </>
  )
}

function LearningToggle() {
  const me = useMe().data
  const qc = useQueryClient()
  const update = useMutation({
    mutationFn: (waveLearning: boolean) => api.updateMySettings({ waveLearning }),
    onSuccess: (next) => {
      qc.setQueryData(['me'], next)
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : 'Не получилось сохранить.')
    },
  })
  if (!me) return null
  return (
    <label className="flex items-start gap-2 text-sm">
      <input
        type="checkbox"
        checked={!me.waveLearning}
        disabled={update.isPending}
        onChange={(e) => {
          update.mutate(!e.target.checked)
        }}
        className="mt-1 accent-[var(--c-accent)]"
      />
      <span>
        Не учить мою волну на прослушиваниях в комнате
        <span className="text-fg-subtle block text-xs">
          Волна будет хуже подстраиваться, зато рекомендации останутся только вашими.
        </span>
      </span>
    </label>
  )
}

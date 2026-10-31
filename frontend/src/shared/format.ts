import type { ArtistRef, RoomEvent } from './protocol/generated'

export function formatTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${String(h)}:${String(m).padStart(2, '0')}:${ss}` : `${String(m)}:${ss}`
}

export function artistNames(artists: ArtistRef[]): string {
  return artists.map((a) => a.name).join(', ')
}

/** Склонение: plural(5, 'трек', 'трека', 'треков'). */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

const SOURCE_LABEL: Record<string, string> = {
  album: 'из альбома',
  playlist: 'из плейлиста',
  artist: 'исполнителя',
  liked: 'из «Мне нравится»',
}

/** Текст события ленты: «Аня поставила на паузу» (без рода — нейтральные формулировки). */
export function eventText(e: RoomEvent): string {
  const who = e.userName ?? 'Кто-то'
  switch (e.kind) {
    case 'joined':
      return `${who} — в комнате`
    case 'left':
      return `${who} вышел(а) из комнаты`
    case 'play':
      return `${who}: ▶ воспроизведение`
    case 'pause':
      return `${who}: ⏸ пауза`
    case 'seek':
      return `${who}: перемотка на ${formatTime(e.positionMs ?? 0)}`
    case 'next':
      return `${who}: ⏭ следующий трек`
    case 'prev':
      return `${who}: ⏮ предыдущий трек`
    case 'play_item':
      return `${who}: играть «${e.title ?? ''}»`
    case 'queue_add': {
      const count = e.count ?? 1
      if (count === 1 && e.title) return `${who} добавил(а) «${e.title}»`
      const source = e.source?.kind ? SOURCE_LABEL[e.source.kind] : undefined
      const from = source ? ` ${source}${e.source?.title ? ` «${e.source.title}»` : ''}` : ''
      return `${who} добавил(а) ${String(count)} ${plural(count, 'трек', 'трека', 'треков')}${from}`
    }
    case 'queue_remove':
      return `${who} убрал(а) «${e.title ?? ''}» из очереди`
    case 'queue_move':
      return `${who} изменил(а) порядок очереди`
    case 'queue_shuffle':
      return `${who} перемешал(а) очередь`
    case 'queue_clear':
      return `${who} очистил(а) очередь`
    case 'repeat':
      return `${who}: повтор — ${e.repeat === 'track' ? 'трек' : e.repeat === 'queue' ? 'очередь' : 'выкл'}`
    case 'renamed':
      return `${who} переименовал(а) комнату в «${e.title ?? ''}»`
    case 'kicked':
      return `${who} убрал(а) из комнаты: ${e.title ?? ''}`
    case 'wave_started':
      return e.title ? `${who} включил(а) волну по: ${e.title}` : `${who} включил(а) свою волну`
    case 'wave_replaced':
      return e.title
        ? `${who} заменил(а) волну на волну по: ${e.title}`
        : `${who} заменил(а) волну на свою`
    case 'wave_stopped':
      return waveStopText(e, who)
    case 'wave_unavailable':
      return 'Волна временно недоступна — пробуем снова'
    case 'wave_resumed':
      return 'Волна снова играет'
    case 'wave_shared_started':
      return `${who} включил(а) общую волну`
    case 'wave_no_sources':
      return 'В общей волне никого нет — ждём участников'
    case 'track_liked':
      return `${who} лайкнул(а) «${e.title ?? ''}»`
  }
}

function waveStopText(e: RoomEvent, who: string): string {
  switch (e.reason) {
    case 'owner_away':
      return 'Волна остановлена: владелец вышел из комнаты'
    case 'owner_gone':
      return 'Волна остановлена: владелец больше не в комнате'
    case 'auth':
      return 'Волна остановлена: нужен повторный вход в Яндекс Музыку'
    default:
      return `${who} остановил(а) волну`
  }
}

/** Критичные действия дублируются тостом (SPEC §4.5). */
export function isToastWorthy(e: RoomEvent): boolean {
  return [
    'pause',
    'play',
    'seek',
    'next',
    'prev',
    'play_item',
    'queue_clear',
    'wave_started',
    'wave_shared_started',
    'wave_replaced',
    'wave_stopped',
    'wave_unavailable',
  ].includes(e.kind)
}

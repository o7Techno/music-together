// Состояние комнаты для UI. Пишет только RoomSession (из сообщений сервера и движка).

import { create } from 'zustand'

import type {
  ChatMessage,
  MemberView,
  PlaybackState,
  QueueState,
  RoomEvent,
  RoomInfo,
  ServerMessage,
  SyncState,
  SyncStats,
} from '@/shared/protocol/generated'
import type { SocketStatus } from '@/shared/roomSocket'

const EVENTS_LIMIT = 100
const CHAT_LIMIT = 200

export interface RoomState {
  status: SocketStatus
  terminalCode: number | null
  room: RoomInfo | null
  selfUserId: string | null
  playback: PlaybackState | null
  queue: QueueState | null
  members: MemberView[]
  stats: SyncStats
  events: RoomEvent[]
  chat: ChatMessage[]
  audioUnlocked: boolean
  sync: SyncState
  trackUnavailable: boolean
}

const initial: RoomState = {
  status: 'connecting',
  terminalCode: null,
  room: null,
  selfUserId: null,
  playback: null,
  queue: null,
  members: [],
  stats: { medianMs: null, p95Ms: null, samples: 0 },
  events: [],
  chat: [],
  audioUnlocked: false,
  sync: 'idle',
  trackUnavailable: false,
}

export const useRoomStore = create<RoomState>(() => ({ ...initial }))

export function resetRoomStore(): void {
  useRoomStore.setState({ ...initial }, true)
}

/**
 * Оптимистичное изменение очереди: применяется сразу, сервер подтвердит новой версией.
 * Возвращает откат — вызвать, если команда отклонена (и сервер ещё не прислал новую версию).
 */
export function optimisticQueue(mutate: (q: QueueState) => QueueState): () => void {
  const before = useRoomStore.getState().queue
  if (!before) return () => undefined
  useRoomStore.setState({ queue: mutate(before) })
  return () => {
    const now = useRoomStore.getState().queue
    if (now && now.version === before.version) useRoomStore.setState({ queue: before })
  }
}

/** Применить сообщение сервера к состоянию UI. Версии защищают от устаревших данных. */
export function applyServerMessage(msg: ServerMessage): void {
  const set = useRoomStore.setState
  switch (msg.type) {
    case 'snapshot':
      set({
        room: msg.room,
        selfUserId: msg.selfUserId,
        playback: msg.playback,
        queue: msg.queue,
        members: msg.members,
        stats: msg.stats,
        events: msg.events.slice(-EVENTS_LIMIT),
        chat: msg.chat.slice(-CHAT_LIMIT),
      })
      break
    case 'playback':
      set((s) =>
        s.playback && msg.state.version <= s.playback.version ? {} : { playback: msg.state },
      )
      break
    case 'queue':
      set((s) => (s.queue && msg.queue.version < s.queue.version ? {} : { queue: msg.queue }))
      break
    case 'members':
      set({ members: msg.members, stats: msg.stats })
      break
    case 'room':
      set({ room: msg.room })
      break
    case 'event':
      set((s) => ({ events: [...s.events, msg.event].slice(-EVENTS_LIMIT) }))
      break
    case 'chat':
      set((s) => ({ chat: [...s.chat, msg.message].slice(-CHAT_LIMIT) }))
      break
    default:
      break
  }
}

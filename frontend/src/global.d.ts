import type { RoomSession } from './features/room/roomSession'
import type { SyncProbe } from './player/syncEngine'

declare global {
  interface Window {
    /** Тестовый хук (SPEC §10): позиция, ожидаемая позиция, offset часов. */
    __syncProbe?: () => SyncProbe
    __roomSession?: RoomSession
  }
}

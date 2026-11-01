import type { RoomSession } from './features/room/roomSession'
import type { SyncProbe } from './player/syncEngine'

declare global {
  /** Идентификатор сборки, подставляет Vite. */
  const __BUILD_ID__: string

  interface Window {
    /** Тестовый хук (SPEC §10): позиция, ожидаемая позиция, offset часов. */
    __syncProbe?: () => SyncProbe
    __roomSession?: RoomSession
  }
}

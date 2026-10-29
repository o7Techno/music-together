import { createContext, useContext } from 'react'

import type { RoomSession } from './roomSession'

export const RoomContext = createContext<RoomSession | null>(null)

export function useRoomSession(): RoomSession {
  const session = useContext(RoomContext)
  if (!session) throw new Error('useRoomSession outside RoomContext')
  return session
}

// Текущая сессия комнаты как внешний стор: создаётся/закрывается эффектом страницы,
// компоненты подписываются без setState внутри эффекта (корректно и в StrictMode).

import { create } from 'zustand'

import { toast } from '@/shared/ui/Toaster'

import { RoomSession } from './roomSession'

interface SessionState {
  session: RoomSession | null
}

export const useSessionStore = create<SessionState>(() => ({ session: null }))

let offError: (() => void) | null = null

export function openRoom(slug: string): void {
  closeRoom()
  const session = new RoomSession(slug)
  offError = session.onError((err) => {
    toast.error(err.message)
  })
  session.start()
  useSessionStore.setState({ session })
}

export function closeRoom(): void {
  const { session } = useSessionStore.getState()
  offError?.()
  offError = null
  session?.dispose()
  useSessionStore.setState({ session: null })
}

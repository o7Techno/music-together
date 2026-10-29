import { useCallback } from 'react'

import { toast } from '@/shared/ui/Toaster'

import { useRoomSession } from './RoomContext'
import { CommandError, type RoomSession } from './roomSession'

type Command = Parameters<RoomSession['command']>[0]

/** Отправка команды с показом ошибки тостом. «Устаревшие» команды — мягкое уведомление. */
export function useCommand() {
  const session = useRoomSession()
  return useCallback(
    async (cmd: Command): Promise<boolean> => {
      try {
        await session.command(cmd)
        return true
      } catch (err) {
        if (err instanceof CommandError) {
          if (err.code === 'stale') toast.info(err.message)
          else toast.error(err.message)
        } else {
          toast.error('Что-то пошло не так.')
        }
        return false
      }
    },
    [session],
  )
}

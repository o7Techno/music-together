// Горячие клавиши плеера (SPEC §4.5): пробел — пауза, ←/→ — ±10 с, Shift+→ — следующий,
// Shift+← — предыдущий. Не срабатывают в полях ввода и на кнопках (там пробел — нажатие).

import { useEffect } from 'react'

import { useRoomSession } from './RoomContext'
import { useRoomStore } from './roomStore'
import { usePlaybackActions } from './usePlaybackActions'

const SEEK_STEP_MS = 10_000

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return Boolean(
    el?.closest('input, textarea, select, button, a, [contenteditable="true"], [role="slider"]'),
  )
}

export function usePlayerHotkeys(): void {
  const session = useRoomSession()
  const actions = usePlaybackActions()
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return
      const playback = useRoomStore.getState().playback
      switch (e.code) {
        case 'Space':
          e.preventDefault()
          actions.playPause()
          break
        case 'ArrowRight':
          e.preventDefault()
          if (e.shiftKey) actions.next()
          else if (playback?.queueItemId) {
            actions.seek(session.engine.expectedPositionMs() + SEEK_STEP_MS)
          }
          break
        case 'ArrowLeft':
          e.preventDefault()
          if (e.shiftKey) actions.prev()
          else if (playback?.queueItemId) {
            actions.seek(Math.max(0, session.engine.expectedPositionMs() - SEEK_STEP_MS))
          }
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [session, actions])
}

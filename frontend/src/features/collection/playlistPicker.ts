// Какие треки сейчас добавляем в плейлист. Диалог один на комнату: строк в списках сотни.

import { create } from 'zustand'

export interface PlaylistTarget {
  trackIds: string[]
  title: string
}

export const usePlaylistPicker = create<{
  target: PlaylistTarget | null
  open: (target: PlaylistTarget) => void
  close: () => void
}>((set) => ({
  target: null,
  open: (target) => {
    set({ target })
  },
  close: () => {
    set({ target: null })
  },
}))

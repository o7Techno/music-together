// Навигация панели «Добавить»: вкладки и стек открытых сущностей (альбом → исполнитель → альбом…).

import { create } from 'zustand'

export type AddTab = 'search' | 'library' | 'link'

export interface EntityRef {
  type: 'album' | 'playlist' | 'artist' | 'liked'
  id: string
  title: string
}

interface AddNavState {
  tab: AddTab
  stack: EntityRef[]
  setTab: (tab: AddTab) => void
  open: (entity: EntityRef) => void
  back: () => void
  reset: () => void
}

export const useAddNav = create<AddNavState>((set) => ({
  tab: 'search',
  stack: [],
  setTab: (tab) => {
    set({ tab, stack: [] })
  },
  open: (entity) => {
    set((s) => ({ stack: [...s.stack, entity] }))
  },
  back: () => {
    set((s) => ({ stack: s.stack.slice(0, -1) }))
  },
  reset: () => {
    set({ tab: 'search', stack: [] })
  },
}))

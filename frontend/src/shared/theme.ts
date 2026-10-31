// Тема: тёмная по умолчанию, светлая по выбору (SPEC §8). Выбор запоминается в localStorage.

import { create } from 'zustand'

export type Theme = 'dark' | 'light'
const KEY = 'mt.theme'

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.classList.toggle('light', theme === 'light')
  root.classList.toggle('dark', theme === 'dark')
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'light' ? '#f6f6f8' : '#0b0b0d')
}

export const useTheme = create<{ theme: Theme; toggle: () => void }>((set, get) => ({
  theme: read(),
  toggle: () => {
    const theme = get().theme === 'dark' ? 'light' : 'dark'
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* без сохранения */
    }
    applyTheme(theme)
    set({ theme })
  },
}))

/** Вызвать до первого рендера, чтобы не мигала тема. */
export function initTheme(): void {
  applyTheme(useTheme.getState().theme)
}

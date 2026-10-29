// Тема: тёмная по умолчанию, светлая по выбору; «как в системе» — по prefers-color-scheme.

import { create } from 'zustand'

export type ThemeChoice = 'dark' | 'light' | 'system'
const KEY = 'mt.theme'

function read(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'dark' || v === 'light' || v === 'system') return v
  } catch {
    /* без localStorage — тема по умолчанию */
  }
  return 'dark'
}

function resolve(choice: ThemeChoice): 'dark' | 'light' {
  if (choice !== 'system') return choice
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function applyTheme(choice: ThemeChoice): void {
  const theme = resolve(choice)
  const root = document.documentElement
  root.classList.toggle('light', theme === 'light')
  root.classList.toggle('dark', theme === 'dark')
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'light' ? '#f6f6f8' : '#0b0b0d')
}

export const useTheme = create<{ choice: ThemeChoice; set: (c: ThemeChoice) => void }>((set) => ({
  choice: read(),
  set: (choice) => {
    try {
      localStorage.setItem(KEY, choice)
    } catch {
      /* без сохранения */
    }
    applyTheme(choice)
    set({ choice })
  },
}))

/** Вызвать до первого рендера, чтобы не мигала тема. */
export function initTheme(): void {
  applyTheme(useTheme.getState().choice)
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (useTheme.getState().choice === 'system') applyTheme('system')
  })
}

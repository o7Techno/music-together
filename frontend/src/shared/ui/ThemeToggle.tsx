import { type ThemeChoice, useTheme } from '@/shared/theme'

const NEXT: Record<ThemeChoice, ThemeChoice> = { dark: 'light', light: 'system', system: 'dark' }
const LABEL: Record<ThemeChoice, string> = {
  dark: 'Тема: тёмная',
  light: 'Тема: светлая',
  system: 'Тема: как в системе',
}
const ICON: Record<ThemeChoice, string> = { dark: '☾', light: '☀', system: '◐' }

export function ThemeToggle() {
  const choice = useTheme((s) => s.choice)
  const set = useTheme((s) => s.set)
  return (
    <button
      type="button"
      onClick={() => {
        set(NEXT[choice])
      }}
      aria-label={`${LABEL[choice]}. Переключить`}
      title={LABEL[choice]}
      className="focus-ring text-fg-muted hover:text-fg hover:bg-surface-3 flex size-9 items-center justify-center rounded-full text-lg"
    >
      <span aria-hidden="true">{ICON[choice]}</span>
    </button>
  )
}

import { useTheme } from '@/shared/theme'

export function ThemeToggle() {
  const theme = useTheme((s) => s.theme)
  const toggle = useTheme((s) => s.toggle)
  const label = theme === 'dark' ? 'Тема: тёмная' : 'Тема: светлая'
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`${label}. Переключить`}
      title={label}
      className="focus-ring text-fg-muted hover:text-fg hover:bg-surface-3 flex size-9 items-center justify-center rounded-full text-lg"
    >
      <span aria-hidden="true">{theme === 'dark' ? '☾' : '☀'}</span>
    </button>
  )
}

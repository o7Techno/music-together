// Тосты: ошибки, действия других участников, «Отменить» для удаления.

import { useEffect } from 'react'
import { create } from 'zustand'

export interface Toast {
  id: number
  text: string
  kind: 'info' | 'error' | 'success'
  action?: { label: string; run: () => void }
  durationMs: number
}

interface ToastState {
  toasts: Toast[]
  push: (t: Omit<Toast, 'id' | 'durationMs'> & { durationMs?: number }) => number
  dismiss: (id: number) => void
}

let seq = 0
const MAX_TOASTS = 4

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = ++seq
    set((s) => ({
      toasts: [...s.toasts, { durationMs: 3500, ...t, id }].slice(-MAX_TOASTS),
    }))
    return id
  },
  dismiss: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
  },
}))

export const toast = {
  info: (text: string) => useToasts.getState().push({ text, kind: 'info' }),
  error: (text: string) => useToasts.getState().push({ text, kind: 'error', durationMs: 5000 }),
  success: (text: string) => useToasts.getState().push({ text, kind: 'success' }),
  withAction: (text: string, label: string, run: () => void, durationMs = 5000) =>
    useToasts.getState().push({ text, kind: 'info', action: { label, run }, durationMs }),
}

function ToastItem({ t }: { t: Toast }) {
  const dismiss = useToasts((s) => s.dismiss)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      dismiss(t.id)
    }, t.durationMs)
    return () => {
      window.clearTimeout(timer)
    }
  }, [t.id, t.durationMs, dismiss])
  const tone =
    t.kind === 'error' ? 'border-bad/40' : t.kind === 'success' ? 'border-ok/40' : 'border-border'
  return (
    <div
      role={t.kind === 'error' ? 'alert' : 'status'}
      className={`bg-surface-2/95 pointer-events-auto flex max-w-sm items-center gap-3 rounded-xl border px-4 py-3 text-sm shadow-xl backdrop-blur ${tone}`}
    >
      <span className="flex-1">{t.text}</span>
      {t.action && (
        <button
          type="button"
          className="focus-ring text-accent rounded font-semibold hover:underline"
          onClick={() => {
            t.action?.run()
            dismiss(t.id)
          }}
        >
          {t.action.label}
        </button>
      )}
    </div>
  )
}

export function Toaster() {
  const toasts = useToasts((s) => s.toasts)
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4 lg:bottom-6"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} t={t} />
      ))}
    </div>
  )
}

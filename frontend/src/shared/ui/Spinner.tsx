export function Spinner({ className = 'size-8' }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Загрузка"
      className={`border-surface-4 border-t-accent animate-spin rounded-full border-2 ${className}`}
    />
  )
}

export function FullScreenSpinner() {
  return (
    <div className="flex min-h-dvh items-center justify-center">
      <Spinner />
    </div>
  )
}

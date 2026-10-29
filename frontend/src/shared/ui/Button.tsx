import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-black hover:bg-accent-strong font-semibold',
  secondary: 'bg-surface-3 text-fg hover:bg-surface-4',
  ghost: 'text-fg-muted hover:text-fg hover:bg-surface-3',
  danger: 'bg-red-600/90 text-white hover:bg-red-600',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
  children: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const sizes = { sm: 'h-8 px-3 text-sm', md: 'h-10 px-4', lg: 'h-12 px-6 text-lg' }[size]
  return (
    <button
      type={type}
      className={`focus-ring inline-flex items-center justify-center gap-2 rounded-full transition-colors disabled:pointer-events-none disabled:opacity-50 ${sizes} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  active?: boolean
  size?: 'sm' | 'md' | 'lg'
  children: ReactNode
}

export function IconButton({
  label,
  active = false,
  size = 'md',
  className = '',
  children,
  type = 'button',
  ...rest
}: IconButtonProps) {
  const sizes = { sm: 'size-8', md: 'size-10', lg: 'size-14' }[size]
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={`focus-ring inline-flex shrink-0 items-center justify-center rounded-full transition-colors disabled:pointer-events-none disabled:opacity-40 ${sizes} ${
        active ? 'text-accent' : 'text-fg-muted hover:text-fg'
      } hover:bg-surface-3 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

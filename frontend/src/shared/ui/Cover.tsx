import { useState } from 'react'

const SIZES = { sm: '50x50', md: '200x200', lg: '400x400', xl: '1000x1000' } as const
export type CoverSize = keyof typeof SIZES

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

/** URL обложки: шаблон провайдера с `{size}`. `fake://seed/{size}` → градиентная заглушка. */
export function coverSrc(template: string | null | undefined, size: CoverSize): string | null {
  if (!template || template.startsWith('fake://')) return null
  return template.replace('{size}', SIZES[size])
}

interface CoverProps {
  url: string | null | undefined
  size?: CoverSize
  alt?: string
  className?: string
  rounded?: string
}

export function Cover({
  url,
  size = 'md',
  alt = '',
  className = '',
  rounded = 'rounded-md',
}: CoverProps) {
  const [failed, setFailed] = useState(false)
  const src = coverSrc(url, size)
  if (!src || failed) {
    const h = hash(url ?? alt) % 360
    return (
      <div
        role="img"
        aria-label={alt || 'Обложка'}
        className={`${rounded} ${className} shrink-0`}
        style={{
          background: `linear-gradient(135deg, hsl(${String(h)} 70% 45%), hsl(${String((h + 60) % 360)} 70% 25%))`,
        }}
      />
    )
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => {
        setFailed(true)
      }}
      className={`${rounded} ${className} shrink-0 object-cover`}
    />
  )
}

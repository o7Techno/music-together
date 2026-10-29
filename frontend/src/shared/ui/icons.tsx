// Небольшой набор иконок (inline SVG, без внешних зависимостей). Цвет — currentColor.

import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Svg({ size = 20, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  )
}

export const PlayIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none" />
  </Svg>
)
export const PauseIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none" />
    <rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none" />
  </Svg>
)
export const NextIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 5v14l10-7z" fill="currentColor" stroke="none" />
    <path d="M18 5v14" />
  </Svg>
)
export const PrevIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M19 5v14L9 12z" fill="currentColor" stroke="none" />
    <path d="M6 5v14" />
  </Svg>
)
export const RepeatIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M17 2l4 4-4 4" />
    <path d="M3 11v-1a4 4 0 0 1 4-4h14" />
    <path d="M7 22l-4-4 4-4" />
    <path d="M21 13v1a4 4 0 0 1-4 4H3" />
  </Svg>
)
export const VolumeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M11 5L6 9H2v6h4l5 4z" fill="currentColor" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7" />
    <path d="M19 5a10 10 0 0 1 0 14" />
  </Svg>
)
export const MuteIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M11 5L6 9H2v6h4l5 4z" fill="currentColor" />
    <path d="M22 9l-6 6M16 9l6 6" />
  </Svg>
)
export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
)
export const PlayNextIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 6h11M3 12h11M3 18h7" />
    <path d="M16 15l5 3-5 3z" fill="currentColor" />
  </Svg>
)
export const TrashIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
  </Svg>
)
export const SearchIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4.3-4.3" />
  </Svg>
)
export const ShuffleIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5" />
  </Svg>
)
export const LinkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" />
    <path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />
  </Svg>
)
export const GripIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="9" cy="6" r="1" fill="currentColor" />
    <circle cx="15" cy="6" r="1" fill="currentColor" />
    <circle cx="9" cy="12" r="1" fill="currentColor" />
    <circle cx="15" cy="12" r="1" fill="currentColor" />
    <circle cx="9" cy="18" r="1" fill="currentColor" />
    <circle cx="15" cy="18" r="1" fill="currentColor" />
  </Svg>
)
export const CloseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
)
export const HistoryIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5M12 7v5l3 3" />
  </Svg>
)

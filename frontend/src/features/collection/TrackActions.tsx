// Личные действия над треком: ♥ и «в плейлист». Статус лайка — из общего Set, без запроса на строку.

import type { Track } from '@/shared/protocol/generated'
import { IconButton } from '@/shared/ui/Button'
import { HeartIcon, ListPlusIcon } from '@/shared/ui/icons'

import { usePlaylistPicker } from './playlistPicker'
import { useLikedIds, useToggleLike } from './useLikes'

export function LikeButton({
  track,
  size = 'sm',
  className = '',
}: {
  track: Pick<Track, 'id' | 'title'>
  size?: 'sm' | 'md'
  className?: string
}) {
  const liked = useLikedIds().has(track.id)
  const toggle = useToggleLike()
  return (
    <IconButton
      size={size}
      className={className}
      active={liked}
      aria-pressed={liked}
      label={liked ? `Убрать «${track.title}» из «Мне нравится»` : `Лайкнуть «${track.title}»`}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        toggle(track.id)
      }}
    >
      <HeartIcon size={size === 'sm' ? 16 : 20} filled={liked} />
    </IconButton>
  )
}

export function PlaylistButton({
  track,
  size = 'sm',
}: {
  track: Pick<Track, 'id' | 'title'>
  size?: 'sm' | 'md'
}) {
  const open = usePlaylistPicker((s) => s.open)
  return (
    <IconButton
      size={size}
      label={`Добавить «${track.title}» в плейлист`}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        open({ trackIds: [track.id], title: track.title })
      }}
    >
      <ListPlusIcon size={size === 'sm' ? 16 : 20} />
    </IconButton>
  )
}

/** На узком экране в строке только «в плейлист»: лайк есть в его диалоге, места мало. */
export function TrackActions({ track }: { track: Pick<Track, 'id' | 'title'> }) {
  return (
    <>
      <LikeButton track={track} className="hidden sm:inline-flex" />
      <PlaylistButton track={track} />
    </>
  )
}

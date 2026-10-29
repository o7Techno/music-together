// Плоский список строк результатов поиска по секциям — основа клавиатурной навигации.

import type {
  AlbumSummary,
  ArtistSummary,
  PlaylistSummary,
  SearchResult,
  Track,
} from '@/shared/protocol/generated'

export type SearchRow =
  | { key: string; section: Section; kind: 'track'; track: Track }
  | { key: string; section: Section; kind: 'album'; album: AlbumSummary }
  | { key: string; section: Section; kind: 'artist'; artist: ArtistSummary }
  | { key: string; section: Section; kind: 'playlist'; playlist: PlaylistSummary }

export type Section = 'best' | 'tracks' | 'albums' | 'artists' | 'playlists'

export const SECTION_TITLES: Record<Section, string> = {
  best: 'Лучший результат',
  tracks: 'Треки',
  albums: 'Альбомы',
  artists: 'Исполнители',
  playlists: 'Плейлисты',
}

export const LIMITS = { tracks: 10, albums: 6, artists: 6, playlists: 6 } as const

export function searchRows(r: SearchResult, expanded = false): SearchRow[] {
  const rows: SearchRow[] = []
  const best = r.best
  let bestKey: string | null = null
  if (best?.track) {
    bestKey = `track:${best.track.id}`
    rows.push({ key: `best:${bestKey}`, section: 'best', kind: 'track', track: best.track })
  } else if (best?.album) {
    bestKey = `album:${best.album.id}`
    rows.push({ key: `best:${bestKey}`, section: 'best', kind: 'album', album: best.album })
  } else if (best?.artist) {
    bestKey = `artist:${best.artist.id}`
    rows.push({ key: `best:${bestKey}`, section: 'best', kind: 'artist', artist: best.artist })
  } else if (best?.playlist) {
    bestKey = `playlist:${best.playlist.ref}`
    rows.push({
      key: `best:${bestKey}`,
      section: 'best',
      kind: 'playlist',
      playlist: best.playlist,
    })
  }
  const trackLimit = expanded ? Infinity : LIMITS.tracks
  for (const track of r.tracks.slice(0, trackLimit)) {
    const key = `track:${track.id}`
    if (key !== bestKey) rows.push({ key, section: 'tracks', kind: 'track', track })
  }
  for (const album of r.albums.slice(0, LIMITS.albums)) {
    const key = `album:${album.id}`
    if (key !== bestKey) rows.push({ key, section: 'albums', kind: 'album', album })
  }
  for (const artist of r.artists.slice(0, LIMITS.artists)) {
    const key = `artist:${artist.id}`
    if (key !== bestKey) rows.push({ key, section: 'artists', kind: 'artist', artist })
  }
  for (const playlist of r.playlists.slice(0, LIMITS.playlists)) {
    const key = `playlist:${playlist.ref}`
    if (key !== bestKey) rows.push({ key, section: 'playlists', kind: 'playlist', playlist })
  }
  return rows
}

/** Следующий активный индекс для стрелок (с ограничением по краям, -1 — ничего не выбрано). */
export function moveActive(current: number, delta: number, length: number): number {
  if (length === 0) return -1
  if (current < 0) return delta > 0 ? 0 : length - 1
  return Math.max(0, Math.min(length - 1, current + delta))
}

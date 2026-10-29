import type { SearchResult, Track } from '@/shared/protocol/generated'

import { moveActive, searchRows } from './searchRows'

const track = (id: string): Track => ({
  id,
  title: id,
  artists: [],
  albumId: null,
  albumTitle: null,
  durationMs: 1000,
  coverUrl: null,
  available: true,
})

const result = (over: Partial<SearchResult> = {}): SearchResult => ({
  best: null,
  tracks: [],
  albums: [],
  artists: [],
  playlists: [],
  ...over,
})

describe('searchRows', () => {
  it('orders sections and does not repeat the best result', () => {
    const rows = searchRows(
      result({
        best: { kind: 'track', track: track('t1'), album: null, artist: null, playlist: null },
        tracks: [track('t1'), track('t2')],
        artists: [{ id: 'a', name: 'A', coverUrl: null }],
      }),
    )
    expect(rows.map((r) => `${r.section}:${r.key}`)).toEqual([
      'best:best:track:t1',
      'tracks:track:t2',
      'artists:artist:a',
    ])
  })

  it('limits tracks unless expanded', () => {
    const many = result({ tracks: Array.from({ length: 30 }, (_, i) => track(`t${String(i)}`)) })
    expect(searchRows(many)).toHaveLength(10)
    expect(searchRows(many, true)).toHaveLength(30)
  })
})

describe('moveActive', () => {
  it('starts at the first/last row and clamps', () => {
    expect(moveActive(-1, 1, 5)).toBe(0)
    expect(moveActive(-1, -1, 5)).toBe(4)
    expect(moveActive(4, 1, 5)).toBe(4)
    expect(moveActive(0, -1, 5)).toBe(0)
    expect(moveActive(2, 1, 0)).toBe(-1)
  })
})

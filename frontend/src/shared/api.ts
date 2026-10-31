// REST-клиент. Сессия — httpOnly cookie (same-origin), ошибки сервера → ApiError с понятным текстом.

import type {
  AlbumSummary,
  AuthConfig,
  DevicePollResponse,
  DeviceStartResponse,
  LikedIds,
  Me,
  PlaylistSummary,
  ResolveResponse,
  RoomDetails,
  RoomSummary,
  SearchResult,
  SessionInfo,
  SlugResponse,
  StreamInfo,
  TrackList,
  WaveMix,
  WaveOptions,
} from './protocol/generated'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface ErrorBody {
  code?: string
  message?: string
  detail?: unknown
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal) {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'network', 'Нет связи с сервером. Проверьте интернет.')
  }
  if (response.status === 204) return undefined as T
  const data = (await response.json().catch(() => ({}))) as ErrorBody & T
  if (!response.ok) {
    const message =
      data.message ??
      (response.status === 422
        ? 'Некорректный запрос.'
        : 'Что-то пошло не так. Попробуйте ещё раз.')
    throw new ApiError(response.status, data.code ?? 'http_' + String(response.status), message)
  }
  return data as T
}

function roomQuery(room: string | undefined): string {
  return room ? `?room=${encodeURIComponent(room)}` : ''
}

export const api = {
  authConfig: () => request<AuthConfig>('GET', '/api/auth/config'),
  me: () => request<Me>('GET', '/api/auth/me'),
  session: () => request<SessionInfo>('GET', '/api/auth/session'),
  devLogin: (name: string) => request<Me>('POST', '/api/auth/dev-login', { name }),
  logout: () => request<undefined>('POST', '/api/auth/logout'),
  deviceStart: () => request<DeviceStartResponse>('POST', '/api/auth/device/start'),
  devicePoll: (flowId: string) =>
    request<DevicePollResponse>('POST', '/api/auth/device/poll', { flowId }),
  tokenLogin: (token: string) => request<Me>('POST', '/api/auth/token-login', { token }),

  myRooms: () => request<RoomSummary[]>('GET', '/api/rooms'),
  createRoom: (name?: string) => request<RoomSummary>('POST', '/api/rooms', { name: name ?? null }),
  room: (slug: string) => request<RoomDetails>('GET', `/api/rooms/${encodeURIComponent(slug)}`),
  renameRoom: (slug: string, name: string) =>
    request<RoomDetails>('PATCH', `/api/rooms/${encodeURIComponent(slug)}`, { name }),
  updateRoom: (slug: string, changes: { waveMix?: WaveMix; announceLikes?: boolean }) =>
    request<RoomDetails>('PATCH', `/api/rooms/${encodeURIComponent(slug)}`, changes),
  deleteRoom: (slug: string) =>
    request<undefined>('DELETE', `/api/rooms/${encodeURIComponent(slug)}`),
  reissueLink: (slug: string) =>
    request<SlugResponse>('POST', `/api/rooms/${encodeURIComponent(slug)}/reissue`),
  kick: (slug: string, userId: string) =>
    request<undefined>(
      'POST',
      `/api/rooms/${encodeURIComponent(slug)}/kick/${encodeURIComponent(userId)}`,
    ),

  search: (q: string, signal?: AbortSignal) =>
    request<SearchResult>('GET', `/api/search?q=${encodeURIComponent(q)}`, undefined, signal),
  album: (id: string) => request<TrackList>('GET', `/api/albums/${encodeURIComponent(id)}`),
  playlist: (ref: string) => request<TrackList>('GET', `/api/playlists/${encodeURIComponent(ref)}`),
  artist: (id: string) => request<TrackList>('GET', `/api/artists/${encodeURIComponent(id)}`),
  myPlaylists: () => request<PlaylistSummary[]>('GET', '/api/me/playlists'),
  myLiked: () => request<TrackList>('GET', '/api/me/liked'),
  myAlbums: () => request<AlbumSummary[]>('GET', '/api/me/albums'),
  resolveLinks: (text: string, signal?: AbortSignal) =>
    request<ResolveResponse>('POST', '/api/resolve-link', { text }, signal),
  likedIds: () => request<LikedIds>('GET', '/api/me/liked/ids'),
  like: (trackId: string, room?: string) =>
    request<undefined>('PUT', `/api/me/liked/${encodeURIComponent(trackId)}${roomQuery(room)}`),
  unlike: (trackId: string, room?: string) =>
    request<undefined>('DELETE', `/api/me/liked/${encodeURIComponent(trackId)}${roomQuery(room)}`),
  createPlaylist: (title: string) =>
    request<PlaylistSummary>('POST', '/api/me/playlists', { title }),
  addToPlaylist: (ref: string, trackIds: string[], allowDuplicate: boolean) =>
    request<PlaylistSummary>('POST', `/api/me/playlists/${encodeURIComponent(ref)}/tracks`, {
      trackIds,
      allowDuplicate,
    }),
  removeFromPlaylist: (ref: string, trackId: string) =>
    request<PlaylistSummary>(
      'DELETE',
      `/api/me/playlists/${encodeURIComponent(ref)}/tracks/${encodeURIComponent(trackId)}`,
    ),
  waveOptions: () => request<WaveOptions>('GET', '/api/me/wave/options'),
  updateMySettings: (settings: { waveLearning: boolean }) =>
    request<Me>('PATCH', '/api/me/settings', settings),
  stream: (trackId: string) =>
    request<StreamInfo>('GET', `/api/stream/${encodeURIComponent(trackId)}`),
}

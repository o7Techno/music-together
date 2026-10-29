/* Сгенерировано из Pydantic-моделей бэкенда (npm run gen:types). Не редактировать вручную. */

/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "AddPosition".
 */
export type AddPosition = 'end' | 'next' | 'now'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "EntityKind".
 */
export type EntityKind = 'track' | 'album' | 'artist' | 'playlist'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage =
  | Ping
  | Ready
  | ClientStatus
  | DriftReport
  | CmdPlay
  | CmdPause
  | CmdSeek
  | CmdNext
  | CmdPrev
  | CmdPlayItem
  | CmdSetRepeat
  | QueueAdd
  | QueueRemove
  | QueueMove
  | QueueShuffle
  | QueueClear
  | ChatSend
  | ReactionSend
export type SyncState = 'in_sync' | 'catching_up' | 'buffering' | 'unstable' | 'idle'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "RepeatMode".
 */
export type RepeatMode = 'off' | 'queue' | 'track'
export type AddPosition1 = 'end' | 'next' | 'now'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CloseReason".
 */
export type CloseReason = 'deleted' | 'kicked' | 'restart' | 'replaced'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "EventKind".
 */
export type EventKind =
  | 'joined'
  | 'left'
  | 'play'
  | 'pause'
  | 'seek'
  | 'next'
  | 'prev'
  | 'play_item'
  | 'queue_add'
  | 'queue_remove'
  | 'queue_move'
  | 'queue_shuffle'
  | 'queue_clear'
  | 'repeat'
  | 'renamed'
  | 'kicked'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "SyncState".
 */
export type SyncState1 = 'in_sync' | 'catching_up' | 'buffering' | 'unstable' | 'idle'
export type PlaybackStatus = 'playing' | 'paused' | 'loading'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "PlaybackStatus".
 */
export type PlaybackStatus1 = 'playing' | 'paused' | 'loading'
export type RepeatMode1 = 'off' | 'queue' | 'track'
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage =
  | Pong
  | Snapshot
  | PlaybackMessage
  | QueueMessage
  | MembersMessage
  | RoomInfoMessage
  | EventMessage
  | ChatMessageEnvelope
  | Ack
  | ErrorMessage
  | Closed
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "StreamMode".
 */
export type StreamMode = 'direct' | 'proxy'

export interface Protocol {
  Ack?: Ack
  AddPosition?: AddPosition
  AlbumSummary?: AlbumSummary
  ArtistRef?: ArtistRef
  ArtistSummary?: ArtistSummary
  AuthConfig?: AuthConfig
  BestResult?: BestResult
  ChatMessage?: ChatMessage
  ChatMessageEnvelope?: ChatMessageEnvelope
  ChatSend?: ChatSend
  ClientMessage?: ClientMessage
  ClientStatus?: ClientStatus
  CloseReason?: CloseReason
  Closed?: Closed
  CmdNext?: CmdNext
  CmdPause?: CmdPause
  CmdPlay?: CmdPlay
  CmdPlayItem?: CmdPlayItem
  CmdPrev?: CmdPrev
  CmdSeek?: CmdSeek
  CmdSetRepeat?: CmdSetRepeat
  DevicePollResponse?: DevicePollResponse
  DeviceStartResponse?: DeviceStartResponse
  DriftReport?: DriftReport
  EntityKind?: EntityKind
  ErrorMessage?: ErrorMessage
  EventKind?: EventKind
  EventMessage?: EventMessage
  Me?: Me
  MemberView?: MemberView
  MembersMessage?: MembersMessage
  Ping?: Ping
  PlaybackMessage?: PlaybackMessage
  PlaybackState?: PlaybackState
  PlaybackStatus?: PlaybackStatus1
  PlaylistSummary?: PlaylistSummary
  Pong?: Pong
  QueueAdd?: QueueAdd
  QueueClear?: QueueClear
  QueueItem?: QueueItem
  QueueMessage?: QueueMessage
  QueueMove?: QueueMove
  QueueRemove?: QueueRemove
  QueueShuffle?: QueueShuffle
  'QueueSource-Input'?: QueueSourceInput
  'QueueSource-Output'?: QueueSourceOutput
  QueueState?: QueueState
  ReactionSend?: ReactionSend
  Ready?: Ready
  RepeatMode?: RepeatMode
  ResolveFailure?: ResolveFailure
  ResolveResponse?: ResolveResponse
  ResolvedEntity?: ResolvedEntity
  RoomDetails?: RoomDetails
  RoomEvent?: RoomEvent
  RoomInfo?: RoomInfo
  RoomInfoMessage?: RoomInfoMessage
  RoomSummary?: RoomSummary
  SearchResult?: SearchResult
  ServerMessage?: ServerMessage
  SlugResponse?: SlugResponse
  Snapshot?: Snapshot
  StreamInfo?: StreamInfo
  StreamMode?: StreamMode
  SyncState?: SyncState1
  SyncStats?: SyncStats
  Track?: Track
  TrackList?: TrackList
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Ack".
 */
export interface Ack {
  type: 'ack'
  clientMsgId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "AlbumSummary".
 */
export interface AlbumSummary {
  id: string
  title: string
  artists: ArtistRef[]
  year: number | null
  trackCount: number | null
  coverUrl: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ArtistRef".
 */
export interface ArtistRef {
  id: string
  name: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ArtistSummary".
 */
export interface ArtistSummary {
  id: string
  name: string
  coverUrl: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "AuthConfig".
 */
export interface AuthConfig {
  devLogin: boolean
  yandexLogin: boolean
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "BestResult".
 */
export interface BestResult {
  kind: EntityKind
  track: Track | null
  album: AlbumSummary | null
  artist: ArtistSummary | null
  playlist: PlaylistSummary | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Track".
 */
export interface Track {
  id: string
  title: string
  artists: ArtistRef[]
  albumId: string | null
  albumTitle: string | null
  durationMs: number
  coverUrl: string | null
  available: boolean
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "PlaylistSummary".
 */
export interface PlaylistSummary {
  ref: string
  title: string
  ownerName: string | null
  trackCount: number | null
  coverUrl: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ChatMessage".
 */
export interface ChatMessage {
  id: string
  atMs: number
  userId: string
  userName: string
  text: string | null
  emoji: string | null
  trackId: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ChatMessageEnvelope".
 */
export interface ChatMessageEnvelope {
  type: 'chat'
  message: ChatMessage
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ChatSend".
 */
export interface ChatSend {
  type: 'chat.send'
  clientMsgId: string
  text: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Ping".
 */
export interface Ping {
  type: 'ping'
  t0: number
}
/**
 * Трек загружен и готов к старту для состояния с этой версией.
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Ready".
 */
export interface Ready {
  type: 'ready'
  version: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ClientStatus".
 */
export interface ClientStatus {
  type: 'client_status'
  audioUnlocked: boolean
  trackUnavailable?: boolean
  sync?: SyncState
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "DriftReport".
 */
export interface DriftReport {
  type: 'drift_report'
  driftMs: number
  playbackRate?: number
  offsetMs?: number
  rttMs?: number
  outputLatencyMs?: number | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdPlay".
 */
export interface CmdPlay {
  type: 'cmd.play'
  clientMsgId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdPause".
 */
export interface CmdPause {
  type: 'cmd.pause'
  clientMsgId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdSeek".
 */
export interface CmdSeek {
  type: 'cmd.seek'
  clientMsgId: string
  positionMs: number
  expectedQueueItemId: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdNext".
 */
export interface CmdNext {
  type: 'cmd.next'
  clientMsgId: string
  expectedQueueItemId: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdPrev".
 */
export interface CmdPrev {
  type: 'cmd.prev'
  clientMsgId: string
  expectedQueueItemId: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdPlayItem".
 */
export interface CmdPlayItem {
  type: 'cmd.play_item'
  clientMsgId: string
  queueItemId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "CmdSetRepeat".
 */
export interface CmdSetRepeat {
  type: 'cmd.set_repeat'
  clientMsgId: string
  mode: RepeatMode
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueAdd".
 */
export interface QueueAdd {
  type: 'queue.add'
  clientMsgId: string
  /**
   * @minItems 1
   * @maxItems 500
   */
  trackIds: string[]
  position?: AddPosition1
  index?: number | null
  source?: QueueSourceInput | null
}
/**
 * Откуда добавлены треки — для события в ленте («37 треков из плейлиста X»).
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueSource-Input".
 */
export interface QueueSourceInput {
  kind: 'album' | 'playlist' | 'artist' | 'liked' | 'search' | 'link' | 'history' | 'undo'
  title?: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueRemove".
 */
export interface QueueRemove {
  type: 'queue.remove'
  clientMsgId: string
  itemId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueMove".
 */
export interface QueueMove {
  type: 'queue.move'
  clientMsgId: string
  itemId: string
  toIndex: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueShuffle".
 */
export interface QueueShuffle {
  type: 'queue.shuffle'
  clientMsgId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueClear".
 */
export interface QueueClear {
  type: 'queue.clear'
  clientMsgId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ReactionSend".
 */
export interface ReactionSend {
  type: 'chat.react'
  clientMsgId: string
  emoji: string
}
/**
 * Сервер закрывает соединение: комната удалена, участника выгнали, сервер перезапускается.
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Closed".
 */
export interface Closed {
  type: 'closed'
  reason: CloseReason
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "DevicePollResponse".
 */
export interface DevicePollResponse {
  status: 'pending' | 'ok' | 'expired'
  me: Me | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Me".
 */
export interface Me {
  id: string
  login: string
  displayName: string
  avatarUrl: string | null
  hasPlus: boolean
  provider: string
  providerConnected: boolean
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "DeviceStartResponse".
 */
export interface DeviceStartResponse {
  flowId: string
  userCode: string
  verificationUrl: string
  expiresIn: number
  interval: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ErrorMessage".
 */
export interface ErrorMessage {
  type: 'error'
  clientMsgId: string | null
  code: string
  message: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "EventMessage".
 */
export interface EventMessage {
  type: 'event'
  event: RoomEvent
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "RoomEvent".
 */
export interface RoomEvent {
  id: string
  atMs: number
  kind: EventKind
  userId: string | null
  userName: string | null
  count: number | null
  title: string | null
  positionMs: number | null
  repeat: RepeatMode | null
  source: QueueSourceOutput | null
}
/**
 * Откуда добавлены треки — для события в ленте («37 треков из плейлиста X»).
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueSource-Output".
 */
export interface QueueSourceOutput {
  kind: 'album' | 'playlist' | 'artist' | 'liked' | 'search' | 'link' | 'history' | 'undo'
  title: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "MemberView".
 */
export interface MemberView {
  userId: string
  name: string
  avatarUrl: string | null
  online: boolean
  connections: number
  audioUnlocked: boolean
  trackUnavailable: boolean
  sync: SyncState1
  driftMedianMs: number | null
  driftP95Ms: number | null
  isOwner: boolean
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "MembersMessage".
 */
export interface MembersMessage {
  type: 'members'
  members: MemberView[]
  stats: SyncStats
}
/**
 * Статистика рассинхрона по комнате (|drift| за последние ~30 с по всем клиентам).
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "SyncStats".
 */
export interface SyncStats {
  medianMs: number | null
  p95Ms: number | null
  samples: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "PlaybackMessage".
 */
export interface PlaybackMessage {
  type: 'playback'
  state: PlaybackState
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "PlaybackState".
 */
export interface PlaybackState {
  queueItemId: string | null
  trackId: string | null
  status: PlaybackStatus
  positionMs: number
  anchorServerMs: number
  durationMs: number
  version: number
  updatedBy: string | null
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Pong".
 */
export interface Pong {
  type: 'pong'
  t0: number
  serverTime: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueItem".
 */
export interface QueueItem {
  id: string
  track: Track
  addedBy: string
  addedAtMs: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueMessage".
 */
export interface QueueMessage {
  type: 'queue'
  queue: QueueState
}
/**
 * Сериализуемый снимок очереди: уходит клиентам и в БД.
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "QueueState".
 */
export interface QueueState {
  version: number
  current: QueueItem | null
  upcoming: QueueItem[]
  history: QueueItem[]
  repeat: RepeatMode1
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ResolveFailure".
 */
export interface ResolveFailure {
  kind: string
  id: string
  message: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ResolveResponse".
 */
export interface ResolveResponse {
  items: TrackList[]
  failures: ResolveFailure[]
}
/**
 * Набор треков сущности (альбом, плейлист, артист, «Мне нравится»).
 *
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "TrackList".
 */
export interface TrackList {
  kind: EntityKind | 'liked'
  id: string
  title: string
  subtitle: string | null
  coverUrl: string | null
  tracks: Track[]
  albums: AlbumSummary[]
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "ResolvedEntity".
 */
export interface ResolvedEntity {
  kind: EntityKind
  id: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "RoomDetails".
 */
export interface RoomDetails {
  id: string
  slug: string
  name: string
  ownerId: string
  isOwner: boolean
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "RoomInfo".
 */
export interface RoomInfo {
  id: string
  slug: string
  name: string
  ownerId: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "RoomInfoMessage".
 */
export interface RoomInfoMessage {
  type: 'room'
  room: RoomInfo
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "RoomSummary".
 */
export interface RoomSummary {
  slug: string
  name: string
  isOwner: boolean
  lastJoinedAt: string | null
  online: number
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "SearchResult".
 */
export interface SearchResult {
  best: BestResult | null
  tracks: Track[]
  albums: AlbumSummary[]
  artists: ArtistSummary[]
  playlists: PlaylistSummary[]
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "Snapshot".
 */
export interface Snapshot {
  type: 'snapshot'
  serverTime: number
  selfUserId: string
  room: RoomInfo
  playback: PlaybackState
  queue: QueueState
  members: MemberView[]
  stats: SyncStats
  events: RoomEvent[]
  chat: ChatMessage[]
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "SlugResponse".
 */
export interface SlugResponse {
  slug: string
}
/**
 * This interface was referenced by `Protocol`'s JSON-Schema
 * via the `definition` "StreamInfo".
 */
export interface StreamInfo {
  trackId: string
  mode: StreamMode
  url: string
  mirrors: string[]
  codec: string
  bitrate: number
  expiresAt: string | null
}

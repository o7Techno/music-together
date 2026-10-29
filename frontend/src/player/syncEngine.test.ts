import type {
  ClientMessage,
  PlaybackState,
  QueueItem,
  QueueState,
} from '@/shared/protocol/generated'

import { SyncEngine } from './syncEngine'
import { FakeClock, FakeDeck, type FakeDeckOptions, FakeResolver, FakeScheduler } from './testing'

const SERVER_OFFSET = 5_000
const ONE_WAY_MS = 10

function ps(over: Partial<PlaybackState> = {}): PlaybackState {
  return {
    queueItemId: 'q1',
    trackId: 't1',
    status: 'loading',
    positionMs: 0,
    anchorServerMs: 0,
    durationMs: 180_000,
    version: 1,
    updatedBy: null,
    ...over,
  }
}

function queueWith(nextTrackId: string): QueueState {
  const item = (id: string, trackId: string): QueueItem => ({
    id,
    track: {
      id: trackId,
      title: trackId,
      artists: [],
      albumId: null,
      albumTitle: null,
      durationMs: 60_000,
      coverUrl: null,
      available: true,
    },
    addedBy: 'u',
    addedAtMs: 0,
  })
  return {
    version: 1,
    current: item('q1', 't1'),
    upcoming: [item('q2', nextTrackId)],
    history: [],
    repeat: 'off',
  }
}

function setup(deckOpts: FakeDeckOptions = {}) {
  const clock = new FakeClock()
  const scheduler = new FakeScheduler(clock)
  const decks = [
    new FakeDeck('a', clock, scheduler, deckOpts),
    new FakeDeck('b', clock, scheduler, deckOpts),
  ] as const
  const resolver = new FakeResolver()
  const sent: ClientMessage[] = []
  const serverNow = (): number => clock.t + SERVER_OFFSET
  // eslint-disable-next-line prefer-const -- engine нужен в замыкании send до присваивания
  let engine: SyncEngine
  const send = (msg: ClientMessage): void => {
    sent.push(msg)
    if (msg.type === 'ping') {
      const serverTime = msg.t0 + ONE_WAY_MS + SERVER_OFFSET
      scheduler.setTimeout(() => {
        engine.handleMessage({ type: 'pong', t0: msg.t0, serverTime })
      }, 2 * ONE_WAY_MS)
    }
  }
  engine = new SyncEngine({ clock, scheduler, decks, resolver, send })
  engine.start()
  engine.onConnected()
  const of = <T extends ClientMessage['type']>(type: T) =>
    sent.filter((m): m is Extract<ClientMessage, { type: T }> => m.type === type)
  return { clock, scheduler, decks, resolver, sent, engine, serverNow, of }
}

async function calibrated(env: ReturnType<typeof setup>): Promise<void> {
  await env.scheduler.advance(600)
  expect(env.engine.clockSync.calibrated).toBe(true)
}

describe('SyncEngine', () => {
  it('calibrates the clock offset from pings', async () => {
    const env = setup()
    await calibrated(env)
    expect(env.engine.clockSync.offsetMs).toBeCloseTo(SERVER_OFFSET, 0)
    expect(env.of('ping').length).toBe(8)
  })

  it('sends ready{version} once the track is buffered (barrier)', async () => {
    const env = setup()
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 7 }), false)
    expect(env.of('ready')).toHaveLength(0)
    await env.scheduler.advance(300)
    expect(env.of('ready')).toEqual([{ type: 'ready', version: 7 }])
    expect(env.resolver.calls).toEqual(['t1'])
  })

  it('does not send ready or play while audio is locked, then plays at computed position', async () => {
    const env = setup()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(500)
    expect(env.of('ready')).toHaveLength(0)

    env.engine.applyState(
      ps({ version: 2, status: 'playing', anchorServerMs: env.serverNow() }),
      false,
    )
    await env.scheduler.advance(5_000)
    expect(env.decks[0].paused).toBe(true)

    await env.engine.unlock()
    await env.scheduler.advance(2_000)
    const probe = env.engine.probe()
    expect(env.decks[0].paused).toBe(false)
    expect(Math.abs(probe.driftMs ?? Infinity)).toBeLessThan(40)
  })

  it('starts playback exactly at the future anchor', async () => {
    const env = setup({ startLatencyMs: 30 })
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(300)
    const anchor = env.serverNow() + 300
    env.engine.applyState(ps({ version: 2, status: 'playing', anchorServerMs: anchor }), false)
    await env.scheduler.advance(1_000)
    const anchorLocal = anchor - SERVER_OFFSET
    const playAt = env.decks[0].playCalls[0] ?? NaN
    // play() вызывается заранее на выученную задержку старта (по умолчанию 30 мс).
    expect(playAt).toBeGreaterThanOrEqual(anchorLocal - 30)
    expect(playAt).toBeLessThanOrEqual(anchorLocal)
    expect(Math.abs(env.engine.probe().driftMs ?? Infinity)).toBeLessThanOrEqual(20)
  })

  it('keeps drift inside the dead zone with a skewed sound card clock', async () => {
    const env = setup({ skew: 0.003 }) // +3 мс на каждую секунду — сильно хуже реальных карт
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(300)
    env.engine.applyState(
      ps({ version: 2, status: 'playing', anchorServerMs: env.serverNow() + 300 }),
      false,
    )
    await env.scheduler.advance(3_000)
    const drifts: number[] = []
    let minRate = 1
    for (let i = 0; i < 120; i++) {
      await env.scheduler.advance(250)
      drifts.push(Math.abs(env.engine.probe().driftMs ?? Infinity))
      minRate = Math.min(minRate, env.decks[0].playbackRate)
    }
    // Коррекция темпом «пилой» в пределах мёртвой зоны; после схождения темп возвращается к 1.0.
    expect(Math.max(...drifts)).toBeLessThan(25)
    expect(minRate).toBeLessThan(1)
    expect(env.engine.sync).toBe('in_sync')
  })

  it('late joiner seeks to the computed position and converges', async () => {
    const env = setup({ seekMs: 80 })
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(
      ps({ version: 9, status: 'playing', anchorServerMs: env.serverNow() - 30_000 }),
      false,
    )
    await env.scheduler.advance(1_500)
    expect(env.decks[0].seekCalls[0]).toBeGreaterThan(30_000)
    await env.scheduler.advance(1_500)
    expect(Math.abs(env.engine.probe().driftMs ?? Infinity)).toBeLessThan(20)
  })

  it('hard-seeks when far off (e.g. after a stall)', async () => {
    const env = setup()
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(300)
    env.engine.applyState(
      ps({ version: 2, status: 'playing', anchorServerMs: env.serverNow() + 300 }),
      false,
    )
    await env.scheduler.advance(2_000)
    // Эмулируем зависание: дек «потерял» 3 секунды.
    env.decks[0].pause()
    await env.scheduler.advance(3_000)
    void env.decks[0].play()
    await env.scheduler.advance(1_500)
    expect(env.decks[0].seekCalls.length).toBeGreaterThan(0)
    expect(Math.abs(env.engine.probe().driftMs ?? Infinity)).toBeLessThan(60)
  })

  it('ignores states with an older version', () => {
    const env = setup()
    env.engine.applyState(ps({ version: 5, trackId: 't5' }), false)
    env.engine.applyState(ps({ version: 4, trackId: 't4' }), false)
    expect(env.engine.state?.trackId).toBe('t5')
  })

  it('pauses on paused state at the given position', async () => {
    const env = setup()
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1, status: 'paused', positionMs: 42_000 }), false)
    await env.scheduler.advance(500)
    expect(env.decks[0].paused).toBe(true)
    expect(env.decks[0].currentTimeMs).toBe(42_000)
  })

  it('preloads the next track and swaps decks without re-resolving', async () => {
    const env = setup()
    await env.engine.unlock()
    await calibrated(env)
    env.engine.handleMessage({ type: 'queue', queue: queueWith('t2') })
    env.engine.applyState(
      ps({
        version: 1,
        status: 'playing',
        durationMs: 30_000,
        anchorServerMs: env.serverNow() + 300,
      }),
      false,
    )
    await env.scheduler.advance(15_000)
    expect(env.resolver.calls).toEqual(['t1', 't2'])
    expect(env.decks[1].src).toContain('t2')

    env.engine.applyState(ps({ version: 2, queueItemId: 'q2', trackId: 't2' }), false)
    await env.scheduler.advance(50)
    expect(env.of('ready').at(-1)).toEqual({ type: 'ready', version: 2 })
    expect(env.resolver.calls).toEqual(['t1', 't2'])
  })

  it('on playback error tries a mirror, then fetches a fresh link', async () => {
    const env = setup()
    env.resolver.mirrors = ['https://mirror.test']
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(300)
    env.decks[0].emit('error')
    await env.scheduler.advance(300)
    expect(env.decks[0].loads.at(-1)).toBe('https://mirror.test/t1.mp3')
    env.decks[0].emit('error')
    await env.scheduler.advance(300)
    expect(env.resolver.calls).toEqual(['t1', 't1'])
  })

  it('marks the track unavailable for this user and stays silent', async () => {
    const env = setup()
    env.resolver.unavailable.add('t1')
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(300)
    expect(env.engine.trackUnavailable).toBe(true)
    expect(env.of('ready')).toHaveLength(0)
    expect(env.of('client_status').at(-1)).toMatchObject({ trackUnavailable: true })
    // Следующий трек снимает флаг.
    env.engine.applyState(ps({ version: 2, queueItemId: 'q2', trackId: 't2' }), false)
    await env.scheduler.advance(300)
    expect(env.engine.trackUnavailable).toBe(false)
  })

  it('reports drift to the server every ~2 s while playing', async () => {
    const env = setup()
    await env.engine.unlock()
    await calibrated(env)
    env.engine.applyState(ps({ version: 1 }), false)
    await env.scheduler.advance(300)
    env.engine.applyState(
      ps({ version: 2, status: 'playing', anchorServerMs: env.serverNow() + 300 }),
      false,
    )
    await env.scheduler.advance(10_300)
    const reports = env.of('drift_report')
    expect(reports.length).toBeGreaterThanOrEqual(4)
    expect(reports.length).toBeLessThanOrEqual(6)
  })

  it('reverts to locked when play() is rejected by autoplay policy', async () => {
    const env = setup()
    await env.engine.unlock()
    await calibrated(env)
    env.decks[0].failNextPlay = true
    env.engine.applyState(
      ps({ version: 1, status: 'playing', anchorServerMs: env.serverNow() + 300 }),
      false,
    )
    await env.scheduler.advance(1_000)
    expect(env.engine.audioUnlocked).toBe(false)
    expect(env.of('client_status').at(-1)).toMatchObject({ audioUnlocked: false })
  })
})

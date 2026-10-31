import { DESKTOP_PROFILE, DriftController } from './driftController'
import { IOS_PROFILE, detectProfile } from './platform'

describe('DriftController', () => {
  it('does nothing inside the dead zone', () => {
    const c = new DriftController()
    expect(c.update(10, 5000, 0)).toEqual({ kind: 'none', rate: 1 })
    expect(c.update(-15, 5250, 250)).toEqual({ kind: 'none', rate: 1 })
  })

  it('slows down when ahead and speeds up when behind, proportionally and clamped', () => {
    const ahead = new DriftController()
    const a = ahead.update(40, 5000, 0)
    expect(a.kind).toBe('rate')
    if (a.kind === 'rate') expect(a.rate).toBeCloseTo(0.96)

    const behind = new DriftController()
    const b = behind.update(-30, 5000, 0)
    if (b.kind === 'rate') expect(b.rate).toBeCloseTo(1.03)

    const far = new DriftController()
    const f = far.update(600, 5000, 0)
    if (f.kind === 'rate') expect(f.rate).toBeCloseTo(1 - DESKTOP_PROFILE.maxRateDelta)
  })

  it('uses hysteresis: keeps correcting until drift is below the exit zone', () => {
    const c = new DriftController()
    c.update(30, 0, 0)
    c.update(30, 0, 250)
    c.update(30, 0, 500)
    // 15 мс — ниже мёртвой зоны, но коррекция идёт до exitZone (8 мс).
    for (let i = 0; i < 3; i++) c.update(15, 0, 750 + i * 250)
    expect(c.update(15, 0, 1500).kind).toBe('rate')
    for (let i = 0; i < 3; i++) c.update(5, 0, 1750 + i * 250)
    expect(c.update(5, 0, 2500)).toEqual({ kind: 'none', rate: 1 })
  })

  it('smooths single-sample spikes with a median', () => {
    const c = new DriftController()
    c.update(2, 0, 0)
    c.update(3, 0, 250)
    expect(c.update(500, 0, 500)).toEqual({ kind: 'none', rate: 1 })
  })

  it('hard-seeks on large drift with learned seek latency lead', () => {
    const c = new DriftController()
    const action = c.update(-2500, 10_000, 0)
    expect(action).toEqual({ kind: 'seek', targetMs: 10_000 + c.seekLatencyMs })
  })

  it('does not seek more often than every 2 s', () => {
    const c = new DriftController()
    expect(c.update(5000, 0, 0).kind).toBe('seek')
    // Сразу после seek — проверка результата, ещё большой дрейф → rate, а не новый seek.
    expect(c.update(5000, 0, 500).kind).toBe('rate')
    expect(c.update(5000, 0, 1000).kind).toBe('rate')
    expect(c.update(5000, 0, 2100).kind).toBe('seek')
  })

  it('marks unstable after 3 failed seeks in a row and recovers', () => {
    const c = new DriftController()
    let t = 0
    for (let i = 0; i < 4; i++) {
      c.update(5000, 0, t)
      t += 2100
    }
    expect(c.unstable).toBe(true)
    c.update(5000, 0, t) // seek
    c.update(5, 0, t + 300) // помог
    expect(c.unstable).toBe(false)
    expect(c.seekFailureCount).toBe(0)
  })

  it('learns seek latency from the post-seek drift', () => {
    const c = new DriftController()
    const before = c.seekLatencyMs
    c.update(3000, 0, 0)
    c.update(-80, 0, 300) // после seek всё ещё отстаём на 80 мс
    expect(c.seekLatencyMs).toBeCloseTo(before + 40)
  })

  it('works correctly with skipped ticks (background tab)', () => {
    const c = new DriftController()
    // Тики раз в 5 с вместо 250 мс — решение зависит только от текущего дрейфа.
    expect(c.update(10, 0, 0)).toEqual({ kind: 'none', rate: 1 })
    expect(c.update(12, 0, 5000)).toEqual({ kind: 'none', rate: 1 })
    expect(c.update(11, 0, 10_000)).toEqual({ kind: 'none', rate: 1 })
  })

  it('profile without rate control never changes tempo', () => {
    const c = new DriftController({ ...IOS_PROFILE, maxRateDelta: 0 })
    expect(c.update(100, 0, 0)).toEqual({ kind: 'none', rate: 1 })
  })
})

describe('detectProfile', () => {
  it.each([
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', 5, 'ios'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari', 5, 'ios'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari', 0, 'desktop'],
    ['Mozilla/5.0 (Linux; Android 15) Chrome/141', 5, 'android'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141', 0, 'desktop'],
  ])('%s → %s', (userAgent, maxTouchPoints, expected) => {
    expect(detectProfile({ userAgent, maxTouchPoints }).name).toBe(expected)
  })

  it('honours explicit override', () => {
    expect(detectProfile({ userAgent: 'x', maxTouchPoints: 0, override: 'ios' }).name).toBe('ios')
  })

  it('seeks rarely once repeated seeks keep failing', () => {
    const c = new DriftController()
    let now = 0
    // Каждая перемотка не помогает: дрейф остаётся большим.
    c.update(5000, 10_000, now)
    now += 2000
    c.update(5000, 10_000, now)
    for (let i = 0; i < 3; i++) {
      now += 2000
      c.update(5000, 10_000, now)
    }
    expect(c.seekFailureCount).toBeGreaterThan(3)
    now += 2000
    expect(c.update(5000, 10_000, now).kind).not.toBe('seek')
    now += 30_000
    expect(c.update(5000, 10_000, now).kind).toBe('seek')
  })
})

import { ClockSync } from './clockSync'

/** Смоделировать пинг: истинный offset сервера, задержки туда/обратно. */
function ping(sync: ClockSync, t0: number, trueOffset: number, upMs: number, downMs: number): void {
  const serverTime = t0 + upMs + trueOffset
  sync.addSample(t0, serverTime, t0 + upMs + downMs)
}

describe('ClockSync', () => {
  it('estimates offset exactly with symmetric latency', () => {
    const sync = new ClockSync()
    for (let i = 0; i < 8; i++) ping(sync, 1000 + i * 60, 5000, 20, 20)
    expect(sync.calibrated).toBe(true)
    expect(sync.offsetMs).toBeCloseTo(5000, 5)
    expect(sync.rttMs).toBe(40)
  })

  it('uses lowest-RTT samples and ignores outliers', () => {
    const sync = new ClockSync()
    // Выбросы: огромная асимметричная задержка (очередь в сети).
    ping(sync, 0, -300, 400, 10)
    ping(sync, 100, -300, 10, 350)
    for (let i = 0; i < 6; i++) ping(sync, 200 + i * 60, -300, 15, 15)
    expect(Math.abs(sync.offsetMs - -300)).toBeLessThan(1)
  })

  it('error is bounded by half the asymmetry of the best samples', () => {
    const sync = new ClockSync()
    for (let i = 0; i < 8; i++) ping(sync, i * 60, 1234, 30 + (i % 3), 10)
    // Асимметрия 20 мс → ошибка ≈ 10 мс.
    expect(Math.abs(sync.offsetMs - 1234)).toBeLessThanOrEqual(11)
  })

  it('smooths small changes but jumps on large clock changes', () => {
    const sync = new ClockSync()
    for (let i = 0; i < 8; i++) ping(sync, i * 60, 100, 10, 10)
    sync.resetWindow()
    for (let i = 0; i < 3; i++) ping(sync, 1000 + i * 60, 140, 10, 10)
    // Сглаживание: не сразу 140.
    expect(sync.offsetMs).toBeGreaterThan(100)
    expect(sync.offsetMs).toBeLessThan(140)
    sync.resetWindow()
    for (let i = 0; i < 3; i++) ping(sync, 2000 + i * 60, 10_000, 10, 10)
    expect(sync.offsetMs).toBeCloseTo(10_000, 5)
  })

  it('rejects invalid samples', () => {
    const sync = new ClockSync()
    sync.addSample(100, 5000, 50)
    expect(sync.calibrated).toBe(false)
    expect(sync.sampleCount).toBe(0)
  })

  it('converts between local and server time', () => {
    const sync = new ClockSync()
    for (let i = 0; i < 3; i++) ping(sync, i * 60, 250, 5, 5)
    expect(sync.serverNow(1000)).toBeCloseTo(1250)
    expect(sync.toLocal(1250)).toBeCloseTo(1000)
  })

  it('forgets old samples even if their RTT was the best', () => {
    const sync = new ClockSync()
    for (let i = 0; i < 3; i++) sync.addSample(i, 1000 + i + 1, i + 2)
    expect(sync.offsetMs).toBeCloseTo(1000, 0)
    // Прошло больше двух минут, часы сместились, а RTT стал хуже.
    const later = 200_000
    for (let i = 0; i < 3; i++) {
      sync.addSample(later + i, later + i + 5000 + 20, later + i + 40)
    }
    expect(sync.offsetMs).toBeCloseTo(5000, 0)
  })
})

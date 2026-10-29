// E2E синхронизации на FakeProvider (SPEC §10): 3 независимых браузерных контекста.

import { writeFileSync } from 'node:fs'

import { type Page, expect, test } from '@playwright/test'

import {
  addTrack,
  createRoom,
  enterRoom,
  measureSpread,
  newUser,
  probe,
  waitPlaying,
} from './helpers'

// Цели SPEC §5.1 (десктоп): медиана ≤ 30 мс, p95 ≤ 80 мс. На shared-раннерах CI (2 vCPU на
// три браузерных контекста) пороги мягче — см. DECISIONS D-022.
const CI = Boolean(process.env.CI)
const MEDIAN_LIMIT = CI ? 50 : 30
const P95_LIMIT = CI ? 150 : 80

async function threeInRoom(browser: import('@playwright/test').Browser): Promise<Page[]> {
  const anna = await newUser(browser, 'Аня')
  const slug = await createRoom(anna)
  const petya = await newUser(browser, 'Петя')
  const vera = await newUser(browser, 'Вера')
  await enterRoom(anna, slug)
  await enterRoom(petya, slug)
  await enterRoom(vera, slug)
  await expect(anna.getByTestId('members').getByRole('listitem')).toHaveCount(3)
  return [anna, petya, vera]
}

test('three clients play in sync (30 s measurement)', async ({ browser }, testInfo) => {
  const pages = await threeInRoom(browser)
  const [anna] = pages as [Page, Page, Page]
  await addTrack(anna, 'четыре', 'Четыре минуты')
  for (const p of pages) await waitPlaying(p, 'fake-9')

  // Установившийся режим: после старта даём пару секунд на сходимость (цель ≤ 1.5 с).
  await anna.waitForTimeout(2_000)
  const stats = await measureSpread(pages, 30_000)
  const report = JSON.stringify({ ci: CI, ...stats }, null, 2)
  console.log('sync stats', report)
  writeFileSync(testInfo.outputPath('sync-stats.json'), report)
  await testInfo.attach('sync-stats', { body: report, contentType: 'application/json' })

  expect(stats.samples).toBeGreaterThan(60)
  expect(stats.spreadMedianMs).toBeLessThanOrEqual(MEDIAN_LIMIT)
  expect(stats.spreadP95Ms).toBeLessThanOrEqual(P95_LIMIT)
})

test('pause, seek and next apply to everyone', async ({ browser }) => {
  const pages = await threeInRoom(browser)
  const [anna, petya, vera] = pages as [Page, Page, Page]
  await addTrack(anna, 'три минуты', 'Три минуты')
  await addTrack(anna, 'две минуты', 'Две минуты')
  for (const p of pages) await waitPlaying(p, 'fake-8')

  // Пауза от Пети — у всех.
  const t0 = Date.now()
  await petya.getByRole('button', { name: 'Пауза', exact: true }).click()
  for (const p of pages) {
    await expect.poll(async () => (await probe(p))?.status, { intervals: [50] }).toBe('paused')
  }
  console.log('pause applied to all in', Date.now() - t0, 'ms (including test polling)')

  // Перемотка от Веры на 1:30 — все играют с ~90 с и в синхроне.
  await vera.getByRole('button', { name: 'Играть', exact: true }).click()
  for (const p of pages) await waitPlaying(p, 'fake-8')
  await vera.evaluate(() => {
    const s = window.__roomSession
    const state = s?.engine.state
    if (!s || !state) throw new Error('no session')
    void s.command({ type: 'cmd.seek', positionMs: 90_000, expectedQueueItemId: state.queueItemId })
  })
  for (const p of pages) {
    await expect
      .poll(
        async () => {
          const pr = await probe(p)
          return pr?.status === 'playing' && pr.actualMs !== null && pr.actualMs > 89_000
        },
        { intervals: [100] },
      )
      .toBe(true)
  }
  const afterSeek = await measureSpread(pages, 3_000)
  expect(afterSeek.spreadMedianMs).toBeLessThanOrEqual(MEDIAN_LIMIT)

  // «Следующий» от Ани — у всех новый трек.
  await anna.getByRole('button', { name: 'Следующий', exact: true }).click()
  for (const p of pages) await waitPlaying(p, 'fake-6')
  await expect(petya.getByTestId('track-title')).toHaveText('Две минуты')
})

test('client returns to sync after going offline', async ({ browser }) => {
  const pages = await threeInRoom(browser)
  const [anna, petya] = pages as [Page, Page, Page]
  await addTrack(anna, 'четыре', 'Четыре минуты')
  for (const p of pages) await waitPlaying(p, 'fake-9')

  await petya.context().setOffline(true)
  await petya.evaluate(() => {
    window.__roomSession?.dropConnection()
  })
  await expect(petya.getByTestId('connection')).toContainText(/Нет связи/)
  // Пока Петя офлайн, комната ставит паузу и снова играет — он должен это догнать.
  await anna.getByRole('button', { name: 'Пауза', exact: true }).click()
  await anna.waitForTimeout(1_000)
  await anna.getByRole('button', { name: 'Играть', exact: true }).click()
  await anna.waitForTimeout(8_000)

  await petya.context().setOffline(false)
  await waitPlaying(petya, 'fake-9', 15_000)
  await petya.waitForTimeout(1_500)
  const stats = await measureSpread(pages, 5_000)
  expect(stats.spreadMedianMs).toBeLessThanOrEqual(MEDIAN_LIMIT)
})
